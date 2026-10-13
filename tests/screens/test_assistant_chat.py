"""Assistant chat-surface tests: the state machine, throttles, and lifecycle.

The important properties are the ones a user would feel:

* **The two clocks starve independently.** Sharing one throttle meant a text
  flush reset the thought clock, so thinking could go unseen for 500ms every
  time a text token landed.
* **State mutates on every event; only the repaint is throttled.** A throttled
  text event must still accumulate, or the final text silently drops tokens.
* **Minimize never cancels, and never tears down.** A running turn survives,
  and so does a pending approval — re-opening lands on the same card.
* **Busy never double-sends**, so a double-tap cannot double the spend.
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace as NS

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from kani import AIFunction

from screens import assistant_view
from services import ai_tools, kani_backend


class FakeEvent:
    def set(self):
        pass


class FakePage:
    """Just enough Page for the chat: no server, no widget tree."""

    def __init__(self):
        self.views = []
        self.width = 420
        self.updates = 0

    def update(self):
        self.updates += 1

    def run_task(self, coro):
        # The chat schedules a credit read; close the coroutine so no
        # "never awaited" warning escapes into the test output.
        try:
            coro.close()
        except Exception:
            pass


class FakeController:
    def __init__(self):
        self.revealed = []
        self.history_calls = []

    def reveal_cell(self, session_name, cell_id):
        self.revealed.append((session_name, cell_id))

    def open_assistant_history(self, rows):
        self.history_calls.append(list(rows or []))


def _state(**kw):
    # A plain namespace: the chat only reads these, and the pair exercises the
    # same attribute surface the real AppState exposes.
    base = {
        "active_session_name": "sess",
        "ai_model": "auto",
        "ai_help": True,
        "ai_router_url": "http://127.0.0.1:8082/v1",
        "is_premium": False,
        "credits_revision": 0,
        "active_assistant_conversation": "",
        "assistant_open": False,
        "assistant_minimized": False,
    }
    base.update(kw)
    return NS(**base)


def _session(tmp_path, monkeypatch, controller=None):
    """A ChatSession whose conversation storage is redirected to a tmp dir."""
    from services import conversation_service as conversations

    monkeypatch.setattr(conversations, "_tombstones", {})
    monkeypatch.setattr(
        conversations, "conversations_dir", lambda: tmp_path
    )
    monkeypatch.setattr(conversations, "ensure_active", lambda: "chat1")
    state = _state()
    session = assistant_view.ChatSession(
        FakePage(), state, NS(credits=None), controller
    )
    return session


def _drive(session, events):
    """Push turns through _emit without the agent loop, then return the last
    assistant turn."""
    session._turns.clear()
    session._turns.append({"role": "user", "text": "hello"})
    current = assistant_view._empty_turn()
    session._turns.append(current)
    session._current = current
    for event, data in events:
        session._emit(event, data)
    return current


# ── the two throttle clocks ──────────────────────────────────────────────────


def test_text_and_thought_throttle_independently(tmp_path, monkeypatch):
    """A text flush must not reset the thought clock, and vice versa."""
    session = _session(tmp_path, monkeypatch)
    turn = _drive(session, [("text_partial", {"text": "abc"})])

    # Force the clocks apart: the last text flush is "now", the last thought
    # flush is in the past. With a shared clock the thought event would be
    # swallowed by the text throttle.
    session._last_text_flush = 1_000.0
    session._last_thought_flush = 0.0
    session._emit("text_partial", {"text": "def"})
    session._emit("thought", {"text": "hmm"})
    assert "def" in turn["text"], "a throttled text event must still accumulate"
    assert "hmm" in turn["thought"], "a text flush must not swallow a thought"


def test_state_accumulates_even_when_repaint_is_throttled(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    turn = _drive(
        session,
        [("text_partial", {"text": "a"}), ("text_partial", {"text": "b"}),
         ("text_partial", {"text": "c"})],
    )
    # All three events land inside the 0.2s text window, so only one repaint
    # happened — but nothing may be dropped.
    assert turn["text"] == "abc"


def test_thought_is_capped_so_a_long_think_cannot_grow_without_bound(
    tmp_path, monkeypatch
):
    session = _session(tmp_path, monkeypatch)
    turn = _drive(
        session, [("thought", {"text": "x" * (assistant_view._THOUGHT_CAP * 2)})]
    )
    assert len(turn["thought"]) <= assistant_view._THOUGHT_CAP


# ── composer guards ─────────────────────────────────────────────────────────


def test_busy_never_double_sends(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    session._busy = True
    before = list(session._turns)
    session.send("second question")
    assert session._turns == before, "a busy chat must not accept another turn"


def test_empty_text_never_sends(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    session.send("   ")
    assert session._turns == []


def test_stop_cancels_the_running_task(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)

    cancelled = []

    class FakeTask:
        def done(self):
            return False

        def cancel(self):
            cancelled.append(True)

    session._task = FakeTask()
    session.stop()
    assert cancelled, "stop must cancel the in-flight turn"
    assert session._cancel.is_set(), "stop must also raise the cancel flag"


# ── lifecycle ────────────────────────────────────────────────────────────────


def test_minimize_keeps_the_session_and_does_not_cancel(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    session._turns.append({"role": "user", "text": "keep me"})

    cancelled = []

    class FakeTask:
        def done(self):
            return False

        def cancel(self):
            cancelled.append(True)

    session._task = FakeTask()
    session.close()

    page = session.page
    assert page.views == [], "minimize pops the view"
    assert session._turns, "minimize must not wipe the transcript"
    assert not cancelled, "close() must not cancel a running turn"
    assert session.state.assistant_minimized is True


def test_restore_reuses_the_same_session(tmp_path, monkeypatch):
    page = FakePage()
    controller = FakeController()
    from services import conversation_service as conversations

    monkeypatch.setattr(conversations, "_tombstones", {})
    monkeypatch.setattr(conversations, "conversations_dir", lambda: tmp_path)
    monkeypatch.setattr(conversations, "ensure_active", lambda: "chat1")

    state = _state()
    first = assistant_view.open_assistant(page, state, NS(credits=None), controller)
    first._turns.append({"role": "user", "text": "still here"})

    second = assistant_view.open_assistant(page, state, NS(credits=None), controller)

    assert first is second, "re-opening must reuse the retained session"
    assert len(page.views) == 1, "re-open must not stack a second view"
    assert any(
        t.get("text") == "still here" for t in second._turns
    ), "the transcript survives minimize/restore"


def test_shutdown_stops_the_turn_and_marks_closed(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    session._turns.append({"role": "user", "text": "bye"})

    cancelled = []

    class FakeTask:
        def done(self):
            return False

        def cancel(self):
            cancelled.append(True)

    session._task = FakeTask()
    session.shutdown()

    assert cancelled, "shutdown must cancel the running turn"
    assert session._closing is True
    # After teardown, nothing may push to the UI.
    session._emit("text_partial", {"text": "ghost"})
    assert all(
        "ghost" not in str(t.get("text", "")) for t in session._turns
    ), "a closed session must not accept events"


# ── approval gate ────────────────────────────────────────────────────────────


def _run_async(coro):
    return asyncio.run(coro)


def test_approval_denies_and_returns_false(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)

    async def _scenario():
        task = asyncio.ensure_future(session.ask_confirm("Delete file", "/content/x.csv"))
        await asyncio.sleep(0)
        session._confirm_decision("deny")
        return await task

    assert _run_async(_scenario()) is False


def test_approval_allows_and_returns_true(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)

    async def _scenario():
        task = asyncio.ensure_future(session.ask_confirm("Restart kernel", "all vars lost"))
        await asyncio.sleep(0)
        session._confirm_decision("allow")
        return await task

    assert _run_async(_scenario()) is True


def test_approval_timeout_denies(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    monkeypatch.setattr(assistant_view, "APPROVAL_TIMEOUT_SEC", 0)
    assert _run_async(session.ask_confirm("Stop session", "vm killed")) is False


def test_second_decision_on_a_settled_gate_is_ignored(tmp_path, monkeypatch):
    """First answer wins — a late tap must not race the resumed tool."""
    session = _session(tmp_path, monkeypatch)

    async def _scenario():
        task = asyncio.ensure_future(session.ask_confirm("Delete file", "x"))
        await asyncio.sleep(0)
        session._confirm_decision("deny")
        session._confirm_decision("allow")
        return await task

    assert _run_async(_scenario()) is False


def test_an_approval_survives_minimize(tmp_path, monkeypatch):
    """Minimizing mid-gate must not settle the gate — the card comes back."""
    session = _session(tmp_path, monkeypatch)

    async def _scenario():
        task = asyncio.ensure_future(session.ask_confirm("Restart kernel", "vars"))
        await asyncio.sleep(0)
        pending = session._confirm
        session.close()
        assert session._confirm is not None, "minimize must not clear a pending gate"
        assert task.done() is False, "minimize must not settle the gate"
        session._confirm_decision("allow")
        result = await task
        assert pending is not None
        return result

    assert _run_async(_scenario()) is True


# ── step rows: identity, failure, and the orphaned spinner ──────────────────


def test_two_calls_to_the_same_tool_get_two_rows(tmp_path, monkeypatch):
    """The same tool twice in one turn is two rows, each with its own id.

    Rows keyed by tool name collide: the second call overwrites the first row's
    output and leaves a ProgressRing the user waits on forever.
    """
    session = _session(tmp_path, monkeypatch)
    _drive(
        session,
        [
            ("step_start", {"label": "Running code", "id": "call_1", "name": "_exec"}),
            ("step_done", {"label": "Running code", "id": "call_1", "result": "first"}),
            ("step_start", {"label": "Running code", "id": "call_2", "name": "_exec"}),
            ("step_done", {"label": "Running code", "id": "call_2", "result": "second"}),
        ],
    )
    rows = session._turns[-1]["steps_rows"]
    assert len(rows) == 2, rows
    assert [r["id"] for r in rows] == ["call_1", "call_2"], rows
    assert [r["outcome"] for r in rows] == ["first", "second"], rows
    assert all(r["state"] == "done" for r in rows), rows


def test_a_failed_tool_row_is_an_error_not_a_green_check(tmp_path, monkeypatch):
    """A tool that raised must render red, or a failure reads as success."""
    session = _session(tmp_path, monkeypatch)
    _drive(
        session,
        [
            ("step_start", {"label": "Running code", "id": "call_1", "name": "_exec"}),
            (
                "step_error",
                {
                    "label": "Running code",
                    "id": "call_1",
                    "result": "(the _exec tool failed: kernel gone)",
                    "error": "kernel gone",
                },
            ),
        ],
    )
    row = session._turns[-1]["steps_rows"][0]
    assert row["state"] == "error", row
    assert row["error"] == "kernel gone", row
    assert "kernel gone" in row["outcome"], row


def test_a_row_left_spinning_is_closed_when_the_turn_ends(tmp_path, monkeypatch):
    """A tool that opened a row and then the turn died gets settled.

    Otherwise the user stares at a spinner for a row that will never finish.
    """
    session = _session(tmp_path, monkeypatch)
    _drive(
        session,
        [
            ("step_start", {"label": "Reading the notebook", "id": "c1", "name": "read_notebook"}),
            ("error", {"kind": "unavailable", "message": "Could not reach the Assistant."}),
        ],
    )
    row = session._turns[-1]["steps_rows"][0]
    assert row["state"] == "error", row
    assert row["error"], row


def test_a_stopped_turn_keeps_its_cost_and_text(tmp_path, monkeypatch):
    """The work before the stop was billed, so the turn must show its price."""
    session = _session(tmp_path, monkeypatch)
    _drive(
        session,
        [
            ("text_partial", {"text": "Here"}),
            ("stopped", {"text": "Here", "cost": 1, "steps": 1}),
        ],
    )
    turn = session._turns[-1]
    assert turn["stopped"] is True, turn
    assert turn["partial"] is False, turn
    assert turn["text"] == "Here", turn
    assert turn["cost"] == 1, turn


def test_a_stopped_turn_is_not_also_rendered_finished(tmp_path, monkeypatch):
    """One terminal event: a stopped bubble must not also show an answer.

    This is the shape of the bug: emitting stopped and then text_final made a
    cancelled turn look like a completed one.
    """
    events: list[str] = []
    session = _session(tmp_path, monkeypatch)
    original = session._emit

    def spy(event, data):
        events.append(event)
        original(event, data)

    monkeypatch.setattr(session, "_emit", spy)
    _drive(
        session,
        [
            ("stopped", {"text": "partial", "cost": 1, "steps": 1}),
        ],
    )
    assert "text_final" not in events, events


def test_a_long_tool_output_does_not_become_a_long_label(tmp_path, monkeypatch):
    """The row shows what the tool did, not a paste of everything it printed."""
    session = _session(tmp_path, monkeypatch)
    _drive(
        session,
        [
            ("step_start", {"label": "Running code", "id": "call_1", "name": "_exec"}),
            ("step_done", {"label": "Running code", "id": "call_1", "result": "x" * 5000}),
        ],
    )
    row = session._turns[-1]["steps_rows"][0]
    assert len(row["outcome"]) <= 121, len(row["outcome"])
    assert row["outcome"].endswith("…"), row["outcome"][-5:]


# ── step → cell tap-through ──────────────────────────────────────────────────


def test_write_cells_step_row_carries_its_cell_refs(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    step = {
        "name": "write_cells",
        "id": "call_1",
        "result": "Wrote 2 cell(s) into the open notebook. Cells: abc123, def456",
    }
    turn = _drive(
        session,
        [("step_done", {"label": step["name"], "id": step["id"],
                        "result": step["result"], "refs": assistant_view._cell_refs(step)})],
    )
    assert turn["steps_rows"][0]["refs"] == ["abc123", "def456"]


def test_non_write_cells_steps_have_no_refs(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    step = {"name": "_exec", "id": "c", "result": "print(1) => 1"}
    assert assistant_view._cell_refs(step) == []
    turn = _drive(
        session,
        [("step_done", {"label": "_exec", "id": "c", "result": "1",
                        "refs": assistant_view._cell_refs(step)})],
    )
    assert turn["steps_rows"][0]["refs"] == []


def test_a_ref_without_a_marker_parses_to_nothing():
    assert assistant_view._cell_refs(
        {"name": "write_cells", "id": "c", "result": "Wrote 0 cell(s)."}
    ) == []


def test_tapping_a_ref_calls_the_controller_with_the_session(tmp_path, monkeypatch):
    """The chat says which cell; the shell decides how to reach it."""
    controller = FakeController()
    session = _session(tmp_path, monkeypatch, controller=controller)
    _drive(
        session,
        [("step_done", {"label": "write_cells", "id": "c",
                        "result": "x. Cells: zz99",
                        "refs": assistant_view._cell_refs(
                            {"name": "write_cells", "id": "c",
                             "result": "x. Cells: zz99"})})],
    )
    session._reveal_cell("zz99")
    assert controller.revealed == [("sess", "zz99")]


def test_reveal_without_a_controller_is_a_no_op(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    session._reveal_cell("abc")  # must not raise


# ── history ──────────────────────────────────────────────────────────────────


def test_history_goes_through_the_controller(tmp_path, monkeypatch):
    controller = FakeController()
    session = _session(tmp_path, monkeypatch, controller=controller)
    monkeypatch.setattr(
        session._conversations, "refresh_state", lambda: [{"id": "a", "title": "A"}]
    )
    session._show_history()
    assert controller.history_calls == [[{"id": "a", "title": "A"}]]


def test_load_conversation_rejects_a_missing_chat(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    session._turns.append({"role": "user", "text": "mine"})
    assert session.load_conversation("nope") is False
    assert any(t.get("text") == "mine" for t in session._turns), (
        "a failed switch must leave the current chat open"
    )


def test_load_conversation_replaces_the_transcript(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    session._conversations.save_conversation(
        "other", [{"role": "user", "content": "saved"}]
    )
    assert session.load_conversation("other") is True
    assert session.conversation_id == "other"
    assert [t.get("text") for t in session._turns] == ["saved"]



# ── round-trip through the real service ──────────────────────────────────────


def test_a_turn_round_trips_through_conversation_service(tmp_path, monkeypatch):
    """Persisting then reloading must give the conversation back, not just the
    last message."""
    session = _session(tmp_path, monkeypatch)
    _drive(
        session,
        [("text_partial", {"text": "The answer is 42."}),
         ("text_final", {"text": "The answer is 42.", "model": "qwen", "cost": 1})],
    )
    session._persist_history()
    # A fresh session on the same saved id reads the whole pair back.
    fresh = assistant_view.ChatSession(FakePage(), _state(), NS(credits=None), None)
    assert [t.get("text") for t in fresh._turns] == ["hello", "The answer is 42."]


# ── metering integration ─────────────────────────────────────────────────────


def _credit_reads(session):
    """Count how many times the chat asked for a fresh balance."""
    return session._credit_reads


def _watch_credits(session, monkeypatch):
    session._credit_reads = 0

    def _counting_refresh():
        session._credit_reads += 1

    monkeypatch.setattr(session, "_refresh_credits", _counting_refresh)
    return session


def test_a_terminal_event_refreshes_the_credit_chip(tmp_path, monkeypatch):
    """The balance moves on a stop or a failure too, not only on success —
    otherwise the chip shows a stale number until the next successful turn."""
    for event, data in (
        ("text_final", {"text": "done", "model": "m", "cost": 1}),
        ("stopped", {}),
        ("error", {"kind": "unavailable", "message": "down"}),
    ):
        session = _session(tmp_path, monkeypatch)
        _watch_credits(session, monkeypatch)
        _drive(session, [(event, data)])
        assert _credit_reads(session) >= 1, f"{event} must refresh the chip"


def test_a_streaming_event_does_not_refresh_the_chip(tmp_path, monkeypatch):
    """A per-token refresh would read the credit service at the token rate."""
    session = _session(tmp_path, monkeypatch)
    _watch_credits(session, monkeypatch)
    _drive(session, [("text_partial", {"text": "tok"}),
                     ("step_start", {"label": "x", "id": "1"})])
    assert _credit_reads(session) == 0


# ── the approval gate, end to end through the chat ───────────────────────────


def test_the_chats_tools_are_gateable(tmp_path, monkeypatch):
    """The linchpin: ChatSession must hand its ask_confirm to build_tools, or
    the approval card is dead UI and every destructive tool silently refuses."""
    session = _session(tmp_path, monkeypatch)
    from services import ai_tools

    captured = {}

    def _spy(session_name, services, state, ask_confirm=None):
        captured["ask_confirm"] = ask_confirm
        return []

    monkeypatch.setattr(ai_tools, "build_tools", _spy)
    session._build_tools()
    bound = captured["ask_confirm"]
    # A bound method is re-created on each attribute access, so compare its
    # function and receiver rather than object identity.
    assert bound.__func__ is session.ask_confirm.__func__
    assert bound.__self__ is session


def test_the_gate_the_chat_binds_really_asks(tmp_path, monkeypatch):
    """The bound callback is the same one the button answers, so a tool calling
    it blocks on the user rather than falling through to a denial."""
    session = _session(tmp_path, monkeypatch)
    from services import ai_tools

    holder = {}

    def _capture(session_name, services, state, ask_confirm=None):
        holder["fn"] = ask_confirm

        async def restart_kernel() -> str:
            return "restarted" if await ask_confirm("Restart kernel", "vars lost") else "declined"

        restart_kernel.__name__ = "restart_kernel"
        return [restart_kernel]

    monkeypatch.setattr(ai_tools, "build_tools", _capture)
    tools = session._build_tools()

    async def _scenario():
        task = asyncio.ensure_future(tools[0]())
        await asyncio.sleep(0)
        session._confirm_decision("allow")
        return await task

    assert _run_async(_scenario()) == "restarted"


def test_the_chats_real_tools_are_executable(tmp_path, monkeypatch):
    """The chat must build tools that kani can actually register.

    The gate tests above mock build_tools, so without this the chat could hand
    run_turn bare functions — which crashes the first turn — and every other
    test would stay green.
    """
    session = _session(tmp_path, monkeypatch)
    tools = session._build_tools()
    assert tools, "the chat must contribute tools"
    # The exact construction ai_service performs.
    specs = ai_tools.tool_specs(tools)
    assert len(specs) == len(tools)
    functions = kani_backend.build_functions(specs)
    assert len(functions) == len(specs)
    for fn in functions:
        assert isinstance(fn, AIFunction), f"{type(fn).__name__} is not an AIFunction"
    # A bare function would raise here, which is what kani's do_function_call
    # does when it looks a call up in self.functions by name.
    names = {f.name for f in functions}
    assert names == {t.__name__ for t in tools}

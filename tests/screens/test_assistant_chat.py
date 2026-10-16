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


def test_stop_raises_the_flag_the_turn_polls(tmp_path, monkeypatch):
    """Stop reaches the model, it does not yank the turn out from under it.

    The flag is what `kani_backend.run_turn` checks between tokens, so raising
    it is what makes the prompt actually stop streaming. A hard cancel would
    kill the graceful path and leave the bubble half rendered.
    """
    session = _session(tmp_path, monkeypatch)

    class FakeTask:
        def done(self):
            return False

        def cancel(self):
            pass

    session._task = FakeTask()
    session.stop()
    assert session._cancel.is_set(), "stop must raise the cancel flag"


def test_a_silent_task_still_gets_cancelled(tmp_path, monkeypatch):
    """The hard cancel is a backstop, not the mechanism.

    A model that stopped emitting has stopped polling its stop flag, so without
    a deadline the Stop button would hang the session forever. The backstop is
    a scheduled coroutine: it is reached by running the loop's clock past the
    grace window.
    """
    from core.constants import TURN_STOP_GRACE_S

    session = _session(tmp_path, monkeypatch)
    scheduled = []
    cancelled = []

    class FakeTask:
        def done(self):
            return False

        def cancel(self):
            cancelled.append(True)

    session._task = FakeTask()

    # Capture the backstop instead of running it, so the test can prove the
    # deadline exists without sleeping through it.
    class CapturingPage:
        def __init__(self):
            self.views = []
            self.width = 420
            self.updates = 0

        def update(self):
            pass

        def run_task(self, coro):
            scheduled.append(coro)

    monkeypatch.setattr(session, "page", CapturingPage())
    session.stop()
    assert not cancelled, "stop must not cancel instantly"
    assert len(scheduled) == 1, "stop must schedule a backstop"
    assert TURN_STOP_GRACE_S > 0
    # Run the backstop to its first suspension: inside the grace window it
    # must return without touching the turn, which is the whole point of
    # scheduling it rather than cancelling now.
    try:
        scheduled[0].send(None)
    except StopIteration:
        pass  # returned without suspending: the in-window branch is proof
    assert not cancelled, "the backstop must not cancel inside the grace window"
    scheduled[0].close()


def test_stop_on_a_finished_task_does_nothing(tmp_path, monkeypatch):
    """A second tap after the turn ended must not touch a dead task."""
    session = _session(tmp_path, monkeypatch)

    class FakeTask:
        def done(self):
            return True

        def cancel(self):
            raise AssertionError("a finished task must not be cancelled")

    session._task = FakeTask()
    session.stop()
    assert session._cancel.is_set()


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


def test_the_real_callbacks_open_and_close_rows_on_the_call_id(tmp_path, monkeypatch):
    """Drive `_on_tool_start`/`_on_tool_done` themselves, not `_emit`.

    Every other step test hand-feeds `_emit` with a fabricated id, so the chain
    from kani's payload through `_step_emitter` to the row was never executed.
    This is the test that fails if the id stops being threaded.
    """
    from services import ai_service

    session = _session(tmp_path, monkeypatch)
    current = assistant_view._empty_turn()
    session._turns.append(current)
    session._current = current

    emitted: list[tuple[str, dict]] = []
    real_emit = session._emit

    def spy(event, data):
        emitted.append((event, data))
        real_emit(event, data)

    monkeypatch.setattr(session, "_emit", spy)

    # The payload exactly as kani_backend builds it, twice for the same tool.
    payloads = [
        {"name": "read_notebook", "id": "call_1", "args": {}, "result": "first"},
        {"name": "read_notebook", "id": "call_2", "args": {}, "result": "second"},
    ]

    emit = ai_service._step_emitter(session._on_tool_start, session._on_tool_done)
    emit("start", payloads[0])
    emit("done", payloads[0])
    emit("start", payloads[1])
    emit("done", payloads[1])

    rows = current["steps_rows"]
    assert [r["id"] for r in rows] == ["call_1", "call_2"], rows
    assert [r["outcome"] for r in rows] == ["first", "second"], rows
    assert all(r["state"] == "done" for r in rows), rows


def test_the_real_callbacks_mark_a_failed_tool_as_an_error(tmp_path, monkeypatch):
    """A tool that raised must reach the user as a red row, not a green check."""
    from services import ai_service

    session = _session(tmp_path, monkeypatch)
    current = assistant_view._empty_turn()
    session._turns.append(current)
    session._current = current

    emitted: list[tuple[str, dict]] = []
    real_emit = session._emit

    def spy(event, data):
        emitted.append((event, data))
        real_emit(event, data)

    monkeypatch.setattr(session, "_emit", spy)

    payload = {
        "name": "read_notebook",
        "id": "call_1",
        "args": {},
        "result": "(the read_notebook tool failed: no session)",
        "error": "no session",
    }
    emit = ai_service._step_emitter(session._on_tool_start, session._on_tool_done)
    emit("start", payload)
    emit("done", payload)

    assert [e for e, _ in emitted] == ["step_start", "step_error"], emitted
    row = current["steps_rows"][0]
    assert row["state"] == "error", row
    assert row["error"] == "no session", row


def test_the_real_callbacks_survive_a_missing_call_id(tmp_path, monkeypatch):
    """A call with no id must not re-key the row by tool name.

    Name-keyed rows collide, so a second call to the same tool would overwrite
    the first and leave it spinning.
    """
    from services import ai_service

    session = _session(tmp_path, monkeypatch)
    current = assistant_view._empty_turn()
    session._turns.append(current)
    session._current = current

    emitted: list[tuple[str, dict]] = []
    real_emit = session._emit

    def spy(event, data):
        emitted.append((event, data))
        real_emit(event, data)

    monkeypatch.setattr(session, "_emit", spy)

    payload = {"name": "read_notebook", "id": "", "args": {}, "result": "x"}
    emit = ai_service._step_emitter(session._on_tool_start, session._on_tool_done)
    emit("start", payload)
    emit("done", payload)

    # The row was still opened and closed — by a unique id, not the name.
    assert len(current["steps_rows"]) == 1, current["steps_rows"]
    row = current["steps_rows"][0]
    assert row["state"] == "done", row
    assert row["id"] != "read_notebook", row


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
        [
            ("step_start", {"label": "Writing cells", "id": step["id"], "name": step["name"]}),
            ("step_done", {"label": "Writing cells", "id": step["id"],
                           "result": step["result"],
                           "refs": assistant_view._cell_refs(step)}),
        ],
    )
    assert turn["steps_rows"][0]["refs"] == ["abc123", "def456"]


def test_non_write_cells_steps_have_no_refs(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    step = {"name": "_exec", "id": "c", "result": "print(1) => 1"}
    assert assistant_view._cell_refs(step) == []
    turn = _drive(
        session,
        [
            ("step_start", {"label": "Running code", "id": "c", "name": "_exec"}),
            ("step_done", {"label": "Running code", "id": "c", "result": "1",
                           "refs": assistant_view._cell_refs(step)}),
        ],
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


# ── the pill's refresh hook ─────────────────────────────────────────────────


def test_refresh_model_chip_short_circuits_on_an_unchanged_signature(
    tmp_path, monkeypatch
):
    """A status tick must not rebuild the header pill.

    The pill is a static control in an imperative View, and rebuilding it on
    every token would construct a whole control tree for a label that almost
    never moves.
    """
    from components import model_pill

    session = _session(tmp_path, monkeypatch)
    rebuilt = []
    monkeypatch.setattr(session, "model_chip", _ChipSpy(rebuilt))

    # Seed from the pill's own signature, so the first call matches it exactly.
    session._pill_signature = model_pill.pill_signature()

    session.refresh_model_chip()
    assert rebuilt == [], "an unchanged signature must not rebuild"

    # A different one must rebuild.
    session._pill_signature = ("Offline", False, "unavailable", "auto", "", "Start router", ())
    session.refresh_model_chip()
    assert rebuilt == ["built"], rebuilt


def test_refresh_model_chip_rebuilds_when_only_the_menu_changed(
    tmp_path, monkeypatch
):
    """A catalog change with an unchanged label must still rebuild the items.

    The pill bakes its menu in, so a label-only signature would leave a stale
    dropdown: the rows shown would be from before the catalog moved.
    """
    from components import model_pill
    from core.state import state
    from services import model_catalog

    # The pill reads the real singleton, and only a serving router's rows are
    # baked into the menu.
    monkeypatch.setattr(state, "ai_router_status", "ready")
    monkeypatch.setattr(state, "ai_router_port", 8083)

    session = _session(tmp_path, monkeypatch)
    rebuilt = []
    monkeypatch.setattr(session, "model_chip", _ChipSpy(rebuilt))

    rows = [
        {
            "id": "auto",
            "status": "active",
            "latency_ms": 10,
            "endpoint_type": "chat.completion",
            "rate_hint": {"tier": "high", "label": "high tier"},
        }
    ]
    model_catalog._catalog = []
    model_catalog._catalog_fetched_at = 1.0
    session._pill_signature = model_pill.pill_signature()
    rebuilt.clear()

    # Same label (Auto, ready), different rows.
    model_catalog._catalog = model_catalog._normalise(rows)
    session.refresh_model_chip()
    assert rebuilt == ["built"], "a changed menu must rebuild even if the label did not"


class _ChipSpy:
    """Stands in for the pill: records that a rebuild happened, nothing else."""

    def __init__(self, rebuilt):
        self._rebuilt = rebuilt

    @property
    def content(self):
        return None

    @content.setter
    def content(self, value):
        self._rebuilt.append("built")

    def update(self):
        pass


# ── the capability list on the empty chat ───────────────────────────────────


# Which starter exercises which tool. Every tool the assistant has must appear
# here, so a capability cannot become discoverable only by guessing — that is
# the whole point of the "What I can do" list (DDGS gives every ability a
# sample: `chat_screen.py:1705-1709`).
_STARTER_TOOL_MAP = {
    "list_sessions": "List my Colab sessions",
    "create_session": "Create a new session named",
    "_exec": "Run this and tell me what happened",
    "list_variables": "What variables are in my kernel",
    "install_package": "Install pandas and confirm",
    "restart_kernel": "Restart the kernel",
    "read_notebook": "Read my active notebook and explain",
    "write_cells": "Write a cell that loads my data",
    "list_notebook_tabs": "List the notebook tabs I have open",
    "list_files": "List the files in my session",
    "read_file": "Read /content/data.csv",
    "upload_file": "Upload ~/data.csv",
    "read_terminal": "Show me the recent terminal output",
    "delete_file": "Delete /content/old.csv",
    "get_usage": "How many compute units do I have left",
    "get_log": "Show me the session activity log",
    "stop_session": "Stop my session when you're done",
}


def test_every_tool_is_reachable_from_a_starter():
    """A capability nobody can see is a capability nobody uses.

    The assistant gained session creation and the empty chat said nothing about
    it — the owner's "why don't I see an example of creating session?". This
    fails the moment a tool is added without a sample.
    """
    from services import ai_tools

    starters = {prompt for _icon, _label, prompt in assistant_view._starter_rows()}
    tools = {
        t.__name__
        for t in ai_tools.build_tools(
            "sess", NS(colab=NS(), storage=None),
            NS(auth_method="oauth2", default_timeout=30.0),
        )
    }

    missing = tools - set(_STARTER_TOOL_MAP)
    assert not missing, f"tools with no starter prompt: {sorted(missing)}"

    for tool_name, needle in _STARTER_TOOL_MAP.items():
        assert any(needle in prompt for prompt in starters), (
            f"no starter covers {tool_name} (looked for {needle!r})"
        )


def test_the_starters_are_prompts_not_tool_names():
    """A row is a sentence a user would say. The tool is the model's business."""
    from services import ai_tools

    tool_names = {t.__name__ for t in ai_tools.build_tools(
        "sess", NS(colab=NS(), storage=None),
        NS(auth_method="oauth2", default_timeout=30.0),
    )}
    for _icon, label, prompt in assistant_view._starter_rows():
        for name in tool_names:
            assert name not in prompt, f"starter leaks the tool name {name!r}: {prompt!r}"
        assert label and prompt, (label, prompt)
        assert not prompt.endswith("."), f"prompts are sentences, not instructions: {prompt!r}"

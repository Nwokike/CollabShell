"""End-to-end check: a tool's rich outputs must survive every hop and reach
the step row the chat renders (the user saw empty output + copy only)."""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from screens import assistant_view
from services import (
    ai_service,
    ai_tools,
)


class FakePage:
    def __init__(self):
        self.views = []
        self.width = 420

    def update(self):
        pass

    def run_task(self, coro):
        try:
            coro.close()
        except Exception:
            pass


def _state(**kw):
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


def _session(tmp_path, monkeypatch):
    from services import conversation_service as conversations

    monkeypatch.setattr(conversations, "_tombstones", {})
    monkeypatch.setattr(conversations, "conversations_dir", lambda: tmp_path)
    monkeypatch.setattr(conversations, "ensure_active", lambda: "chat1")
    session = assistant_view.ChatSession(FakePage(), _state(), NS(credits=None))
    session._turns.clear()
    session._turns.append({"role": "user", "text": "hello"})
    current = assistant_view._empty_turn()
    session._turns.append(current)
    session._current = current
    return session, current


def _outputs_payload():
    return {
        "name": "_exec",
        "id": "call_1",
        "args": {"code": "print('hi')"},
        "result": json.dumps(
            {
                "text": "hi",
                "outputs": [{"type": "stream", "text": "hi\n", "name": "stdout"}],
            }
        ),
        "error": None,
        "outputs": [{"type": "stream", "text": "hi\n", "name": "stdout"}],
    }


def test_tool_done_puts_outputs_on_the_row(tmp_path, monkeypatch):
    """_step_emitter -> _on_tool_done -> _emit must land outputs on the row."""
    session, turn = _session(tmp_path, monkeypatch)

    payload = _outputs_payload()
    emit = ai_service._step_emitter(session._on_tool_start, session._on_tool_done)
    emit("start", payload)
    emit("done", payload)

    row = turn["steps_rows"][0]
    assert row["state"] == "done"
    assert row["outputs"], "outputs were dropped before the row"
    assert row["outputs"][0]["type"] == "stream"


def test_result_envelope_parsed_when_outputs_missing(tmp_path, monkeypatch):
    """If the payload carried no outputs key, the JSON envelope in the result
    string must still be parsed (belt and braces for older payloads)."""
    session, turn = _session(tmp_path, monkeypatch)

    payload = _outputs_payload()
    payload.pop("outputs")
    emit = ai_service._step_emitter(session._on_tool_start, session._on_tool_done)
    emit("start", payload)
    emit("done", payload)

    row = turn["steps_rows"][0]
    assert row["outputs"], "the JSON envelope was not parsed"


def _walk_texts(control, out: list):
    """Collect every Text value / span text / tooltip in a flet control tree."""
    if control is None:
        return
    value = getattr(control, "value", None)
    if isinstance(value, str):
        out.append(value)
    text_attr = getattr(control, "text", None)
    if isinstance(text_attr, str):
        out.append(text_attr)
    for span in getattr(control, "spans", None) or []:
        span_text = getattr(span, "text", None) or getattr(
            getattr(span, "style", None), "text", None
        )
        if isinstance(span_text, str):
            out.append(span_text)
    tooltip = getattr(control, "tooltip", None)
    if isinstance(tooltip, str):
        out.append(tooltip)
    for attr in ("content", "controls", "actions", "leading", "title"):
        child = getattr(control, attr, None)
        if child is None:
            continue
        if isinstance(child, str):
            out.append(child)
        elif isinstance(child, (list, tuple)):
            for item in child:
                _walk_texts(item, out)
        else:
            _walk_texts(child, out)


def test_exec_tool_returns_the_outputs_envelope():
    """The real _exec tool must return {"text","outputs"} JSON, with the
    streamed on_output dicts preserved for the step row."""

    async def fake_exec_code(code, session_name, **kwargs):
        on_output = kwargs.get("on_output")
        if on_output:
            for out in (
                {"type": "stream", "text": "line one\n", "name": "stdout"},
                {"type": "stream", "text": "line two\n", "name": "stdout"},
            ):
                on_output(out)
        return {"ok": True}

    state = NS(
        active_session_name="s1",
        auth_method="oauth2",
        default_timeout=30.0,
        ai_model="",
        ai_thinking="auto",
    )
    services = NS(colab=NS(exec_code=fake_exec_code))
    tools = ai_tools.build_tools("s1", services, state)
    exec_tool = next(t for t in tools if getattr(t, "__name__", "") == "_exec")

    result = asyncio.run(exec_tool(code="print('hi')"))
    parsed = json.loads(result)
    assert parsed["text"].strip() == "line one\nline two"
    assert len(parsed["outputs"]) == 2
    assert parsed["outputs"][0]["type"] == "stream"


def test_kani_wrapper_splits_the_envelope():
    """kani_backend.tool_specs must split the envelope into result + outputs."""
    from services import kani_backend

    async def run(code, on_tool_output=None):
        return json.dumps(
            {"text": "done", "outputs": [{"type": "stream", "text": "x\n"}]}
        )

    spec = kani_backend.ToolSpec(name="_exec", desc="d", parameters={}, run=run)
    events = []
    wrapped = kani_backend.tool_specs([spec], on_step=lambda e, p: events.append((e, p)))[
        0
    ]
    text = asyncio.run(wrapped.run(code="x"))
    assert text.startswith("{")  # kani still gets the full envelope
    done = [p for e, p in events if e == "done"][-1]
    assert done["result"] == "done"
    assert done["outputs"] == [{"type": "stream", "text": "x\n"}]


def test_render_shows_the_outputs_for_a_done_row(tmp_path, monkeypatch):
    """_render_assistant must build the rich output block for a done row."""
    session, turn = _session(tmp_path, monkeypatch)
    payload = _outputs_payload()
    emit = ai_service._step_emitter(session._on_tool_start, session._on_tool_done)
    emit("start", payload)
    emit("done", payload)

    control = session._render_assistant(turn)
    texts: list[str] = []
    _walk_texts(control, texts)
    joined = " ".join(texts)
    assert "hi" in joined, "the tool output text did not render"
    assert any("Open Notebook" in t or "Open Terminal" in t for t in texts), (
        "no open-in action on the step row"
    )
    assert "Copy Output" in joined, "the notebook's own copy button is missing"


def test_follow_up_pills_render_after_a_done_turn(tmp_path, monkeypatch):
    """DDGS's related-question pills: a finished turn offers contextual next
    moves, tapping one sends it as the next message."""
    session, turn = _session(tmp_path, monkeypatch)
    payload = _outputs_payload()
    emit = ai_service._step_emitter(session._on_tool_start, session._on_tool_done)
    emit("start", payload)
    emit("done", payload)
    turn["partial"] = False  # pills render only for finished turns

    suggestions = session._turn_suggestions(turn)
    assert suggestions, "no follow-up suggestions for a tool turn"
    assert any("Explain that output" in s for s in suggestions)
    assert len(suggestions) <= 3

    control = session._render_assistant(turn)
    texts: list[str] = []
    _walk_texts(control, texts)
    assert any(s in texts for s in suggestions), "pills did not render"

    # A turn still streaming must not show pills yet.
    turn["partial"] = True
    assert session._turn_suggestions(turn) == []
    turn["partial"] = False


def test_suggestions_contextualize_on_errors_and_tools(tmp_path, monkeypatch):
    session, turn = _session(tmp_path, monkeypatch)
    turn["partial"] = False
    turn["steps_rows"].append(
        {
            "id": "call_2",
            "label": "Ran code",
            "name": "_exec",
            "state": "error",
            "outcome": "",
            "error": "boom",
            "refs": [],
            "live_output": "",
            "outputs": [],
        }
    )
    suggestions = session._turn_suggestions(turn)
    assert any("Fix the error" in s for s in suggestions), suggestions
    assert any("Explain that output" in s for s in suggestions)

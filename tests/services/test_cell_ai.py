"""In-cell AI service tests: prompts, code extraction, and the gates.

The important properties:

* **The actions are tool-free and one step.** A full notebook digest rides in
  the prompt, which is what keeps an in-cell "explain this" to one credit
  instead of a tool loop.
* **Never writes on failure.** Every failure path raises before any cell is
  inserted, so a failed action cannot leave a half-written cell in the
  notebook.
* **Code answers come out of the fence.** Models hedge even when told "only a
  code block", and inserting the prose would put a broken cell in the
  notebook.
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace as NS

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from services import cell_ai


class FakeCell:
    def __init__(self, source="", cell_type="code", outputs=None):
        self.source = source
        self.type = cell_type
        self.outputs = outputs or []
        self.id = "c1"
        self.origin = "user"


class FakeOut:
    def __init__(self, text=""):
        self.text = text


def _state(**kw):
    base = {"ai_model": "auto"}
    base.update(kw)
    return NS(**base)


def _patch_turn(monkeypatch, result):
    """Replace the metered turn with a canned result."""
    from services import ai_credits

    captured = {}

    async def fake(**kwargs):
        captured.update(kwargs)
        return result

    monkeypatch.setattr(ai_credits, "run_metered_turn", fake)
    return captured


# ── the gates ────────────────────────────────────────────────────────────────


def test_no_credit_service_raises_disabled_and_never_calls_the_model(monkeypatch):
    """The one remaining refusal: credits unavailable in this build.

    There used to be a second one — the assistant "off" switch — but that
    switch never worked (`on_change` passed a coroutine through a lambda, so
    flet dropped it) and it defaulted to off, so the assistant was effectively
    unusable. It is gone; the assistant always runs, and the only thing that
    can stop a turn is no credits.
    """
    called = _patch_turn(monkeypatch, {"ok": True, "text": "x"})
    try:
        asyncio.run(
            cell_ai.run_cell_action(
                action="explain",
                state=_state(),
                credits=None,
                services=NS(),
                source="x=1",
                notebook_cells=[],
            )
        )
        raise AssertionError("no credits must not reach the model")
    except cell_ai.CellAIDisabled:
        pass
    assert not called, "a disabled gate must not run a turn"


def test_no_credit_service_raises_disabled(monkeypatch):
    _patch_turn(monkeypatch, {"ok": True, "text": "x"})
    try:
        asyncio.run(
            cell_ai.run_cell_action(
                action="explain",
                state=_state(),
                credits=None,
                services=NS(),
                source="x=1",
                notebook_cells=[],
            )
        )
        raise AssertionError("no credit service must not reach the model")
    except cell_ai.CellAIDisabled:
        pass


def test_zero_balance_raises_out_of_credits(monkeypatch):
    _patch_turn(
        monkeypatch,
        {"ok": False, "out_of_credits": True, "error": "Out of assistant credits."},
    )
    try:
        asyncio.run(
            cell_ai.run_cell_action(
                action="explain",
                state=_state(),
                credits=object(),
                services=NS(),
                source="x=1",
                notebook_cells=[],
            )
        )
        raise AssertionError("a zero balance must block, not answer")
    except cell_ai.OutOfCredits:
        pass


def test_unavailable_propagates_for_the_caller_to_surface(monkeypatch):
    from services import ai_service

    _patch_turn(monkeypatch, {"ok": False, "error": "router down"})
    try:
        asyncio.run(
            cell_ai.run_cell_action(
                action="explain",
                state=_state(),
                credits=object(),
                services=NS(),
                source="x=1",
                notebook_cells=[],
            )
        )
        raise AssertionError("an unavailable router must surface")
    except ai_service.AIUnavailable:
        pass


# ── tool-free, one step ──────────────────────────────────────────────────────


def test_the_action_sends_no_tools(monkeypatch):
    """No tools keeps an in-cell action at one credit and one round trip."""
    captured = _patch_turn(monkeypatch, {"ok": True, "text": "hi"})
    asyncio.run(
        cell_ai.run_cell_action(
            action="explain",
            state=_state(),
            credits=object(),
            services=NS(),
            source="x=1",
            notebook_cells=[FakeCell("import os")],
        )
    )
    assert captured["tools"] == []


def test_the_prompt_carries_the_notebook_digest(monkeypatch):
    captured = _patch_turn(monkeypatch, {"ok": True, "text": "hi"})
    asyncio.run(
        cell_ai.run_cell_action(
            action="explain",
            state=_state(),
            credits=object(),
            services=NS(),
            source="plt.plot(x)",
            notebook_cells=[FakeCell("import pandas"), FakeCell("x = 1")],
        )
    )
    content = captured["messages"][0]["content"]
    assert "import pandas" in content, "the model needs the rest of the notebook"
    assert "cell 0" in content and "cell 1" in content, (
        "cells are numbered so the model can cite one"
    )
    assert "plt.plot(x)" in content, "the cell under the cursor must be marked"


def test_the_prompt_carries_the_error_for_fix(monkeypatch):
    captured = _patch_turn(monkeypatch, {"ok": True, "text": "hi"})
    failing = FakeCell("1/0", outputs=[FakeOut("Traceback... ZeroDivisionError")])
    asyncio.run(
        cell_ai.run_cell_action(
            action="fix",
            state=_state(),
            credits=object(),
            services=NS(),
            source="1/0",
            notebook_cells=[failing],
            output=cell_ai._output_digest(failing),
        )
    )
    content = captured["messages"][0]["content"]
    assert "ZeroDivisionError" in content, "Fix needs the error to diagnose"
    assert "ONLY a Python code block" in content, "Fix must ask for code only"


def test_the_digest_is_bounded(monkeypatch):
    """A long notebook must not balloon the prompt past the cap."""
    captured = _patch_turn(monkeypatch, {"ok": True, "text": "hi"})
    big = [FakeCell("x = 1\n" * 200) for _ in range(20)]
    asyncio.run(
        cell_ai.run_cell_action(
            action="explain",
            state=_state(),
            credits=object(),
            services=NS(),
            source="x",
            notebook_cells=big,
        )
    )
    content = captured["messages"][0]["content"]
    assert "truncated" in content, "the digest must announce what it dropped"
    assert len(content) < cell_ai._MAX_NOTEBOOK_CHARS + 2000


# ── code extraction ──────────────────────────────────────────────────────────


def test_extract_code_pulls_the_first_fenced_block():
    assert cell_ai.extract_code(
        "Sure!\n```python\ndef f():\n    return 1\n```\nHope that helps."
    ) == ("def f():\n    return 1")


def test_extract_code_handles_a_missing_close_fence():
    assert cell_ai.extract_code("```python\nx = 1\ny = 2") == "x = 1\ny = 2"


def test_extract_code_falls_back_to_bare_code():
    assert cell_ai.extract_code("x = 1\ny = 2") == "x = 1\ny = 2"


def test_extract_code_returns_empty_for_nothing():
    assert cell_ai.extract_code("") == ""
    assert cell_ai.extract_code("   ") == ""
    assert cell_ai.extract_code("```python\n```") == ""


def test_extract_code_strips_a_language_tag_from_the_first_line():
    assert cell_ai.extract_code("```py\nprint(1)\n```") == "print(1)"


# ── error detection (Fix affordance) ────────────────────────────────────────


def test_looks_like_error_spots_tracebacks():
    assert cell_ai.looks_like_error(
        "Traceback (most recent call last):\nValueError: bad"
    )
    assert cell_ai.looks_like_error("SyntaxError: invalid syntax")
    assert cell_ai.looks_like_error("[Errno 2] No such file")
    assert cell_ai.looks_like_error("Exception in cell")


def test_looks_like_error_ignores_plain_output():
    assert not cell_ai.looks_like_error("hello world")
    assert not cell_ai.looks_like_error("42")
    assert not cell_ai.looks_like_error("")


# ── the shared one-shot engine (ai_quick) ───────────────────────────────────


def test_ai_quick_ask_refuses_without_credits(monkeypatch):
    """The engine is the one place the refusal lives, so every caller inherits
    it — a caller that forgets its own check still cannot spend credits."""
    from services import ai_quick

    called = []

    async def fake(**kwargs):
        called.append(kwargs)
        return {"ok": True, "text": "x"}

    monkeypatch.setattr("services.ai_credits.run_metered_turn", fake)

    try:
        asyncio.run(
            ai_quick.ask(
                action="explain",
                state=_state(),
                credits=None,
                services=NS(),
                prompt="hi",
            )
        )
        raise AssertionError("no credits must not reach the model")
    except ai_quick.CellAIDisabled:
        pass
    assert not called


def test_ai_quick_ask_sends_no_tools_and_one_message(monkeypatch):
    from services import ai_credits, ai_quick

    captured = {}

    async def fake(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "text": "answer"}

    monkeypatch.setattr(ai_credits, "run_metered_turn", fake)
    out = asyncio.run(
        ai_quick.ask(
            action="explain",
            state=_state(),
            credits=object(),
            services=NS(),
            prompt="the prompt",
        )
    )
    assert out == "answer"
    assert captured["tools"] == []
    assert [m["role"] for m in captured["messages"]] == ["user"]


def test_ai_quick_gates_are_the_same_classes_as_cell_ai_uses():
    """cell_ai re-exports them; if these drift apart, every `except` at a call
    site silently stops catching."""
    from services import ai_quick

    assert cell_ai.OutOfCredits is ai_quick.OutOfCredits
    assert cell_ai.CellAIDisabled is ai_quick.CellAIDisabled


# ── hardware suggestion (4C) ───────────────────────────────────────────────


def test_hardware_prompt_lists_only_selectable_options(monkeypatch):
    """A suggestion naming a shape the picker cannot select is useless — and
    worse, it looks like the app lied."""
    captured = {}
    monkeypatch.setattr(
        "services.ai_credits.run_metered_turn", _recording_turn(captured)
    )
    from services import ai_quick

    monkeypatch.setattr(ai_quick, "ask", _recording_turn(captured))
    asyncio.run(
        cell_ai.run_cell_action(
            action="hardware",
            state=_state(),
            credits=object(),
            services=NS(),
            source="",
            notebook_cells=[FakeCell("import torch; torch.cuda.is_available()")],
        )
    )
    prompt = captured["prompt"]
    assert "Available runtime shapes:" in prompt
    # Every option the app can pick appears in the prompt.
    for option in cell_ai.HARDWARE_OPTIONS:
        assert option.split(" (")[0] in prompt, option


def test_hardware_asks_for_a_verdict_first_and_a_markdown_explanation():
    """The recommendation must be separable from the reasoning, so the UI can
    show one line and let the rest be detail."""
    body = cell_ai._model_messages("hardware", source="", digest="x", output="")
    content = body[0]["content"]
    assert "single recommendation on its own line first" in content
    assert "markdown" in content.lower()


def test_hardware_does_not_need_a_cell():
    """It is notebook-scoped: an empty source is legitimate."""
    body = cell_ai._model_messages(
        "hardware", source="", digest="import numpy", output="", cell_type="code"
    )
    assert "import numpy" in body[0]["content"]


def _recording_turn(captured):
    async def fake(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "text": "T4 — plenty for this."}

    return fake

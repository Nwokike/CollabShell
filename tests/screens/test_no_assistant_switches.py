"""There is no assistant switch — the assistant works out of the box.

The owner: *"what do you mean assistant mode? It is on by default. It should
not be an option, so remove it."* and the same for *"Include app guide in
prompts."*

Two bugs this closes, both found while working on it:

1. `on_change=lambda e: _save_mode(e.control.value)` passed an `async def`
   through a lambda, so flet — which only awaits a *coroutine function*
   (`base_control.py:514-555`) — created the coroutine and dropped it on the
   floor. The owner's log shows the `RuntimeWarning: coroutine ...
   never awaited`. Neither switch had ever saved anything, so the assistant
   could not be turned on from the UI at all.
2. The flag defaulted to off, so the in-cell AI, the file and terminal explain
   actions and the Home credit pill were all hidden until a switch that did
   nothing was flipped.
"""

from __future__ import annotations

import inspect
import pathlib
import re
import sys

_SRC = pathlib.Path(__file__).resolve().parent.parent.parent / "src"
_SRC_ROOT = _SRC.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# `\b` because `state.ai_model` contains the substring `state.ai_mode`.
_FLAG = re.compile(r"\b(ai_mode|ai_help)\b")


def test_the_assistant_switches_are_gone():
    for needle in (
        '"Assistant mode",',  # the row title, comma-anchored (a bare substring
        # would match "Assistant model", which is a real row)
        "Include app guide in prompts",
        "mode_switch",
        "help_switch",
        "_save_mode",
        "_save_help",
    ):
        text = (_SRC / "screens/settings/ai_section.py").read_text(encoding="utf-8")
        assert needle not in text, f"the Settings assistant section still has {needle!r}"


def test_no_source_file_names_the_removed_flags():
    """No reader, writer or declaration of either flag anywhere in src/."""
    for src in (_SRC_ROOT / "src").rglob("*.py"):
        found = _FLAG.findall(src.read_text(encoding="utf-8"))
        assert not found, f"{src.name} still names {found}"


def test_the_ai_service_no_longer_refuses_when_assistant_is_off():
    """The gate that raised "Assistant is off" is gone."""
    text = (_SRC / "services/ai_quick.py").read_text(encoding="utf-8")
    assert "Assistant is off" not in text
    # The credits-unavailable refusal stays — that one is a real condition.
    assert "unavailable in this build" in text


def test_the_app_guide_is_always_injected():
    """Both system-prompt paths return the SKILL.md unconditionally."""
    from services import ai_quick

    source = inspect.getsource(ai_quick.system_for)
    assert "if not getattr" not in source, "system_for still has a conditional"
    assert _FLAG.findall(source) == [], "system_for still names the flag"

    text = (_SRC / "screens/assistant_view.py").read_text(encoding="utf-8")
    assert _FLAG.findall(text) == [], "the chat view still names the flag"


def test_no_dead_notice_tells_the_user_to_turn_the_assistant_on():
    for rel in (
        "src/screens/files/__init__.py",
        "src/screens/session/notebook_view.py",
        "src/screens/session/terminal_panel.py",
    ):
        text = (_SRC_ROOT / rel).read_text(encoding="utf-8")
        assert "Turn the Assistant on" not in text, f"{rel} still has the dead notice"


def test_the_state_no_longer_declares_the_flags():
    text = (_SRC / "core/state.py").read_text(encoding="utf-8")
    assert not _FLAG.search(text), "the flags are still declared on AppState"
    # The model choice stays — that one is a real setting.
    assert "ai_model" in text

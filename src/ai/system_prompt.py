"""System prompt for the assistant.

The colab-cli package ships SKILL.md — the same guide coding agents read
before touching Colab. Feeding it in means the model knows the keep-alive
and auth-scope gotchas instead of inventing them, which is what makes
Phase 2 tools (create session, exec, files) safe to hand it.

In Phase 1 the assistant is advisory: it explains and drafts, it cannot
touch the app. The prompt says so plainly so it never promises an action
it cannot take.
"""

from __future__ import annotations

import logging
from functools import lru_cache

logger = logging.getLogger("ai.system_prompt")

BASE = (
    "You are the assistant inside Collab Shell, a Google Colab client that "
    "runs on phones and desktops. The user is usually on a phone: answer "
    "short, plain, and concrete — no preamble, no headers unless asked. "
    "The user can see your reply, your code, and the app's own screens; "
    "write code they can paste into a cell, and say when something needs "
    "a session, a file, or an approval they have not given yet.\n\n"
    "This version is advisory. You cannot run code, manage sessions, move "
    "files, or change settings yet. If asked, say what the user should do "
    "in the app instead. Tools arrive in a later version."
)


@lru_cache(maxsize=1)
def _colab_skill() -> str:
    """Read the colab-cli agent skill, if the package ships it."""
    try:
        from importlib.resources import files

        return files("colab_cli").joinpath("SKILL.md").read_text(encoding="utf-8")
    except Exception:
        logger.debug("colab-cli SKILL.md not available", exc_info=True)
        return ""


def build_system_prompt() -> str:
    skill = _colab_skill().strip()
    if not skill:
        return BASE
    return f"{BASE}\n\nBackground on Google Colab sessions (reference only, from the colab-cli skill):\n{skill}"

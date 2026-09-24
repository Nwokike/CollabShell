"""System prompt for the assistant.

The colab-cli package ships SKILL.md — the same guide coding agents read
before touching Colab. Feeding it in means the model knows the keep-alive
and auth-scope gotchas instead of inventing them, which is what makes
Phase 2 tools (create session, exec, files) safe to hand it.

In Phase 1 the assistant was advisory: it explained and drafted but
could not touch the app. With tools enabled it may act, but every
state-changing call still stops for the user's approval, so the prompt
spells that out instead of letting the model guess.
"""

from __future__ import annotations

import logging
from functools import lru_cache

logger = logging.getLogger("ai.system_prompt")

BASE = (
    "You are the Assistant inside Collab Shell, a Google Colab client that "
    "runs on phones and desktops. The user is usually on a phone: answer "
    "short, plain, and concrete — no preamble, no headers unless asked. "
    "The user can see your reply, your code, and the app's own screens; "
    "write code they can paste into a cell, and say when something needs "
    "a session, a file, or an approval they have not given yet."
)

TOOLS_BASE = (
    "\n\nYou can act on the user's Colab account with tools: list their "
    "sessions, list files on a VM, start or stop a session, run code, "
    "install packages, mount Drive, and authenticate GCP. Actions that "
    "change something always ask the user first — say what you want to do "
    "in plain words, call the tool, and if the user declines, adapt or ask "
    "instead of retrying. After a tool returns, use the real result; never "
    "invent session names, file listings, or outputs. If a tool fails, "
    "explain why once, then try a different approach or ask the user."
)

NOTEBOOK_BASE = (
    "\n\nThe user has a notebook open. Its cells are numbered from 1 and "
    "the screen shows the same numbers. You can read the notebook with "
    "list_cells and read_cell, and change it with set_cell_source, "
    "insert_cell, and run_cell — each of those asks the user first, and "
    "the cell changes on screen the moment they allow it. Use cell numbers "
    "exactly as the user gave them. When you rewrite a cell, put the whole "
    "replacement in the tool call; do not paste code in chat as if it had "
    "been written. When the user asks for code, write it into the notebook "
    "rather than only describing it, unless they asked you not to."
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


def build_system_prompt(
    tools_available: bool = False, notebook_available: bool = False
) -> str:
    skill = _colab_skill().strip()
    parts = [BASE + (TOOLS_BASE if tools_available else "")]
    if notebook_available:
        parts.append(NOTEBOOK_BASE)
    if skill:
        parts.append(
            "Background on Google Colab sessions (reference only, from the "
            f"colab-cli skill):\n{skill}"
        )
    return "\n\n".join(parts)

"""The per-cell Assistant sheet.

Tapping the chat icon on a cell opens a quick-ask sheet with the cell's own
code, its error if it has one, and the three questions people actually
ask about a cell. Each one seeds the composer with the cell attached, so
the user never has to describe or paste their code.

Kept Flet-free at the top so the wording — which is what the model
actually sees — is testable on its own.
"""

from __future__ import annotations

import flet as ft

from ai.quick_sheet import open_quick_sheet
from core.theme import AppColors

# The error goes into the question, so cap it: a runaway traceback should
# not crowd out the cell it belongs to.
_ERROR_CHARS = 600


def build_question(kind: str, number: int, source: str, error: str = "") -> str:
    """The prompt for one of the three quick actions.

    Always the same shape: what the user wants, then the cell, 1-based —
    the same numbering the notebook tools use.
    """
    code = (source or "").strip()
    block = (
        f"Cell {number}:\n\n```python\n{code}\n```"
        if code
        else f"Cell {number} (empty)"
    )
    if kind == "explain":
        return (
            "Explain this cell in a few short lines — what it does, then "
            "anything the user should watch out for.\n\n" + block
        )
    if kind == "fix":
        detail = (error or "").strip()
        head = (
            f"This cell failed:\n\n```\n{detail[:_ERROR_CHARS]}\n```\n\n"
            "Rewrite the cell so it works."
        )
        return head + "\n\n" + block
    return "Question about this cell:\n\n" + block + "\n\nMy question: "


def open_cell_sheet(page, ai, number: int, source: str, error: str = "") -> None:
    """Show the quick-ask sheet for one cell, then the Assistant."""
    if ai is None:
        return

    actions = [
        (
            ft.Icons.LIGHTBULB_ROUNDED,
            "Explain this cell",
            "What it does, and what to watch for",
            build_question("explain", number, source),
            AppColors.WARNING,
        )
    ]
    if (error or "").strip():
        actions.append(
            (
                ft.Icons.AUTO_FIX_HIGH_ROUNDED,
                "Fix this error",
                "Rewrite the cell so it runs",
                build_question("fix", number, source, error),
                AppColors.ERROR,
            )
        )
    actions.append(
        (
            ft.Icons.CHAT_ROUNDED,
            "Ask about it",
            "Type your own question about this cell",
            build_question("ask", number, source),
            ft.Colors.PRIMARY,
        )
    )

    open_quick_sheet(
        page,
        ai,
        title=f"Cell {number}",
        preview=source,
        error=error,
        actions=actions,
    )


__all__ = ["build_question", "open_cell_sheet"]

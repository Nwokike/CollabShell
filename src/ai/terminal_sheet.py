"""The terminal's quick-ask sheet.

Same shape as the cell sheet: a peek at what the terminal last printed,
and the questions that make sense there. The questions deliberately do
not paste the output in — the Assistant reads the live terminal with
`read_terminal`, which is the real thing rather than a snapshot that was
already stale when the user tapped.
"""

from __future__ import annotations

import flet as ft

from ai.quick_sheet import open_quick_sheet
from core.theme import AppColors

_EXPLAIN = (
    "Read the terminal and tell me what the last command did. "
    "If it failed, say why it failed."
)
_RUN = "Run this in the terminal: "
_ASK = "About this terminal: "


def build_question(kind: str) -> str:
    """The prompt for one of the terminal quick actions."""
    if kind == "explain":
        return _EXPLAIN
    if kind == "run":
        return _RUN
    return _ASK


def open_terminal_sheet(page, ai, recent: str = "") -> None:
    """Show the quick-ask sheet for the terminal, then the Assistant."""
    if ai is None:
        return

    open_quick_sheet(
        page,
        ai,
        title="Terminal",
        preview=recent,
        actions=[
            (
                ft.Icons.PSYCHOLOGY_ROUNDED,
                "Explain the last output",
                "What ran, and why it failed if it did",
                _EXPLAIN,
                AppColors.WARNING,
            ),
            (
                ft.Icons.TERMINAL_ROUNDED,
                "Run a command",
                "Type what you want it to run",
                _RUN,
                AppColors.SUCCESS,
            ),
            (
                ft.Icons.CHAT_ROUNDED,
                "Ask about it",
                "Type your own question",
                _ASK,
                ft.Colors.PRIMARY,
            ),
        ],
    )


__all__ = ["build_question", "open_terminal_sheet"]

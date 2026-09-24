"""The per-cell Assistant sheet.

Tapping the chat icon on a cell opens this: the cell's own code, its error
if it has one, and the three questions people actually ask about a cell.
Each one seeds the composer and opens the Assistant sheet with the
question already written, so the user can add a detail or hit Send.

The point of showing the code here is that the user never has to describe
their cell — the question carries it.
"""

from __future__ import annotations

import flet as ft

from ai.panel import open_ai_panel
from core import tokens
from core.theme import AppColors

# Cell sources can be long; the sheet shows enough to recognize the cell
# without turning into a scroll-fest on a phone.
_PREVIEW_LINES = 6
_PREVIEW_CHARS = 900
_ERROR_CHARS = 600


def build_question(kind: str, number: int, source: str, error: str = "") -> str:
    """The prompt for one of the three quick actions.

    Kept free of Flet so the wording is testable and the model always
    gets the same shape: what the user wants, then the cell, 1-based.
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


def _preview(text: str) -> ft.Control | None:
    body = (text or "").strip()
    if not body:
        return None
    lines = body.splitlines()
    if len(lines) > _PREVIEW_LINES:
        lines = lines[:_PREVIEW_LINES] + [f"… {len(lines) - _PREVIEW_LINES} more lines"]
    return ft.Container(
        content=ft.Text(
            "\n".join(lines)[:_PREVIEW_CHARS],
            size=tokens.FONT_XS,
            color=ft.Colors.ON_SURFACE_VARIANT,
            selectable=True,
            style=ft.TextStyle(font_family="RobotoMono"),
        ),
        bgcolor=AppColors.TERMINAL_BG,
        border_radius=tokens.RADIUS_SM,
        padding=ft.Padding(
            tokens.SPACE_SM, tokens.SPACE_SM, tokens.SPACE_SM, tokens.SPACE_SM
        ),
    )


def open_cell_sheet(page, services, number: int, source: str, error: str = "") -> None:
    """Show the quick-ask sheet for one cell, then the Assistant."""
    if services.ai is None:
        return

    def _ask(kind: str, e=None):
        page.pop_dialog()
        services.ai.draft = build_question(kind, number, source, error)
        open_ai_panel(page, services)

    actions = [
        ft.ListTile(
            leading=ft.Icon(ft.Icons.LIGHTBULB_ROUNDED, color=AppColors.WARNING),
            title=ft.Text("Explain this cell"),
            subtitle=ft.Text("What it does, and what to watch for"),
            on_click=lambda e, k="explain": _ask(k, e),
        )
    ]
    if (error or "").strip():
        actions.append(
            ft.ListTile(
                leading=ft.Icon(ft.Icons.AUTO_FIX_HIGH_ROUNDED, color=AppColors.ERROR),
                title=ft.Text("Fix this error"),
                subtitle=ft.Text("Rewrite the cell so it runs"),
                on_click=lambda e: _ask("fix", e),
            )
        )
    actions.append(
        ft.ListTile(
            leading=ft.Icon(ft.Icons.CHAT_ROUNDED, color=ft.Colors.PRIMARY),
            title=ft.Text("Ask about it"),
            subtitle=ft.Text("Type your own question about this cell"),
            on_click=lambda e: _ask("ask", e),
        )
    )

    controls: list[ft.Control] = [
        ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.CHAT_ROUNDED, color=ft.Colors.PRIMARY, size=tokens.ICON_MD
                ),
                ft.Text(
                    f"Cell {number}",
                    size=tokens.FONT_MD,
                    weight=ft.FontWeight.BOLD,
                ),
            ],
            spacing=tokens.SPACE_XS,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    ]
    code_preview = _preview(source)
    if code_preview is not None:
        controls.append(code_preview)
    if (error or "").strip():
        controls.append(
            ft.Text(
                "ERROR",
                size=tokens.FONT_XXS,
                color=AppColors.ERROR,
                weight=ft.FontWeight.W_600,
            )
        )
        error_preview = _preview(error)
        if error_preview is not None:
            controls.append(error_preview)
    controls.extend(actions)

    page.show_dialog(
        ft.BottomSheet(
            content=ft.Container(
                content=ft.Column(controls=controls, spacing=tokens.SPACE_SM),
                padding=ft.Padding(
                    tokens.SPACE_MD, tokens.SPACE_MD, tokens.SPACE_MD, tokens.SPACE_MD
                ),
            ),
            show_drag_handle=True,
        )
    )


__all__ = ["build_question", "open_cell_sheet"]

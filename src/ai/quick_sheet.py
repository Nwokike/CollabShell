"""The quick-ask sheet — one small bottom sheet of questions about
whatever is on screen.

Both entry points look the same: a title, an optional preview of the
thing being asked about, and a few one-tap questions. Choosing one seeds
the Assistant's composer and opens the chat, so the user always sees the
question before it costs anything.

Each action carries its own question, because the question is the whole
point: a cell asks *about that cell's code*, a terminal asks *about what
just ran*. The sheet only draws them.
"""

from __future__ import annotations

import flet as ft

from ai.panel import open_ai_panel
from core import tokens
from core.theme import AppColors

# Previews exist to identify the subject, not to scroll: a phone shows a
# handful of lines before the questions.
_PREVIEW_LINES = 6
_PREVIEW_CHARS = 900


def open_quick_sheet(
    page,
    ai,
    *,
    title: str,
    preview: str = "",
    error: str = "",
    actions: list[tuple],
) -> None:
    """Show the sheet.

    Each action is (icon, label, sublabel, question, color): tapping one
    seeds `ai.draft` with that question and opens the Assistant.
    """

    def _ask(question: str, e=None):
        page.pop_dialog()
        ai.draft = question
        open_ai_panel(page, ai)

    controls: list[ft.Control] = [
        ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.CHAT_ROUNDED,
                    color=ft.Colors.PRIMARY,
                    size=tokens.ICON_MD,
                ),
                ft.Text(title, size=tokens.FONT_MD, weight=ft.FontWeight.BOLD),
            ],
            spacing=tokens.SPACE_XS,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    ]

    shown = _preview(preview)
    if shown is not None:
        controls.append(shown)

    if (error or "").strip():
        controls.append(
            ft.Text(
                "ERROR",
                size=tokens.FONT_XXS,
                color=AppColors.ERROR,
                weight=ft.FontWeight.W_600,
            )
        )
        shown_error = _preview(error)
        if shown_error is not None:
            controls.append(shown_error)

    for icon, label, sublabel, question, color in actions:
        controls.append(
            ft.ListTile(
                leading=ft.Icon(icon, color=color),
                title=label,
                subtitle=sublabel,
                on_click=lambda e, q=question: _ask(q, e),
            )
        )

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


__all__ = ["open_quick_sheet"]

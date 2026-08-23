"""Context-aware keyboard shortcuts help dialog (opened with F1)."""

from __future__ import annotations

import flet as ft

from core import tokens
from core.shortcuts import SHORTCUT_DOCS

__all__ = ["open_shortcuts_help"]


def _key_chip(combo: str) -> ft.Control:
    return ft.Container(
        content=ft.Text(
            combo,
            size=tokens.FONT_XS,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.PRIMARY,
        ),
        bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY),
        border_radius=tokens.RADIUS_SM,
        padding=ft.Padding(8, 3, 8, 3),
    )


def _section_rows(section_key: str) -> list[ft.Control]:
    title, rows = SHORTCUT_DOCS[section_key]
    controls: list[ft.Control] = [
        ft.Text(
            title,
            size=tokens.FONT_SM,
            weight=ft.FontWeight.W_700,
            color=ft.Colors.ON_SURFACE_VARIANT,
        ),
    ]
    controls.extend(
        ft.Row(
            controls=[
                _key_chip(combo),
                ft.Text(
                    description,
                    size=tokens.FONT_SM,
                    color=ft.Colors.ON_SURFACE,
                    expand=True,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=tokens.SPACE_SM,
        )
        for combo, description in rows
    )
    return controls


def open_shortcuts_help(page: ft.Page, context: str = "global") -> None:
    """Show the shortcuts cheat sheet — General plus the active screen's set."""
    body_controls: list[ft.Control] = [_section_rows("global")]
    if context in SHORTCUT_DOCS and context != "global":
        body_controls.append(ft.Divider(height=1, thickness=1))
        body_controls.append(_section_rows(context))

    page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Keyboard Shortcuts", weight=ft.FontWeight.W_700),
            content=ft.Container(
                content=ft.Column(
                    controls=body_controls,
                    spacing=tokens.SPACE_SM,
                    scroll=ft.ScrollMode.AUTO,
                    tight=True,
                ),
                width=380,
                max_height=440,
            ),
            actions=[
                ft.FilledButton("Close", on_click=lambda e: page.pop_dialog()),
            ],
        )
    )

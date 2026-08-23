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


def build_help_body(context: str = "global") -> list[ft.Control]:
    """Assemble the cheat-sheet body.

    Opened from a specific screen: General + that screen's section. Opened
    from Home (``context="global"``): General followed by EVERY screen's
    section — otherwise a Home visitor never learns the other screens have
    their own shortcuts.
    """
    # _section_rows() returns a LIST — extend, never append (a nested list
    # reaches Dart as List<dynamic> where a Control is expected).
    body_controls: list[ft.Control] = []
    body_controls.extend(_section_rows("global"))

    if context == "global":
        sections = [k for k in SHORTCUT_DOCS if k != "global"]
    elif context in SHORTCUT_DOCS:
        sections = [context]
    else:
        sections = []

    for key in sections:
        body_controls.append(ft.Divider(height=1, thickness=1))
        body_controls.extend(_section_rows(key))
    return body_controls


def build_help_button(page: ft.Page, context: str | None = None) -> ft.Control:
    """Header "?" button opening the cheat sheet. Desktop only — mobile has
    no keyboard, so the sheet would be dead weight in the app bar."""
    try:
        if page.platform.is_mobile():
            return ft.Container()
    except Exception:
        pass

    def _open(e=None):
        ctx = context
        if callable(ctx):
            ctx = ctx()
        open_shortcuts_help(page, ctx or "global")

    return ft.IconButton(
        icon=ft.Icons.KEYBOARD_OUTLINED,
        icon_size=18,
        tooltip="Keyboard Shortcuts (F1)",
        on_click=_open,
    )


def open_shortcuts_help(page: ft.Page, context: str = "global") -> None:
    """Show the shortcuts cheat sheet — General plus the active screen's set."""
    page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Keyboard Shortcuts", weight=ft.FontWeight.W_700),
            content=ft.Container(
                content=ft.Column(
                    controls=build_help_body(context),
                    spacing=tokens.SPACE_SM,
                    scroll=ft.ScrollMode.AUTO,
                    height=420,
                ),
                width=400,
            ),
            actions=[
                ft.FilledButton("Close", on_click=lambda e: page.pop_dialog()),
            ],
        )
    )

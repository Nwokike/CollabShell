"""Command palette — one searchable place for every action.

`Ctrl+K` opens it from anywhere in the shell. It exists mainly so the AI
actions (open the assistant, ask AI about this cell, explain the terminal,
suggest a runtime shape) are discoverable in the same place as everything
else, rather than hidden in per-screen menus.

Deliberately not a fuzzy-finder with scoring: the command list is a few dozen
items at most, and a case-insensitive substring match on the label is instant
and predictable. Arrow keys move, Enter runs, Escape closes.

Commands are `(label, icon, hint, action)` tuples supplied by the caller, so a
screen contributes exactly the actions it actually has — the palette never
shows a command that would do nothing.
"""

from __future__ import annotations

import flet as ft

from core import tokens

# Palette geometry. Tall enough for a full page of results, narrow enough that
# it reads as a quick command rather than a screen.
_WIDTH = 520
_HEIGHT = 400
_MAX_SHOWN = 40


def open_command_palette(page: ft.Page, commands: list) -> None:
    """Show the palette.

    `commands` is a list of ``(label, icon, hint, action)``; `action` is a
    zero-arg callable run on Enter or click, after the palette closes.
    """
    items = [c for c in (commands or []) if c and c[0]]
    if not items:
        return

    results = ft.Column(
        spacing=0,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
    # A one-element list rather than ft.Ref[int]: Flet's Ref holds a weak
    # reference, so it cannot wrap an immutable int.
    selected = [0]

    def _filter(query: str) -> list:
        query = (query or "").strip().lower()
        if not query:
            return items
        # Match the label, and also the hint, so "explain" finds the terminal
        # action whose label is "What the terminal is telling you".
        return [
            c
            for c in items
            if query in str(c[0]).lower()
            or (len(c) > 2 and query in str(c[2] or "").lower())
        ][:_MAX_SHOWN]

    def _run(entry):
        page.pop_dialog()
        action = entry[3] if len(entry) > 3 else None
        if callable(action):
            try:
                action()
            except Exception:
                # A palette entry must never be able to take the shell down.
                from core.notifications import show_notification

                show_notification(page, "That action failed.", is_error=True)

    def _paint(query: str = ""):
        shown = _filter(query)
        controls = []
        if not shown:
            controls.append(
                ft.Container(
                    content=ft.Text(
                        "No matching command",
                        size=tokens.FONT_SM,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    padding=ft.Padding.all(tokens.SPACE_LG),
                    alignment=ft.Alignment.CENTER,
                )
            )
        for index, entry in enumerate(shown):
            label, icon = entry[0], entry[1]
            hint = entry[2] if len(entry) > 2 else ""
            controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(
                                icon or ft.Icons.CHEVRON_RIGHT_ROUNDED,
                                size=tokens.ICON_SM,
                            ),
                            ft.Column(
                                [
                                    ft.Text(
                                        label,
                                        size=tokens.FONT_SM,
                                        weight=ft.FontWeight.W_600,
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                    *(
                                        [
                                            ft.Text(
                                                str(hint),
                                                size=tokens.FONT_XS,
                                                color=ft.Colors.ON_SURFACE_VARIANT,
                                                max_lines=1,
                                                overflow=ft.TextOverflow.ELLIPSIS,
                                            )
                                        ]
                                        if hint
                                        else []
                                    ),
                                ],
                                spacing=0,
                                expand=True,
                                tight=True,
                            ),
                        ],
                        spacing=tokens.SPACE_SM,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(
                        horizontal=tokens.SPACE_SM, vertical=tokens.SPACE_XS
                    ),
                    border_radius=tokens.RADIUS_MD,
                    bgcolor=(
                        ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY)
                        if index == selected[0]
                        else None
                    ),
                    ink=True,
                    on_click=lambda e, entry=entry: _run(entry),
                )
            )
        results.controls = controls
        try:
            results.update()
        except Exception:
            pass

    def _move(delta: int):
        shown = _filter(field.value or "")
        if not shown:
            return
        selected[0] = (selected[0] + delta) % len(shown)
        _paint(field.value or "")

    def _on_key(e):
        # Flutter reports arrows as "ArrowDown"; accept both spellings.
        key = (getattr(e, "key", "") or "").lower()
        if key in ("arrowdown", "downarrow"):
            _move(1)
        elif key in ("arrowup", "uparrow"):
            _move(-1)
        elif key in ("enter", "return"):
            shown = _filter(field.value or "")
            if shown and 0 <= selected[0] < len(shown):
                _run(shown[selected[0]])
        elif key in ("escape", "esc"):
            page.pop_dialog()

    field = ft.TextField(
        autofocus=True,
        dense=True,
        hint_text="Type a command",
        border=ft.OutlineInputBorder(border_radius=tokens.RADIUS_LG),
        on_change=lambda e: (selected.__setitem__(0, 0), _paint(e.control.value or "")),
    )

    _paint()

    # KeyboardListener wraps the whole dialog so arrows/Enter/Escape work no
    # matter which control inside holds focus — including the filter field.
    body = ft.KeyboardListener(
        autofocus=True,
        content=ft.Column(
            [field, ft.Container(height=tokens.SPACE_SM), results],
        ),
        on_key_down=_on_key,
    )

    page.show_dialog(
        ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [
                    ft.Icon(ft.Icons.KEYBOARD_COMMAND_KEY_ROUNDED, size=tokens.ICON_SM),
                    ft.Text("Commands"),
                ],
                spacing=tokens.SPACE_SM,
            ),
            content=ft.Container(content=body, width=_WIDTH, height=_HEIGHT),
            actions=[ft.TextButton("Close", on_click=lambda e: page.pop_dialog())],
            actions_alignment=ft.MainAxisAlignment.END,
        )
    )

"""Per-session environment override dialog (memory-only, never persisted).

Pre-filled from state.default_env. Effective env = defaults merged with the
session override (override wins per key). Values are never logged — see
services.colab.execution history redaction.
"""

import re

import flet as ft

from core import tokens

_ENV_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def show_env_override_dialog(
    page: ft.Page,
    state,
    session_env: dict,
    on_save,
    title: str = "Session Environment",
    subtitle: str = (
        "Defaults merged underneath; session values win per key. "
        "Values are never logged or saved."
    ),
    managed_note: str = "these defaults",
) -> None:
    """Show the env row dialog.

    Session mode (defaults): `session_env` is a memory-only override dict
    mutated in place on Save; rows pre-filled from state.default_env.
    Settings mode: pass a working copy + persist in `on_save`.
    `managed_note` names what the Remove action clears (kept generic so both
    callers share the dialog).
    """
    rows: list = []
    error_text = ft.Text("", size=tokens.FONT_XS, color=ft.Colors.ERROR)
    body = ft.Column(controls=[], spacing=tokens.SPACE_SM, scroll=ft.ScrollMode.AUTO)

    defaults = dict(getattr(state, "default_env", {}) or {})

    def _add_row(key: str = "", value: str = "", from_default: bool = False):
        key_field = ft.TextField(
            label="KEY",
            value=key,
            expand=True,
            text_size=tokens.FONT_SM,
            border=ft.OutlineInputBorder(border_radius=tokens.RADIUS_MD),
        )
        value_field = ft.TextField(
            label="VALUE",
            value=value,
            expand=True,
            password=True,
            can_reveal_password=True,
            text_size=tokens.FONT_SM,
            border=ft.OutlineInputBorder(border_radius=tokens.RADIUS_MD),
        )

        def _remove(e=None, row=None):
            if row is not None and row in rows:
                rows.remove(row)
            _rebuild()

        row = ft.Row(controls=[key_field, value_field])
        row_container = ft.Column(
            controls=[
                row,
                ft.Row(
                    controls=[
                        ft.Text(
                            "from defaults" if from_default else "session override",
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            italic=True,
                        ),
                        ft.Container(expand=True),
                        ft.TextButton(
                            "Remove",
                            on_click=lambda e, rc=None: _remove(e, row_container),
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                ),
            ],
            spacing=tokens.SPACE_XXS,
        )
        # Keep refs for harvest.
        row_container.data = (key_field, value_field)
        rows.append(row_container)
        _rebuild()

    def _rebuild():
        body.controls = list(rows)
        try:
            page.update()
        except Exception:
            pass

    def _on_add(e=None):
        _add_row()
        _rebuild()

    def _on_save(e=None):
        parsed: dict = {}
        for rc in rows:
            key_field, value_field = rc.data
            key = (key_field.value or "").strip()
            value = value_field.value or ""
            if not key and not value:
                continue
            if "=" in key or not _ENV_KEY_RE.fullmatch(key):
                error_text.value = (
                    f"Invalid key {key!r}. Expected a valid environment variable name."
                )
                page.update()
                return
            parsed[key] = value
        error_text.value = ""
        session_env.clear()
        session_env.update(parsed)
        page.pop_dialog()
        on_save(dict(parsed))
        page.update()

    def _on_clear(e=None):
        session_env.clear()
        on_save({})
        page.pop_dialog()
        page.update()

    def _close(e=None):
        page.pop_dialog()

    # Pre-fill: defaults first (marked), then session-only overrides.
    for k, v in defaults.items():
        _add_row(k, session_env.get(k, v), from_default=True)
    for k, v in session_env.items():
        if k not in defaults:
            _add_row(k, v, from_default=False)

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(title, weight=ft.FontWeight.W_700),
        content=ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(
                        subtitle,
                        size=tokens.FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    body,
                    error_text,
                ],
                spacing=tokens.SPACE_SM,
            ),
            width=420,
        ),
        actions=[
            ft.TextButton("Add row", on_click=_on_add),
            ft.TextButton("Clear", on_click=_on_clear),
            ft.TextButton("Cancel", on_click=_close),
            ft.FilledButton("Save", on_click=_on_save),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dialog)

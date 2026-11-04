"""Execution settings section — ported from views/settings/hardware_section.py::build_execution_section().

Contains:
- Default Timeout dropdown (using constants.TIMEOUT_OPTIONS)
- Log Export Format dropdown (ipynb / md / jsonl / txt)
- Default Environment Variables (same KEY=VALUE row dialog as the session
  Env chip; persisted here instead of memory-only)
"""

from __future__ import annotations

import json

import flet as ft

from components.env_dialog import show_env_override_dialog
from core import constants, tokens
from core.styles import glass_card, section_header, tip_text


def build_execution_section(page: ft.Page, state, services) -> ft.Column:
    async def _on_timeout_change(e):
        state.default_timeout = int(e.control.value)
        await services.storage.set(
            constants.STORAGE_DEFAULT_TIMEOUT, state.default_timeout
        )

    async def _on_log_format_change(e):
        state.default_log_format = e.control.value
        await services.storage.set(
            constants.STORAGE_LOG_FORMAT, state.default_log_format
        )

    # Derived from observable state at build time: `state.default_env` is
    # replaced (never mutated) when the dialog saves, and that write repaints
    # this section through the observable notify. The previous version also
    # assigned `env_summary.value` and called `page.update()` from inside the
    # render body — a frozen-control write that silently failed, and a page
    # push from a body.
    env_count = len(getattr(state, "default_env", {}) or {})
    env_summary = ft.Text(
        f"{env_count} variable{'s' if env_count != 1 else ''} set"
        if env_count
        else "No default variables",
        size=tokens.FONT_XS,
        color=ft.Colors.ON_SURFACE_VARIANT,
        italic=True,
    )

    def _open_env_dialog(e=None):
        # Persisted mode: the working dict IS state.default_env; on_save
        # writes it to storage. Values masked, validated per row.
        working = dict(getattr(state, "default_env", {}) or {})

        async def _persist(saved: dict):
            state.default_env = dict(saved)
            await services.storage.set(
                constants.STORAGE_DEFAULT_ENV, json.dumps(state.default_env)
            )
            # No repaint call needed: the observable write above rebuilds this
            # section, and the summary is derived from the state at build time.

        def _on_save(saved: dict):
            page.run_task(_persist, saved)

        show_env_override_dialog(
            page,
            state,
            working,
            on_save=_on_save,
            title="Default Environment",
            subtitle="Injected into every execution. Values are never logged or saved in plain text outside this store.",
            managed_note="these defaults",
        )

    return ft.Column(
        controls=[
            section_header("EXECUTION"),
            glass_card(
                ft.Column(
                    controls=[
                        # Default timeout
                        ft.Row(
                            controls=[
                                ft.Icon(
                                    ft.Icons.TIMER_ROUNDED,
                                    size=tokens.ICON_LG,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            "Default Timeout",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        tip_text(constants.TIP_TIMEOUT),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                                ft.Dropdown(
                                    value=str(state.default_timeout),
                                    options=[
                                        ft.dropdown.Option(str(t), f"{t}s")
                                        for t in constants.TIMEOUT_OPTIONS
                                    ],
                                    width=tokens.INPUT_WIDTH_SM,
                                    border=ft.OutlineInputBorder(
                                        border_radius=tokens.RADIUS_MD
                                    ),
                                    text_size=tokens.FONT_SM,
                                    on_select=lambda e: page.run_task(
                                        _on_timeout_change, e
                                    ),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=tokens.SPACE_LG,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        # Log export format
                        ft.Row(
                            controls=[
                                ft.Icon(
                                    ft.Icons.SAVE_ALT_ROUNDED,
                                    size=tokens.ICON_LG,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            "Log Export Format",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        tip_text(
                                            "Default format when exporting session logs"
                                        ),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                                ft.Dropdown(
                                    value=state.default_log_format,
                                    options=[
                                        ft.dropdown.Option("ipynb", ".ipynb"),
                                        ft.dropdown.Option("md", ".md"),
                                        ft.dropdown.Option("jsonl", ".jsonl"),
                                        ft.dropdown.Option("txt", ".txt"),
                                    ],
                                    width=tokens.INPUT_WIDTH_SM,
                                    border=ft.OutlineInputBorder(
                                        border_radius=tokens.RADIUS_MD
                                    ),
                                    text_size=tokens.FONT_SM,
                                    on_select=lambda e: page.run_task(
                                        _on_log_format_change, e
                                    ),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=tokens.SPACE_LG,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        # Default environment variables (same row dialog as
                        # the session Env chip; persisted here)
                        ft.Row(
                            controls=[
                                ft.Icon(
                                    ft.Icons.TUNE_ROUNDED,
                                    size=tokens.ICON_LG,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            "Default Environment",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        env_summary,
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                                ft.FilledButton(
                                    "Manage",
                                    on_click=_open_env_dialog,
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=tokens.SPACE_LG,
                        ),
                    ],
                ),
                margin=ft.Margin(
                    tokens.SPACE_LG,
                    tokens.SPACE_XS,
                    tokens.SPACE_LG,
                    tokens.SPACE_XS,
                ),
            ),
        ],
        spacing=0,
    )

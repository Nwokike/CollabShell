"""Execution settings section — ported from views/settings/hardware_section.py::build_execution_section().

Contains:
- Default Timeout dropdown (using constants.TIMEOUT_OPTIONS)
- Log Export Format dropdown (ipynb / md / jsonl / txt)
"""

from __future__ import annotations

import flet as ft

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
                                    border_radius=tokens.RADIUS_MD,
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
                                    border_radius=tokens.RADIUS_MD,
                                    text_size=tokens.FONT_SM,
                                    on_select=lambda e: page.run_task(
                                        _on_log_format_change, e
                                    ),
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

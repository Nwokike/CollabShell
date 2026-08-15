"""Execution settings section (timeout and log export format)."""

from __future__ import annotations

import flet as ft

from core import constants, tokens
from core.styles import section_card, tip_text


def build_execution_section(page: ft.Page, state, services) -> ft.Container:
    async def _on_timeout_change(e):
        try:
            state.default_timeout = int(e.control.value)
            await services.storage.set(
                constants.STORAGE_DEFAULT_TIMEOUT, str(state.default_timeout)
            )
        except (ValueError, TypeError):
            pass

    async def _on_log_format_change(e):
        state.default_log_format = e.control.value
        await services.storage.set(
            constants.STORAGE_LOG_FORMAT, state.default_log_format
        )

    return section_card(
        "Execution & Logs",
        ft.Icons.TIMER_ROUNDED,
        ft.Column(
            controls=[
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
                            on_change=lambda e: page.run_task(_on_timeout_change, e),
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=tokens.SPACE_LG,
                ),
                ft.Divider(
                    height=1,
                    color=ft.Colors.with_opacity(
                        tokens.OPACITY_CONTAINER, ft.Colors.ON_SURFACE
                    ),
                ),
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
                                tip_text("Default format when exporting session logs"),
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
                            on_change=lambda e: page.run_task(_on_log_format_change, e),
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=tokens.SPACE_LG,
                ),
            ],
            spacing=tokens.SPACE_SM,
        ),
        page=page,
    )

"""Compute usage settings section — balance, burn rate, active runtimes."""

from __future__ import annotations

import asyncio
import logging

import flet as ft

from core import tokens
from core.styles import glass_card, section_header

logger = logging.getLogger(__name__)


def build_usage_section(page: ft.Page, state, services) -> ft.Column:
    async def _show_usage(e=None):
        def _fetch():
            from colab_cli.auth import AuthProvider
            from colab_cli.common import State
            from colab_cli.consumption import format_consumption_status

            st = State()
            st.auth_provider = (
                AuthProvider.ADC if state.auth_method == "adc" else AuthProvider.OAUTH2
            )
            return format_consumption_status(st.client.get_consumption_user_info())

        try:
            text = await asyncio.to_thread(_fetch)
        except Exception as ex:
            logger.warning("Compute usage lookup failed: %s", ex)
            text = (
                "Could not load your compute usage.\n"
                "Make sure you are signed in, then try again."
            )
        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Compute Usage", weight=ft.FontWeight.BOLD),
                content=ft.Text(
                    text,
                    selectable=True,
                    font_family="RobotoMono",
                    size=tokens.FONT_SM,
                ),
                actions=[ft.TextButton("Close", on_click=lambda ev: page.pop_dialog())],
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )

    return ft.Column(
        controls=[
            section_header("COMPUTE USAGE"),
            glass_card(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Column(
                                controls=[
                                    ft.Text(
                                        "Check your compute balance",
                                        size=tokens.FONT_MD,
                                        weight=ft.FontWeight.W_500,
                                    ),
                                    ft.Text(
                                        "Balance, usage per hour, and active runtimes",
                                        size=tokens.FONT_XS,
                                        color=ft.Colors.ON_SURFACE_VARIANT,
                                    ),
                                ],
                                spacing=tokens.SPACE_XXS,
                                expand=True,
                            ),
                            ft.Icon(
                                ft.Icons.CHEVRON_RIGHT_ROUNDED,
                                size=tokens.ICON_LG,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=tokens.SPACE_MD,
                    ),
                    ink=True,
                    tooltip="Tap to check your compute-unit balance",
                    on_click=lambda e: page.run_task(_show_usage, e),
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


__all__ = ["build_usage_section"]

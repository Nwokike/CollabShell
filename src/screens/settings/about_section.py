"""About, version metadata, legal terms, and Pro tease settings section."""

from __future__ import annotations

import logging

import flet as ft

from core import constants, tokens
from core.styles import glass_card, section_header
from core.urls import get_url_launcher

logger = logging.getLogger(__name__)


def _get_cli_version() -> str:
    try:
        from colab_cli.auto_update import get_app_version as _get_cli_ver

        return _get_cli_ver()
    except Exception:
        return "latest"


def _open_version_dialog(page: ft.Page, state):
    """Open the version dialog — changelog when up to date, update UI when
    a newer build was found. The dialog reads observable state itself."""
    from components.version_dialog import show_version_dialog

    show_version_dialog(page)


def build_about_section(page: ft.Page, state, services) -> ft.Column:
    """App metadata, version info, and terms links."""
    cli_version = _get_cli_version()

    async def _launch_privacy(e=None):
        try:
            await get_url_launcher().launch_url(constants.PRIVACY_POLICY_URL)
        except Exception:
            logger.exception("Suppressed exception")

    async def _launch_terms(e=None):
        try:
            await get_url_launcher().launch_url(constants.TERMS_OF_SERVICE_URL)
        except Exception:
            logger.exception("Suppressed exception")

    return ft.Column(
        controls=[
            section_header("ABOUT"),
            glass_card(
                ft.Column(
                    controls=[
                        ft.Container(
                            content=ft.Image(
                                src="icon.png",
                                width=tokens.HERO_ICON_SIZE,
                                height=tokens.HERO_ICON_SIZE,
                                fit=ft.BoxFit.CONTAIN,
                            ),
                            alignment=ft.Alignment.CENTER,
                            margin=ft.Margin(0, tokens.SPACE_SM, 0, tokens.SPACE_XS),
                        ),
                        ft.Text(
                            "Cloud GPUs and Notebooks from your phone",
                            size=tokens.FONT_SM,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Container(height=tokens.SPACE_SM),
                        ft.Container(
                            content=ft.Row(
                                controls=[
                                    ft.Text("App Version", size=tokens.FONT_SM),
                                    ft.Text(
                                        f"v{constants.APP_VERSION}",
                                        size=tokens.FONT_SM,
                                        color=ft.Colors.ON_SURFACE_VARIANT,
                                        weight=ft.FontWeight.W_500,
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            ),
                            ink=True,
                            tooltip="Tap to view changelog",
                            on_click=lambda e: _open_version_dialog(page, state),
                        ),
                        ft.Row(
                            controls=[
                                ft.Text("Powered by", size=tokens.FONT_SM),
                                ft.Text(
                                    f"Google Colab (CLI v{cli_version})",
                                    size=tokens.FONT_SM,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                    weight=ft.FontWeight.W_500,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Divider(
                            height=1,
                            color=ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
                        ),
                        ft.Row(
                            controls=[
                                ft.TextButton(
                                    "Privacy Policy",
                                    icon=ft.Icons.PRIVACY_TIP_ROUNDED,
                                    style=ft.ButtonStyle(color=ft.Colors.PRIMARY),
                                    on_click=lambda e: page.run_task(
                                        _launch_privacy, e
                                    ),
                                ),
                                ft.TextButton(
                                    "Terms of Service",
                                    icon=ft.Icons.GAVEL_ROUNDED,
                                    style=ft.ButtonStyle(color=ft.Colors.PRIMARY),
                                    on_click=lambda e: page.run_task(_launch_terms, e),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_EVENLY,
                        ),
                        ft.Text(
                            "Disclaimer: Unofficial client application. Not affiliated with, authorized, sponsored, or endorsed by Google LLC.",
                            size=tokens.FONT_XXS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            italic=True,
                            text_align=ft.TextAlign.CENTER,
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
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

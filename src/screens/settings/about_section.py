"""About and app info settings section."""

from __future__ import annotations

import flet as ft

from components.brand_header import build_brand_header
from core import constants, tokens
from core.styles import section_card


def build_about_section(page: ft.Page, state, services) -> ft.Container:
    return section_card(
        "About",
        ft.Icons.INFO_ROUNDED,
        ft.Column(
            controls=[
                ft.Container(
                    content=build_brand_header(show_tagline=True, spacing_below=False),
                    opacity=0.85,
                ),
                ft.Divider(
                    height=1,
                    color=ft.Colors.with_opacity(
                        tokens.OPACITY_CONTAINER, ft.Colors.ON_SURFACE
                    ),
                ),
                ft.Row(
                    controls=[
                        ft.Text("Version", size=tokens.FONT_SM),
                        ft.Text(
                            f"v{constants.APP_VERSION}",
                            size=tokens.FONT_SM,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Row(
                    controls=[
                        ft.Text("Core Engine", size=tokens.FONT_SM),
                        ft.Text(
                            "google-colab-cli",
                            size=tokens.FONT_SM,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Text(
                    "Disclaimer: Unofficial client application. Not affiliated with, authorized, sponsored, or endorsed by Google LLC.",
                    size=tokens.FONT_XXS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    italic=True,
                ),
            ],
            spacing=tokens.SPACE_SM,
        ),
        page=page,
    )

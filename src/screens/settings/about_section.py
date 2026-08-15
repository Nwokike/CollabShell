"""About and app info settings section."""

from __future__ import annotations

import flet as ft

from components.brand_header import build_brand_header
from core import tokens
from core.styles import glass_card, section_header


def build_about_section(page: ft.Page, state, services) -> ft.Column:
    return ft.Column(
        controls=[
            section_header("ABOUT"),
            glass_card(
                ft.Column(
                    controls=[
                        ft.Container(
                            content=build_brand_header(
                                show_tagline=True, spacing_below=False
                            ),
                            opacity=0.8,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
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

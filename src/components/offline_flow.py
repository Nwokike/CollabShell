"""OfflineFlow — retry-only no-internet surface shown at startup.

Adapted from KTV Player's OfflineFlow pattern. Pure presentational function:
it takes an `on_retry` callback and owns no async/loading state. The parent
component (the router) owns the probing logic.
"""

import flet as ft
from flet import Control

from core import tokens
from core.theme import AppColors


def OfflineFlow(on_retry) -> Control:
    """Centered offline card with a single Retry button."""
    return ft.Container(
        alignment=ft.Alignment(0.0, 0.0),
        expand=True,
        padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, 0),
        content=ft.Column(
            controls=[
                ft.Icon(
                    ft.Icons.CLOUD_OFF_ROUNDED,
                    size=tokens.ICON_XXXL,
                    color=AppColors.WARNING,
                ),
                ft.Container(height=tokens.SPACE_MD),
                ft.Text(
                    "No internet connection",
                    size=tokens.FONT_XL,
                    weight=ft.FontWeight.W_700,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=tokens.SPACE_SM),
                ft.Text(
                    "Check your network and try again.\n"
                    "You need a connection to sign in and manage sessions.",
                    size=tokens.FONT_SM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=tokens.SPACE_XL),
                ft.FilledButton(
                    content=ft.Text("Retry Connection"),
                    icon=ft.Icons.REFRESH_ROUNDED,
                    on_click=on_retry,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        ),
    )

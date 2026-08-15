"""Account and authentication settings section."""

from __future__ import annotations

import flet as ft

from core import tokens
from core.styles import glass_card, section_header


def build_account_section(page: ft.Page, state, services) -> ft.Column:
    async def _sign_out(e):
        try:
            await services.colab.revoke_auth()
        except Exception:
            pass
        state.is_authenticated = False
        state.auth_email = ""
        state.onboarding_done = False

    return ft.Column(
        controls=[
            section_header("ACCOUNT"),
            glass_card(
                ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Icon(
                                    ft.Icons.ACCOUNT_CIRCLE_ROUNDED,
                                    size=tokens.ICON_XL,
                                    color=ft.Colors.PRIMARY,
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            state.auth_email or "Not signed in",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        ft.Text(
                                            "Google Account"
                                            if state.is_authenticated
                                            else "Sign in to use Colab",
                                            size=tokens.FONT_XS,
                                            color=ft.Colors.ON_SURFACE_VARIANT,
                                        ),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                            ],
                            spacing=tokens.SPACE_MD,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        ft.OutlinedButton(
                            "Sign Out",
                            icon=ft.Icons.LOGOUT_ROUNDED,
                            on_click=lambda e: page.run_task(_sign_out, e),
                            visible=state.is_authenticated,
                            style=ft.ButtonStyle(color=ft.Colors.ERROR),
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

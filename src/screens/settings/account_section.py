"""Account and authentication settings section."""

from __future__ import annotations

import flet as ft

from core import constants, tokens
from core.styles import section_card, tip_text
from core.theme import AppColors


def build_account_section(page: ft.Page, state, services, snack=None) -> ft.Container:
    async def _on_auth_method_change(e):
        val = e.control.value
        state.auth_method = val
        await services.storage.set(constants.STORAGE_AUTH_METHOD, val)

    async def _on_reauth(e):
        if snack:
            snack("Clearing Google token...")
        await services.colab.clear_token()
        state.is_authenticated = False
        state.auth_email = ""
        state.onboarding_done = False
        await services.storage.set(constants.STORAGE_ONBOARDING_DONE, "false")
        page.update()

    async def _on_whoami(e):
        if snack:
            snack("Checking Google credentials...")
        result = await services.colab.check_auth()
        if result.get("authenticated"):
            msg = f"Email: {result.get('email', 'N/A')}\nExpires in: {result.get('expires_in', 'N/A')}\nMethod: {result.get('auth_method', state.auth_method)}"
        else:
            msg = "Not authenticated — sign in to get started."

        info_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                controls=[
                    ft.Icon(
                        ft.Icons.PERSON_SEARCH_ROUNDED,
                        size=tokens.ICON_MD,
                        color=ft.Colors.PRIMARY,
                    ),
                    ft.Text(
                        "Authentication Details",
                        size=tokens.FONT_LG,
                        weight=ft.FontWeight.BOLD,
                    ),
                ],
                spacing=tokens.SPACE_SM,
            ),
            content=ft.Text(msg, size=tokens.FONT_SM, selectable=True),
            actions=[ft.FilledButton("Close", on_click=lambda _: page.pop_dialog())],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(info_dialog)

    auth_status_color = AppColors.SUCCESS if state.is_authenticated else AppColors.ERROR
    auth_status_icon = (
        ft.Icons.CHECK_CIRCLE_ROUNDED
        if state.is_authenticated
        else ft.Icons.ERROR_ROUNDED
    )
    auth_status_text = (
        f"Signed in as {state.auth_email}"
        if state.is_authenticated
        else "Not signed in"
    )

    return section_card(
        "Authentication",
        ft.Icons.ACCOUNT_CIRCLE_ROUNDED,
        ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(
                            auth_status_icon,
                            size=tokens.ICON_LG,
                            color=auth_status_color,
                        ),
                        ft.Column(
                            controls=[
                                ft.Text(
                                    auth_status_text,
                                    size=tokens.FONT_MD,
                                    weight=ft.FontWeight.W_500,
                                ),
                                ft.Text(
                                    "Google Account"
                                    if state.is_authenticated
                                    else "Sign in to access Google Colab runtimes",
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
                ft.Divider(
                    height=1,
                    color=ft.Colors.with_opacity(
                        tokens.OPACITY_CONTAINER, ft.Colors.ON_SURFACE
                    ),
                ),
                ft.Row(
                    controls=[
                        ft.Icon(
                            ft.Icons.VPN_KEY_ROUNDED,
                            size=tokens.ICON_LG,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Column(
                            controls=[
                                ft.Text(
                                    "Auth Method",
                                    size=tokens.FONT_MD,
                                    weight=ft.FontWeight.W_500,
                                ),
                                tip_text(
                                    constants.TIP_AUTH_OAUTH2
                                    if state.auth_method == "oauth2"
                                    else constants.TIP_AUTH_ADC
                                ),
                            ],
                            spacing=tokens.SPACE_XXS,
                            expand=True,
                        ),
                        ft.Dropdown(
                            value=state.auth_method,
                            options=[
                                ft.dropdown.Option("oauth2", "OAuth2"),
                                ft.dropdown.Option("adc", "ADC"),
                            ],
                            width=tokens.INPUT_WIDTH_MD,
                            border_radius=tokens.RADIUS_MD,
                            text_size=tokens.FONT_SM,
                            on_change=lambda e: page.run_task(
                                _on_auth_method_change, e
                            ),
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
                        ft.OutlinedButton(
                            constants.LBL_RE_AUTH,
                            icon=ft.Icons.REFRESH_ROUNDED,
                            on_click=lambda e: page.run_task(_on_reauth, e),
                            expand=True,
                        ),
                        ft.OutlinedButton(
                            "Who Am I",
                            icon=ft.Icons.PERSON_SEARCH_ROUNDED,
                            on_click=lambda e: page.run_task(_on_whoami, e),
                            expand=True,
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                ),
            ],
            spacing=tokens.SPACE_SM,
        ),
        page=page,
    )

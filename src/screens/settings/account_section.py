"""Account and authentication settings section.

Restored from views/settings/auth_section.py:
- Auth status indicator (icon + email or "Not signed in")
- Auth method dropdown (oauth2 / adc) with tip text, persisted to STORAGE_AUTH_METHOD
- Re-Authenticate button (clear_token → navigate to onboarding)
- Who Am I button (check_auth → AlertDialog with email/expiry/method)
"""

from __future__ import annotations

import flet as ft

from core import constants, tokens
from core.styles import glass_card, section_header, tip_text
from core.theme import AppColors


def build_account_section(page: ft.Page, state, services) -> ft.Column:
    # ── Auth status indicator ─────────────────────────────────────────────────
    auth_status_icon = (
        ft.Icons.CHECK_CIRCLE_ROUNDED
        if state.is_authenticated
        else ft.Icons.ERROR_ROUNDED
    )
    auth_status_color = AppColors.SUCCESS if state.is_authenticated else AppColors.ERROR
    auth_status_text = (
        f"Signed in as {state.auth_email}"
        if state.is_authenticated
        else "Not signed in"
    )

    # ── Handlers ──────────────────────────────────────────────────────────────
    async def _on_auth_method_change(e):
        val = e.control.value
        state.auth_method = val
        await services.storage.set(constants.STORAGE_AUTH_METHOD, val)
        page.update()

    async def _on_reauth(e):
        controller_snack = getattr(state, "_snack", None)
        try:
            await services.colab.clear_token()
        except Exception:
            pass
        state.is_authenticated = False
        state.auth_email = ""
        state.onboarding_done = False
        await services.storage.set(constants.STORAGE_ONBOARDING_DONE, "false")
        page.update()

    async def _on_whoami(e):
        try:
            result = await services.colab.check_auth()
        except Exception as ex:
            result = {"authenticated": False, "error": str(ex)}

        if result.get("authenticated"):
            msg = (
                f"Email: {result.get('email', 'unknown')}\n"
                f"Expires: {result.get('expires_in', 'unknown')}\n"
                f"Method: {result.get('auth_method', state.auth_method)}"
            )
        else:
            msg = "Not authenticated"

        def _close_info(e=None):
            page.pop_dialog()

        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Who Am I"),
                content=ft.Text(msg, selectable=True),
                actions=[ft.TextButton("OK", on_click=_close_info)],
            )
        )

    # ── Current tip text based on auth method ────────────────────────────────
    current_tip = (
        constants.TIP_AUTH_OAUTH2
        if state.auth_method == "oauth2"
        else constants.TIP_AUTH_ADC
    )

    return ft.Column(
        controls=[
            section_header("AUTHENTICATION"),
            glass_card(
                ft.Column(
                    controls=[
                        # Auth status row
                        ft.Row(
                            controls=[
                                ft.Icon(
                                    auth_status_icon,
                                    size=tokens.ICON_LG,
                                    color=auth_status_color,
                                ),
                                ft.Text(
                                    auth_status_text,
                                    size=tokens.FONT_MD,
                                    weight=ft.FontWeight.W_500,
                                    expand=True,
                                ),
                            ],
                            spacing=tokens.SPACE_MD,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        # Auth method dropdown
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
                                        tip_text(current_tip),
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
                                    on_select=lambda e: page.run_task(
                                        _on_auth_method_change, e
                                    ),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=tokens.SPACE_LG,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        # Re-Authenticate + Who Am I buttons
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

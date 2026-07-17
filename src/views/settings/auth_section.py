import flet as ft
from core import tokens, constants
from core.theme import AppColors
from core.styles import glass_card, section_header, tip_text


def build_auth_section(page: ft.Page, colab_service, state, storage, snack):
    async def _on_auth_method_change(e):
        val = e.control.value
        state.auth_method = val
        await storage.set(constants.STORAGE_AUTH_METHOD, val)
        page.update()

    async def _on_reauth(e):
        snack("Clearing token...")
        await colab_service.clear_token()
        state.is_authenticated = False
        state.auth_email = ""
        state.onboarding_done = False
        await storage.set(constants.STORAGE_ONBOARDING_DONE, "false")
        snack("Token cleared. Redirecting to onboarding...")
        page.route = "/onboarding"
        page.update()

    async def _on_whoami(e):
        snack("Checking credentials...")
        result = await colab_service.check_auth()
        if result["authenticated"]:
            msg = f"Email: {result['email']}\nExpires: {result['expires_in']}\nMethod: {result['auth_method']}"
        else:
            msg = "Not authenticated"

        def _close_info(e=None):
            info_dialog.open = False
            page.update()

        info_dialog = ft.AlertDialog(
            title=ft.Text("Who Am I"),
            content=ft.Text(msg),
            actions=[ft.TextButton("OK", on_click=_close_info)],
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

    auth_section = ft.Column(
        controls=[
            section_header("AUTHENTICATION"),
            glass_card(
                ft.Column(
                    controls=[
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
                                    on_select=lambda e: page.run_task(
                                        _on_auth_method_change, e
                                    ),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=tokens.SPACE_LG,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
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
                    tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
                ),
            ),
        ],
        spacing=0,
    )
    return auth_section

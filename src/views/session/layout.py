import asyncio
import flet as ft
from core import tokens, constants
from core.styles import glass_card
from core.theme import AppColors


def build_action_chip(icon, label, on_click, color=None):
    icon_color = color or ft.Colors.ON_SURFACE
    return ft.FilledButton(
        content=ft.Row(
            [
                ft.Icon(icon, size=tokens.ICON_SM, color=icon_color),
                ft.Text(label, size=tokens.FONT_XS, color=ft.Colors.ON_SURFACE),
            ],
            spacing=tokens.SPACE_XS,
        ),
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=tokens.RADIUS_MD),
            bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.ON_SURFACE),
            elevation=0,
        ),
        on_click=on_click,
        height=tokens.SPACE_XL * 2,
    )


def build_action_row(
    page: ft.Page,
    on_files,
    on_mount_drive,
    on_auth_gcp,
    on_open_browser,
    on_terminal,
    on_view_logs,
    on_restart,
    on_stop,
):
    return ft.Container(
        content=ft.Row(
            controls=[
                build_action_chip(ft.Icons.FOLDER_ROUNDED, "Files", on_files),
                build_action_chip(
                    ft.Icons.ADD_TO_DRIVE_ROUNDED, "Mount Drive", on_mount_drive
                ),
                build_action_chip(ft.Icons.SECURITY_ROUNDED, "Auth GCP", on_auth_gcp),
                build_action_chip(
                    ft.Icons.OPEN_IN_BROWSER_ROUNDED,
                    constants.LBL_OPEN_BROWSER,
                    on_open_browser,
                    AppColors.BADGE_TPU,
                ),
                build_action_chip(
                    ft.Icons.TERMINAL_ROUNDED,
                    "Terminal",
                    on_terminal,
                    AppColors.BADGE_GPU,
                ),
                build_action_chip(ft.Icons.HISTORY_ROUNDED, "Logs", on_view_logs),
                build_action_chip(
                    ft.Icons.REFRESH_ROUNDED,
                    "Restart",
                    on_restart,
                    AppColors.WARNING,
                ),
                build_action_chip(
                    ft.Icons.STOP_CIRCLE_ROUNDED,
                    "Stop",
                    on_stop,
                    AppColors.ERROR,
                ),
            ],
            scroll=ft.ScrollMode.HIDDEN,
            spacing=tokens.SPACE_SM,
        ),
        padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, 0),
    )


def build_keep_alive_card(
    page: ft.Page, state, on_keep_alive, on_keep_alive_disconnect
):
    def _keep_alive_toggle(label, tooltip, value, on_change):
        async def _trigger_change(e):
            if callable(on_change):
                res = on_change(e)
                if asyncio.iscoroutine(res):
                    await res

        return ft.Row(
            controls=[
                ft.Column(
                    controls=[
                        ft.Text(
                            label,
                            size=tokens.FONT_SM,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(
                            tooltip,
                            size=tokens.FONT_XXS,
                            color=ft.Colors.with_opacity(
                                0.6, ft.Colors.ON_SURFACE_VARIANT
                            ),
                        ),
                    ],
                    spacing=tokens.SPACE_XXS,
                    expand=True,
                ),
                ft.Switch(
                    value=value,
                    on_change=lambda e: page.run_task(_trigger_change, e),
                    scale=0.75,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    return glass_card(
        ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(
                            ft.Icons.POWER_SETTINGS_NEW_ROUNDED,
                            size=tokens.ICON_SM,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(
                            "Keep Session Alive",
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.W_600,
                            color=ft.Colors.ON_SURFACE,
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                _keep_alive_toggle(
                    "Active keep-alive",
                    "Ping the session every 60s to prevent timeout",
                    state.keep_alive_enabled,
                    on_keep_alive,
                ),
                _keep_alive_toggle(
                    "Keep alive on disconnect",
                    "Keep sessions running when the app closes",
                    state.keep_alive_on_disconnect,
                    on_keep_alive_disconnect,
                ),
            ],
            spacing=tokens.SPACE_SM,
        ),
        margin=ft.Margin(
            tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
        ),
    )

"""Session screen layout components (action chips, status header)."""

from __future__ import annotations

import flet as ft

from core import constants, tokens
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
    on_env=None,
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
                *(
                    [
                        build_action_chip(
                            ft.Icons.TUNE_ROUNDED,
                            "Env",
                            on_env,
                            AppColors.BADGE_TPU,
                        )
                    ]
                    if on_env
                    else []
                ),
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
            scroll=ft.ScrollMode.AUTO,
            spacing=tokens.SPACE_SM,
        ),
        padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, 0),
    )


def build_tab_switcher(active_tab: int, on_switch) -> ft.Container:
    """Compact Notebook/Terminal pill switcher for the session header.

    Modeled on SpanInsight's Insight/Expert mode bar: two segments in a
    bordered container; the active segment gets PRIMARY bg + white text.
    """

    def _segment(idx: int, label: str, icon) -> ft.Container:
        is_active = active_tab == idx
        fg = ft.Colors.WHITE if is_active else ft.Colors.ON_SURFACE_VARIANT
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(icon, size=tokens.ICON_MICRO, color=fg),
                    ft.Text(
                        label,
                        size=tokens.FONT_XS,
                        weight=ft.FontWeight.BOLD
                        if is_active
                        else ft.FontWeight.NORMAL,
                        color=fg,
                    ),
                ],
                spacing=tokens.SPACE_XXS,
                alignment=ft.MainAxisAlignment.CENTER,
                tight=True,
            ),
            bgcolor=ft.Colors.PRIMARY if is_active else ft.Colors.TRANSPARENT,
            border_radius=tokens.RADIUS_SM,
            padding=ft.Padding(
                tokens.SPACE_SM, tokens.SPACE_XXS, tokens.SPACE_SM, tokens.SPACE_XXS
            ),
            ink=True,
            on_click=lambda e: on_switch(idx),
        )

    return ft.Container(
        padding=ft.Padding(
            tokens.SPACE_XXS,
            tokens.SPACE_XXS,
            tokens.SPACE_XXS,
            tokens.SPACE_XXS,
        ),
        border_radius=tokens.RADIUS_SM,
        bgcolor=ft.Colors.with_opacity(tokens.OPACITY_ACCENT, ft.Colors.ON_SURFACE),
        border=ft.Border.all(
            tokens.DIVIDER_THICKNESS,
            ft.Colors.with_opacity(tokens.OPACITY_CARD, ft.Colors.ON_SURFACE),
        ),
        content=ft.Row(
            controls=[
                _segment(0, "Notebook", ft.Icons.EDIT_NOTE_ROUNDED),
                _segment(1, "Terminal", ft.Icons.TERMINAL_ROUNDED),
            ],
            spacing=tokens.SPACE_XXS,
            tight=True,
        ),
    )

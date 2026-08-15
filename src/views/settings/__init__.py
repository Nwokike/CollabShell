import flet as ft

from core import tokens
from core.styles import build_banner_ad
from views.settings.advanced_section import (
    build_about_section,
    build_advanced_section,
    build_behavior_section,
)
from views.settings.auth_section import build_auth_section
from views.settings.hardware_section import (
    build_execution_section,
    build_hardware_section,
)
from views.settings.logs_section import build_logs_section
from views.settings.preferences import build_preferences_section


def build_settings_view(
    page: ft.Page,
    colab_service,
    state,
    storage,
    on_back=None,
    snack=None,
    theme_btn=None,
) -> ft.View:
    """Build the settings screen view."""

    def _snack(msg: str):
        if snack:
            snack(msg)

    preferences_section = build_preferences_section(page, state, storage)
    auth_section = build_auth_section(page, colab_service, state, storage, _snack)
    hardware_section = build_hardware_section(page, state, storage)
    execution_section = build_execution_section(page, state, storage)
    behavior_section = build_behavior_section(page, state, storage)
    advanced_section = build_advanced_section(page, state, storage)
    logs_section = build_logs_section(page)
    about_section = build_about_section()

    view_content = ft.Column(
        controls=[
            preferences_section,
            auth_section,
            build_banner_ad(page),
            hardware_section,
            execution_section,
            behavior_section,
            build_banner_ad(page),
            advanced_section,
            logs_section,
            about_section,
            ft.Container(height=tokens.SPACE_XXL),
        ],
        spacing=tokens.SPACE_SM,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    return ft.View(
        route="/settings",
        controls=[view_content],
        padding=0,
        appbar=ft.AppBar(
            leading=ft.Container(
                content=ft.IconButton(
                    icon=ft.Icons.ARROW_BACK_ROUNDED,
                    on_click=on_back,
                    icon_size=tokens.ICON_MD,
                    tooltip="Back",
                ),
                padding=ft.Padding(tokens.SPACE_XS, 0, 0, 0),
            ),
            leading_width=48,
            title=ft.Text(
                "Settings",
                size=tokens.FONT_LG,
                weight=ft.FontWeight.W_700,
                color=ft.Colors.ON_SURFACE,
            ),
            center_title=True,
            bgcolor=ft.Colors.TRANSPARENT,
            actions=[theme_btn] if theme_btn else None,
        ),
    )

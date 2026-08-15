"""Display preferences settings section (Light, Dark, System)."""

from __future__ import annotations

import flet as ft

from core import constants, tokens
from core.styles import section_card
from core.theme import AppColors


def build_preferences_section(page: ft.Page, state, services) -> ft.Container:
    def _current_theme_str() -> str:
        if state.theme_mode == ft.ThemeMode.DARK:
            return "dark"
        elif state.theme_mode == ft.ThemeMode.LIGHT:
            return "light"
        return "system"

    cur_theme = _current_theme_str()

    async def _change_theme(mode: str):
        theme_map = {
            "dark": ft.ThemeMode.DARK,
            "light": ft.ThemeMode.LIGHT,
            "system": ft.ThemeMode.SYSTEM,
        }
        m = theme_map.get(mode, ft.ThemeMode.SYSTEM)
        page.theme_mode = m
        state.theme_mode = m
        await services.storage.set(constants.STORAGE_THEME, mode)
        page.update()

    def _theme_card(mode: str, label: str, icon: str):
        is_sel = cur_theme == mode
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(
                        icon,
                        color=AppColors.PRIMARY
                        if is_sel
                        else ft.Colors.ON_SURFACE_VARIANT,
                        size=tokens.ICON_MD,
                    ),
                    ft.Text(
                        label,
                        size=tokens.FONT_XS,
                        weight=ft.FontWeight.W_600 if is_sel else ft.FontWeight.NORMAL,
                        color=AppColors.PRIMARY if is_sel else ft.Colors.ON_SURFACE,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=tokens.SPACE_XS,
            ),
            padding=ft.Padding(
                tokens.SPACE_MD,
                tokens.SPACE_SM,
                tokens.SPACE_MD,
                tokens.SPACE_SM,
            ),
            border_radius=tokens.RADIUS_MD,
            border=ft.Border.all(2, AppColors.PRIMARY)
            if is_sel
            else ft.Border.all(
                1,
                ft.Colors.with_opacity(tokens.OPACITY_CONTAINER, ft.Colors.ON_SURFACE),
            ),
            bgcolor=ft.Colors.with_opacity(tokens.OPACITY_ACCENT, AppColors.PRIMARY)
            if is_sel
            else ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.ON_SURFACE),
            expand=True,
            on_click=lambda e: page.run_task(_change_theme, mode),
            ink=True,
        )

    return section_card(
        "Display Theme",
        ft.Icons.PALETTE_ROUNDED,
        ft.Row(
            controls=[
                _theme_card("light", "Light", ft.Icons.LIGHT_MODE_ROUNDED),
                _theme_card("dark", "Dark", ft.Icons.DARK_MODE_ROUNDED),
                _theme_card(
                    "system",
                    "System",
                    ft.Icons.SETTINGS_SYSTEM_DAYDREAM_ROUNDED,
                ),
            ],
            spacing=tokens.SPACE_SM,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
        page=page,
    )

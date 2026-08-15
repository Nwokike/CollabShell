"""Display preferences settings section (light/dark/system themes)."""

from __future__ import annotations

import flet as ft

from core import constants, tokens
from core.styles import glass_card, section_header


def build_preferences_section(page: ft.Page, state, services) -> ft.Column:
    def _make_theme_btn(label: str, mode: ft.ThemeMode) -> ft.Control:
        is_sel = state.theme_mode == mode

        def _select(e, m=mode):
            page.theme_mode = m
            state.theme_mode = m
            page.run_task(services.storage.set, constants.STORAGE_THEME, label.lower())
            page.update()

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(
                        ft.Icons.LIGHT_MODE_ROUNDED
                        if label == "Light"
                        else ft.Icons.DARK_MODE_ROUNDED
                        if label == "Dark"
                        else ft.Icons.BRIGHTNESS_AUTO_ROUNDED,
                        color=ft.Colors.PRIMARY
                        if is_sel
                        else ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Text(
                        label,
                        size=tokens.FONT_XS,
                        color=ft.Colors.PRIMARY if is_sel else ft.Colors.ON_SURFACE,
                        weight=ft.FontWeight.W_600 if is_sel else ft.FontWeight.NORMAL,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=tokens.SPACE_XXS,
            ),
            expand=True,
            padding=ft.Padding(
                tokens.SPACE_SM,
                tokens.SPACE_MD,
                tokens.SPACE_SM,
                tokens.SPACE_MD,
            ),
            border_radius=tokens.RADIUS_MD,
            bgcolor=ft.Colors.with_opacity(tokens.OPACITY_ACCENT, ft.Colors.PRIMARY)
            if is_sel
            else ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.ON_SURFACE),
            on_click=_select,
            ink=True,
        )

    return ft.Column(
        controls=[
            section_header("PREFERENCES"),
            glass_card(
                ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Icon(
                                    ft.Icons.PALETTE_ROUNDED,
                                    size=tokens.ICON_LG,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            "Display Theme",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        ft.Text(
                                            "Appearance mode",
                                            size=tokens.FONT_XS,
                                            color=ft.Colors.ON_SURFACE_VARIANT,
                                        ),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=tokens.SPACE_LG,
                        ),
                        ft.Container(height=tokens.SPACE_SM),
                        ft.Row(
                            controls=[
                                _make_theme_btn("Light", ft.ThemeMode.LIGHT),
                                _make_theme_btn("Dark", ft.ThemeMode.DARK),
                                _make_theme_btn("System", ft.ThemeMode.SYSTEM),
                            ],
                            spacing=tokens.SPACE_SM,
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    ],
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

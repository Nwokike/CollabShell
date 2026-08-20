"""Display preferences settings section (light/dark/system themes)."""

from __future__ import annotations

import flet as ft

from core import constants, tokens
from core.styles import section_header


def build_preferences_section(page: ft.Page, state, services) -> ft.Control:
    """Appearance section with a compact Light / Dark / System selector.

    Modeled on SpanInsight's appearance_section: three horizontal icon+label
    cards in a single row; the active one gets a light-PRIMARY tint + border.
    """
    current_mode = state.theme_mode or page.theme_mode

    def _select(m: ft.ThemeMode, lbl: str):
        page.theme_mode = m
        state.theme_mode = m
        if services and services.storage:
            page.run_task(services.storage.set, constants.STORAGE_THEME, lbl.lower())
        page.update()

    def _card(mode: ft.ThemeMode, label: str, icon) -> ft.Container:
        is_sel = current_mode == mode
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(
                        icon,
                        size=tokens.ICON_MD,
                        color=ft.Colors.PRIMARY
                        if is_sel
                        else ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Text(
                        label,
                        size=tokens.FONT_SM,
                        weight=ft.FontWeight.W_600 if is_sel else ft.FontWeight.NORMAL,
                        color=ft.Colors.PRIMARY if is_sel else ft.Colors.ON_SURFACE,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=tokens.SPACE_XS,
                tight=True,
            ),
            expand=True,
            padding=ft.Padding(
                tokens.SPACE_MD, tokens.SPACE_SM, tokens.SPACE_MD, tokens.SPACE_SM
            ),
            border_radius=tokens.RADIUS_MD,
            border=ft.Border.all(tokens.DIVIDER_THICKNESS, ft.Colors.PRIMARY)
            if is_sel
            else ft.Border.all(
                tokens.DIVIDER_THICKNESS,
                ft.Colors.with_opacity(tokens.OPACITY_CARD, ft.Colors.ON_SURFACE),
            ),
            bgcolor=ft.Colors.with_opacity(tokens.OPACITY_ACCENT, ft.Colors.PRIMARY)
            if is_sel
            else ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.ON_SURFACE),
            animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
            on_click=lambda e, m=mode, l=label: _select(m, l),
            ink=True,
        )

    return ft.Column(
        controls=[
            section_header("APPEARANCE"),
            ft.Container(
                content=ft.Row(
                    controls=[
                        _card(ft.ThemeMode.LIGHT, "Light", ft.Icons.LIGHT_MODE_ROUNDED),
                        _card(ft.ThemeMode.DARK, "Dark", ft.Icons.DARK_MODE_ROUNDED),
                        _card(
                            ft.ThemeMode.SYSTEM,
                            "System",
                            ft.Icons.BRIGHTNESS_AUTO_ROUNDED,
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                ),
                padding=ft.Padding(
                    tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_SM
                ),
            ),
        ],
        spacing=tokens.SPACE_XS,
    )


__all__ = ["build_preferences_section"]

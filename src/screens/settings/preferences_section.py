"""Display preferences settings section (light/dark/system themes) matching SpanInsight polish."""

from __future__ import annotations

import flet as ft

from core import constants, tokens
from core.styles import glass_card, section_header


@ft.component
def PreferencesSection(page: ft.Page, state, services) -> ft.Control:
    # Local reactive state mirrors state.theme_mode so toggling re-renders immediately.
    current_mode, set_current_mode = ft.use_state(state.theme_mode)

    def _make_theme_btn(label: str, mode: ft.ThemeMode) -> ft.Control:
        is_sel = current_mode == mode

        def _select(e, m=mode, lbl=label):
            page.theme_mode = m
            state.theme_mode = m
            set_current_mode(m)
            page.run_task(
                services.storage.set,
                constants.STORAGE_THEME,
                lbl.lower(),
            )
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
                        size=tokens.ICON_MD,
                    ),
                    ft.Text(
                        label,
                        size=tokens.FONT_SM,
                        color=ft.Colors.PRIMARY if is_sel else ft.Colors.ON_SURFACE,
                        weight=ft.FontWeight.W_600
                        if is_sel
                        else ft.FontWeight.NORMAL,
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
            border=ft.Border.all(2, ft.Colors.PRIMARY)
            if is_sel
            else ft.Border.all(1, ft.Colors.with_opacity(0.12, ft.Colors.ON_SURFACE)),
            bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY)
            if is_sel
            else ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.ON_SURFACE),
            animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
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
                                            "Choose Light, Dark, or System default",
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


def build_preferences_section(page: ft.Page, state, services) -> ft.Control:
    """Shim so settings/__init__.py call signature is unchanged."""
    return PreferencesSection(page=page, state=state, services=services)

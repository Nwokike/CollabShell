import flet as ft
from core import tokens
from core.styles import glass_card, section_header


def build_preferences_section(page: ft.Page, state, storage):
    def create_theme_card(mode: str, label: str, icon: str):
        async def on_click(e):
            state.theme_mode = mode
            await storage.set("theme_mode", mode)
            await change_theme_and_update(mode)

        btn = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(
                        icon, size=tokens.ICON_MD, color=ft.Colors.ON_SURFACE_VARIANT
                    ),
                    ft.Text(label, size=tokens.FONT_XS, weight=ft.FontWeight.W_500),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=tokens.SPACE_XS,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            expand=True,
            on_click=on_click,
            padding=ft.Padding(0, tokens.SPACE_MD, 0, tokens.SPACE_MD),
            border_radius=tokens.RADIUS_MD,
            height=tokens.SPACE_XXXL * 2,
        )
        return btn

    light_btn = create_theme_card("light", "Light", ft.Icons.LIGHT_MODE_ROUNDED)
    dark_btn = create_theme_card("dark", "Dark", ft.Icons.DARK_MODE_ROUNDED)
    system_btn = create_theme_card("system", "System", ft.Icons.BRIGHTNESS_AUTO_ROUNDED)

    async def change_theme_and_update(mode_str):
        if mode_str == "light":
            page.theme_mode = ft.ThemeMode.LIGHT
        elif mode_str == "dark":
            page.theme_mode = ft.ThemeMode.DARK
        else:
            page.theme_mode = ft.ThemeMode.SYSTEM

        for btn, m in [
            (light_btn, "light"),
            (dark_btn, "dark"),
            (system_btn, "system"),
        ]:
            is_sel = m == mode_str
            btn.border = (
                ft.Border.all(2, ft.Colors.PRIMARY)
                if is_sel
                else ft.Border.all(1, ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE))
            )
            btn.bgcolor = (
                ft.Colors.with_opacity(0.1, ft.Colors.PRIMARY)
                if is_sel
                else ft.Colors.with_opacity(0.02, ft.Colors.ON_SURFACE)
            )
            btn.content.controls[0].color = (
                ft.Colors.PRIMARY if is_sel else ft.Colors.ON_SURFACE_VARIANT
            )
            btn.content.controls[1].color = (
                ft.Colors.PRIMARY if is_sel else ft.Colors.ON_SURFACE
            )
            btn.content.controls[1].weight = (
                ft.FontWeight.W_600 if is_sel else ft.FontWeight.NORMAL
            )

        page.update()

    current_mode = state.theme_mode or "system"
    if current_mode == "light":
        page.theme_mode = ft.ThemeMode.LIGHT
    elif current_mode == "dark":
        page.theme_mode = ft.ThemeMode.DARK
    else:
        page.theme_mode = ft.ThemeMode.SYSTEM

    for btn, m in [(light_btn, "light"), (dark_btn, "dark"), (system_btn, "system")]:
        is_sel = m == current_mode
        btn.border = (
            ft.Border.all(2, ft.Colors.PRIMARY)
            if is_sel
            else ft.Border.all(1, ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE))
        )
        btn.bgcolor = (
            ft.Colors.with_opacity(0.1, ft.Colors.PRIMARY)
            if is_sel
            else ft.Colors.with_opacity(0.02, ft.Colors.ON_SURFACE)
        )
        btn.content.controls[0].color = (
            ft.Colors.PRIMARY if is_sel else ft.Colors.ON_SURFACE_VARIANT
        )
        btn.content.controls[1].color = (
            ft.Colors.PRIMARY if is_sel else ft.Colors.ON_SURFACE
        )
        btn.content.controls[1].weight = (
            ft.FontWeight.W_600 if is_sel else ft.FontWeight.NORMAL
        )

    preferences_section = ft.Column(
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
                            [light_btn, dark_btn, system_btn],
                            spacing=tokens.SPACE_SM,
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    ],
                ),
                margin=ft.Margin(
                    tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
                ),
            ),
        ],
        spacing=0,
    )
    return preferences_section

import flet as ft

from components.brand_header import build_brand_header
from core import constants, tokens
from core.styles import glass_card, section_header, tip_text


def build_behavior_section(page: ft.Page, state, storage):
    async def _on_keep_alive_change(e):
        state.keep_alive_enabled = e.control.value
        await storage.set(constants.STORAGE_KEEP_ALIVE, state.keep_alive_enabled)

    async def _on_keep_alive_disconnect_change(e):
        state.keep_alive_on_disconnect = e.control.value
        await storage.set(
            constants.STORAGE_KEEP_ALIVE_ON_DISCONNECT, state.keep_alive_on_disconnect
        )

    async def _on_drive_path_change(e):
        state.drive_mount_path = e.control.value
        await storage.set(constants.STORAGE_DRIVE_MOUNT_PATH, state.drive_mount_path)

    behavior_section = ft.Column(
        controls=[
            section_header("SESSION BEHAVIOR"),
            glass_card(
                ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            "Keep-Alive",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        tip_text(constants.TIP_KEEP_ALIVE),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                                ft.Switch(
                                    value=state.keep_alive_enabled,
                                    on_change=lambda e: page.run_task(
                                        _on_keep_alive_change, e
                                    ),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        ft.Row(
                            controls=[
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            "Keep Alive on Disconnect",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        tip_text(
                                            "Keep sessions running when the app closes and you close all session pages"
                                        ),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                                ft.Switch(
                                    value=state.keep_alive_on_disconnect,
                                    on_change=lambda e: page.run_task(
                                        _on_keep_alive_disconnect_change, e
                                    ),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        ft.TextField(
                            value=state.drive_mount_path,
                            label="Drive Mount Path",
                            prefix_icon=ft.Icons.ADD_TO_DRIVE_ROUNDED,
                            border_radius=tokens.RADIUS_MD,
                            text_size=tokens.FONT_SM,
                            on_blur=lambda e: page.run_task(_on_drive_path_change, e),
                        ),
                        tip_text(constants.TIP_DRIVE_MOUNT),
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
    return behavior_section


def build_advanced_section(page: ft.Page, state, storage):
    async def _on_logtostderr_change(e):
        state.logtostderr = e.control.value
        await storage.set(constants.STORAGE_LOGTOSTDERR, state.logtostderr)

    advanced_section = ft.Column(
        controls=[
            section_header("ADVANCED"),
            glass_card(
                ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            "Log to Stderr",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        tip_text(
                                            "Debug: route all CLI output to stderr"
                                        ),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                                ft.Switch(
                                    value=state.logtostderr,
                                    on_change=lambda e: page.run_task(
                                        _on_logtostderr_change, e
                                    ),
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
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
    return advanced_section


def build_about_section():
    about_section = ft.Column(
        controls=[
            section_header("ABOUT"),
            glass_card(
                ft.Column(
                    controls=[
                        ft.Container(
                            content=build_brand_header(
                                show_tagline=True, spacing_below=False
                            ),
                            opacity=0.8,
                        ),
                        ft.Divider(height=tokens.SPACE_SM),
                        ft.Row(
                            controls=[
                                ft.Text(
                                    "Core Engine",
                                    size=tokens.FONT_SM,
                                ),
                                ft.Text(
                                    "google-colab-cli",
                                    size=tokens.FONT_SM,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Text(
                            "Disclaimer: Unofficial client application. Not affiliated with, authorized, sponsored, or endorsed by Google LLC.",
                            size=tokens.FONT_XXS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            italic=True,
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
    return about_section

"""Session behavior settings section."""

from __future__ import annotations

import flet as ft

from core import constants, tokens
from core.styles import glass_card, section_header, tip_text


def build_behavior_section(page: ft.Page, state, services) -> ft.Column:
    async def _on_keep_alive_change(e):
        state.keep_alive_enabled = e.control.value
        await services.storage.set(
            constants.STORAGE_KEEP_ALIVE, str(e.control.value).lower()
        )

    async def _on_keep_alive_disconnect_change(e):
        state.keep_alive_on_disconnect = e.control.value
        await services.storage.set(
            constants.STORAGE_KEEP_ALIVE_ON_DISCONNECT,
            str(e.control.value).lower(),
        )

    async def _on_drive_path_change(e):
        state.drive_mount_path = e.control.value
        await services.storage.set(
            constants.STORAGE_DRIVE_MOUNT_PATH, state.drive_mount_path
        )

    return ft.Column(
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
                                            "Keep sessions running when the app closes"
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
                    tokens.SPACE_LG,
                    tokens.SPACE_XS,
                    tokens.SPACE_LG,
                    tokens.SPACE_XS,
                ),
            ),
        ],
        spacing=0,
    )

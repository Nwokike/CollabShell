"""Session behavior settings section."""

from __future__ import annotations

import flet as ft

from core import constants, tokens
from core.styles import glass_card, section_header, tip_text


def build_behavior_section(page: ft.Page, state, services) -> ft.Column:
    async def _on_auto_stop_change(e):
        # Inverted copy: the switch shows "auto-stop", the flag stores
        # "keep alive on disconnect" (default True = sessions survive).
        state.keep_alive_on_disconnect = not e.control.value
        await services.storage.set(
            constants.STORAGE_KEEP_ALIVE_ON_DISCONNECT,
            str(state.keep_alive_on_disconnect).lower(),
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
                                            "Auto-stop sessions on exit",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        tip_text(
                                            "Stop all sessions when the app closes "
                                            "or disconnects. Off by default — "
                                            "sessions survive."
                                        ),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                                ft.Switch(
                                    value=not state.keep_alive_on_disconnect,
                                    on_change=lambda e: page.run_task(
                                        _on_auto_stop_change, e
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
                            border=ft.OutlineInputBorder(
                                border_radius=tokens.RADIUS_MD
                            ),
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

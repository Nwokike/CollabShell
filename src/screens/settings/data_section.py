"""Data & storage settings section with Clear Local Data confirmation dialog."""

from __future__ import annotations

import flet as ft

from core import constants, tokens
from core.notifications import show_notification
from core.styles import glass_card, section_header, tip_text


def build_data_section(page: ft.Page, state, services) -> ft.Column:
    """Build the Data & Storage settings section with cache reset."""

    def _open_clear_data_dialog(e=None):
        def _close(e=None):
            page.pop_dialog()

        async def _do_clear():
            page.pop_dialog()
            try:
                # Delete local preferences without wiping Google credentials
                for key in [
                    constants.STORAGE_THEME,
                    constants.STORAGE_DEFAULT_GPU,
                    constants.STORAGE_DEFAULT_TPU,
                    constants.STORAGE_DEFAULT_TIMEOUT,
                    constants.STORAGE_KEEP_ALIVE,
                    constants.STORAGE_KEEP_ALIVE_ON_DISCONNECT,
                    constants.STORAGE_LOG_FORMAT,
                    constants.STORAGE_LOGTOSTDERR,
                    constants.STORAGE_DRIVE_MOUNT_PATH,
                ]:
                    try:
                        await services.storage.delete(key)
                    except Exception:
                        pass

                show_notification(page, "✅ Local preferences and cache cleared.")
            except Exception as ex:
                show_notification(page, f"❌ Clear failed: {ex}", is_error=True)

        dialog = ft.AlertDialog(
            title=ft.Text("Clear All Local Data?"),
            content=ft.Text(
                "This will reset saved preferences, timeout, and hardware defaults. "
                "Your Google account authentication and active Colab sessions will not be affected.",
                size=tokens.FONT_SM,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=_close),
                ft.FilledButton(
                    "Clear",
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.ERROR,
                        color=ft.Colors.WHITE,
                    ),
                    on_click=lambda e: page.run_task(_do_clear),
                ),
            ],
        )
        page.show_dialog(dialog)

    return ft.Column(
        controls=[
            section_header("DATA & STORAGE"),
            glass_card(
                ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Icon(
                                    ft.Icons.DELETE_SWEEP_ROUNDED,
                                    size=tokens.ICON_LG,
                                    color=ft.Colors.ERROR,
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text(
                                            "Clear Local Data",
                                            size=tokens.FONT_MD,
                                            weight=ft.FontWeight.W_500,
                                        ),
                                        tip_text(
                                            "Reset local preferences, cache, and hardware defaults"
                                        ),
                                    ],
                                    spacing=tokens.SPACE_XXS,
                                    expand=True,
                                ),
                                ft.OutlinedButton(
                                    "Clear",
                                    style=ft.ButtonStyle(color=ft.Colors.ERROR),
                                    on_click=_open_clear_data_dialog,
                                ),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=tokens.SPACE_LG,
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

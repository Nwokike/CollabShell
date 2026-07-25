"""Activity Terminal section for Settings — live activity log viewer and clipboard copy."""

from __future__ import annotations
import flet as ft
from core import tokens
from core.theme import AppColors
from core.styles import glass_card, section_header


def get_live_logs() -> str:
    """Retrieve combined live in-memory and disk log contents."""
    from core.storage_patch import MemoryLogHandler

    memory_logs = MemoryLogHandler.get_logs()
    if memory_logs:
        return "\n".join(memory_logs)

    import os
    from services.storage_service import get_storage_dir

    log_file = os.path.join(get_storage_dir(), "colab.log")
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                return "".join(lines[-200:])
        except Exception:
            pass
    return "No activity logs recorded yet."


def build_logs_dialog(page: ft.Page) -> ft.AlertDialog:
    """Build modal AlertDialog containing live activity log terminal."""
    log_text = get_live_logs()

    log_control = ft.Text(
        value=log_text,
        size=tokens.FONT_XS,
        font_family="JetBrains Mono",
        color="#A6ADC8",
        selectable=True,
    )

    async def _copy_logs(e):
        try:
            await page.set_clipboard(log_control.value)
            page.show_dialog(
                ft.SnackBar(
                    content=ft.Text("Activity logs copied to clipboard"),
                    bgcolor=AppColors.SUCCESS,
                )
            )
        except Exception:
            pass

    return ft.AlertDialog(
        modal=True,
        title=ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.TERMINAL_ROUNDED,
                    size=tokens.ICON_MD,
                    color=ft.Colors.PRIMARY,
                ),
                ft.Text(
                    "Activity Terminal",
                    size=tokens.FONT_LG,
                    weight=ft.FontWeight.BOLD,
                ),
            ],
            spacing=tokens.SPACE_SM,
        ),
        content=ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(
                        "Real-time log of sessions, websocket activity, and connection events. Copy to share for troubleshooting.",
                        size=tokens.FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Container(
                        content=ft.Column(
                            controls=[log_control],
                            scroll=ft.ScrollMode.AUTO,
                            expand=True,
                        ),
                        padding=tokens.SPACE_MD,
                        bgcolor="#0D0D0D",
                        border=ft.Border.all(
                            1, ft.Colors.with_opacity(0.15, ft.Colors.WHITE)
                        ),
                        border_radius=tokens.RADIUS_SM,
                        expand=True,
                    ),
                ],
                spacing=tokens.SPACE_SM,
            ),
            width=min(page.window.width * 0.9 if page.window.width else 450, 500),
            height=400,
        ),
        actions=[
            ft.IconButton(
                icon=ft.Icons.COPY_ROUNDED,
                tooltip="Copy Logs to Clipboard",
                on_click=lambda e: page.run_task(_copy_logs, e),
            ),
            ft.TextButton("Close", on_click=lambda e: page.pop_dialog()),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )


def build_logs_section(page: ft.Page) -> ft.Column:
    """Build Settings section card for Activity Terminal troubleshooting."""
    card = glass_card(
        ft.Column(
            controls=[
                ft.Text(
                    "Live Activity Terminal",
                    size=tokens.FONT_MD,
                    weight=ft.FontWeight.W_600,
                ),
                ft.Text(
                    "View real-time connection activity, session logs, and diagnostic errors. Useful for troubleshooting on mobile.",
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.FilledButton(
                    "Open Terminal",
                    icon=ft.Icons.TERMINAL_ROUNDED,
                    on_click=lambda e: page.show_dialog(build_logs_dialog(page)),
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.PRIMARY,
                        color=ft.Colors.WHITE,
                        shape=ft.RoundedRectangleBorder(radius=tokens.RADIUS_SM),
                    ),
                ),
            ],
            spacing=tokens.SPACE_SM,
        )
    )
    return ft.Column(
        controls=[
            section_header("TROUBLESHOOTING & LOGS"),
            card,
        ],
        spacing=tokens.SPACE_XS,
    )

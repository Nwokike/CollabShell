"""Activity Terminal logs troubleshooting section and modal dialog."""

from __future__ import annotations

import logging
import os

import flet as ft

from core import tokens
from core.storage_patch import MemoryLogHandler, resolve_storage_dir
from core.styles import glass_card, section_header
from core.theme import AppColors

logger = logging.getLogger(__name__)


def build_logs_dialog(page: ft.Page) -> ft.AlertDialog:
    memory_logs = MemoryLogHandler.get_logs()
    if memory_logs:
        log_text = "\n".join(memory_logs)
    else:
        log_file = os.path.join(resolve_storage_dir(), "colab.log")
        if os.path.exists(log_file):
            try:
                with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                    log_text = "".join(f.readlines()[-200:])
            except Exception:
                log_text = "Could not read log file."
        else:
            log_text = "No activity logs recorded yet."

    log_control = ft.Text(
        value=log_text,
        size=tokens.FONT_XS,
        font_family="RobotoMono",
        color=AppColors.TERMINAL_GREEN,
        selectable=True,
    )

    async def _copy(e):
        try:
            await ft.Clipboard().set(log_control.value)
            from core.notifications import show_notification

            show_notification(page, "Logs copied to clipboard")
        except Exception:
            logger.exception("Suppressed exception")

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
                        "Real-time log of sessions, websocket activity, and connection events.",
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
                        bgcolor=AppColors.LOG_TERMINAL_BG,
                        border=ft.Border.all(
                            1,
                            ft.Colors.with_opacity(
                                tokens.OPACITY_ACCENT, ft.Colors.WHITE
                            ),
                        ),
                        border_radius=tokens.RADIUS_SM,
                        expand=True,
                    ),
                ],
                spacing=tokens.SPACE_SM,
            ),
            width=tokens.DIALOG_WIDTH_LG,
            height=tokens.DIALOG_HEIGHT_LG,
        ),
        actions=[
            ft.IconButton(
                icon=ft.Icons.COPY_ROUNDED,
                tooltip="Copy logs",
                on_click=lambda e: page.run_task(_copy, e),
            ),
            ft.TextButton("Close", on_click=lambda e: page.pop_dialog()),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )


def build_logs_section(page: ft.Page, state, services) -> ft.Column:
    return ft.Column(
        controls=[
            section_header("TROUBLESHOOTING & LOGS"),
            glass_card(
                ft.Column(
                    controls=[
                        ft.Text(
                            "Live Activity Terminal",
                            size=tokens.FONT_MD,
                            weight=ft.FontWeight.W_500,
                        ),
                        ft.Text(
                            "View real-time connection activity, session logs, and diagnostic errors.",
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Container(height=tokens.SPACE_XS),
                        ft.FilledButton(
                            "Open Terminal",
                            icon=ft.Icons.TERMINAL_ROUNDED,
                            on_click=lambda e: page.show_dialog(
                                build_logs_dialog(page)
                            ),
                        ),
                    ],
                    spacing=tokens.SPACE_XS,
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

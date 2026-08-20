"""VM operations for Colab sessions (mount drive, auth GCP, restart, stop)."""

from __future__ import annotations

import asyncio
import logging

import flet as ft

from core import tokens
from core.theme import AppColors

logger = logging.getLogger("colab")


def _close_active_auth(page: ft.Page):
    try:
        page.pop_dialog()
    except Exception:
        pass


async def on_mount_drive(
    page: ft.Page,
    session_name: str,
    colab_service,
    state,
    snack=None,
    stdin_hook=None,
):
    dialog = ft.AlertDialog(
        title=ft.Text("Mounting Google Drive..."),
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.ProgressRing(
                            width=tokens.SPINNER_MD,
                            height=tokens.SPINNER_MD,
                            stroke_width=3,
                        ),
                        ft.Text(
                            "Initiating mount on virtual machine...",
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.W_500,
                        ),
                    ],
                    spacing=tokens.SPACE_MD,
                ),
                ft.Text(
                    "Please wait while Colab checks or mounts your Google Drive...",
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            tight=True,
            spacing=tokens.SPACE_SM,
        ),
        actions=[ft.TextButton("Cancel", on_click=lambda e: _close_active_auth(page))],
        modal=True,
    )
    page.show_dialog(dialog)

    def _output_handler(out):
        if snack:
            msg = out if isinstance(out, str) else out.get("text", "")
            msg = msg.strip()
            if msg:
                line = msg.split("\n")[-1] if "\n" in msg else msg
                page.loop.call_soon_threadsafe(snack, f"Drive: {line[:120]}")

    try:
        ok = await colab_service.mount_drive(
            session_name,
            path=state.drive_mount_path,
            auth_method=state.auth_method,
            on_output=_output_handler,
            stdin_hook=stdin_hook,
        )
        if not ok:
            raise RuntimeError(
                "Drive mount did not complete. Check authorization and retry."
            )
        if dialog.open:
            dialog.title = ft.Text("Success")
            dialog.content = ft.Row(
                [
                    ft.Icon(
                        ft.Icons.CHECK_CIRCLE_ROUNDED,
                        color=AppColors.SUCCESS,
                        size=tokens.ICON_LG,
                    ),
                    ft.Text(
                        f"Drive mounted at {state.drive_mount_path}",
                        size=tokens.FONT_SM,
                        weight=ft.FontWeight.BOLD,
                    ),
                ],
                spacing=tokens.SPACE_SM,
            )
            dialog.actions = [
                ft.FilledButton("Done", on_click=lambda e: _close_active_auth(page))
            ]
            dialog.update()

            async def _auto_close():
                await asyncio.sleep(1.5)
                _close_active_auth(page)

            page.run_task(_auto_close)
    except Exception as ex:
        logger.exception("Mount Drive failed")
        if dialog.open:
            dialog.title = ft.Text("Failed")
            dialog.content = ft.Row(
                [
                    ft.Icon(
                        ft.Icons.ERROR_ROUNDED,
                        color=AppColors.ERROR,
                        size=tokens.ICON_LG,
                    ),
                    ft.Text(f"Error: {ex}", size=tokens.FONT_SM),
                ],
                spacing=tokens.SPACE_SM,
            )
            dialog.actions = [
                ft.FilledButton("Close", on_click=lambda e: _close_active_auth(page))
            ]
            dialog.update()


async def on_auth_gcp(
    page: ft.Page,
    session_name: str,
    colab_service,
    state,
    snack=None,
    stdin_hook=None,
):
    dialog = ft.AlertDialog(
        title=ft.Text("Authenticating GCP..."),
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.ProgressRing(
                            width=tokens.SPINNER_MD,
                            height=tokens.SPINNER_MD,
                            stroke_width=3,
                        ),
                        ft.Text(
                            "Initiating GCP auth on virtual machine...",
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.W_500,
                        ),
                    ],
                    spacing=tokens.SPACE_MD,
                ),
                ft.Text(
                    "Please wait while Colab checks or sets up your credentials...",
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            tight=True,
            spacing=tokens.SPACE_SM,
        ),
        actions=[ft.TextButton("Cancel", on_click=lambda e: _close_active_auth(page))],
        modal=True,
    )
    page.show_dialog(dialog)

    def _output_handler(out):
        if snack:
            msg = out if isinstance(out, str) else out.get("text", "")
            msg = msg.strip()
            if msg:
                line = msg.split("\n")[-1] if "\n" in msg else msg
                page.loop.call_soon_threadsafe(snack, f"Auth GCP: {line[:120]}")

    try:
        ok = await colab_service.auth_gcp_on_vm(
            session_name,
            auth_method=state.auth_method,
            on_output=_output_handler,
            stdin_hook=stdin_hook,
        )
        if not ok:
            raise RuntimeError("GCP authentication did not complete. Retry.")
        if dialog.open:
            dialog.title = ft.Text("Success")
            dialog.content = ft.Row(
                [
                    ft.Icon(
                        ft.Icons.CHECK_CIRCLE_ROUNDED,
                        color=AppColors.SUCCESS,
                        size=tokens.ICON_LG,
                    ),
                    ft.Text(
                        "GCP authenticated successfully on VM",
                        size=tokens.FONT_SM,
                        weight=ft.FontWeight.BOLD,
                    ),
                ],
                spacing=tokens.SPACE_SM,
            )
            dialog.actions = [
                ft.FilledButton("Done", on_click=lambda e: _close_active_auth(page))
            ]
            dialog.update()

            async def _auto_close():
                await asyncio.sleep(1.5)
                _close_active_auth(page)

            page.run_task(_auto_close)
    except Exception as ex:
        logger.exception("Auth GCP failed")
        if dialog.open:
            dialog.title = ft.Text("Failed")
            dialog.content = ft.Row(
                [
                    ft.Icon(
                        ft.Icons.ERROR_ROUNDED,
                        color=AppColors.ERROR,
                        size=tokens.ICON_LG,
                    ),
                    ft.Text(f"Error: {ex}", size=tokens.FONT_SM),
                ],
                spacing=tokens.SPACE_SM,
            )
            dialog.actions = [
                ft.FilledButton("Close", on_click=lambda e: _close_active_auth(page))
            ]
            dialog.update()

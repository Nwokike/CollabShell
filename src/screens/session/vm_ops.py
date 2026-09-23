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
        logger.exception("Suppressed exception")


def _finish(page: ft.Page, progress: ft.AlertDialog, ok: bool, message: str):
    """Show the outcome of a VM operation.

    Morphs the live progress dialog when it is still open; if it yielded to
    a sign-in prompt (and was popped), shows a fresh dialog instead.
    """
    title = "Success" if ok else "Failed"
    icon = ft.Icons.CHECK_CIRCLE_ROUNDED if ok else ft.Icons.ERROR_ROUNDED
    color = AppColors.SUCCESS if ok else AppColors.ERROR
    content = ft.Row(
        [
            ft.Icon(icon, color=color, size=tokens.ICON_LG),
            ft.Text(message, size=tokens.FONT_SM, weight=ft.FontWeight.BOLD),
        ],
        spacing=tokens.SPACE_SM,
    )

    def _close(e=None):
        _close_active_auth(page)

    actions = [ft.FilledButton("Done" if ok else "Close", on_click=_close)]

    if progress.open:
        progress.title = ft.Text(title)
        progress.content = content
        progress.actions = actions
        progress.update()
    else:
        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text(title), content=content, actions=actions, modal=True
            )
        )

    if ok:

        async def _auto_close():
            await asyncio.sleep(1.5)
            _close_active_auth(page)

        page.run_task(_auto_close)


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
        _finish(page, dialog, True, f"Drive mounted at {state.drive_mount_path}")
    except Exception as ex:
        logger.exception("Mount Drive failed")
        _finish(page, dialog, False, f"Error: {ex}")


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
        _finish(page, dialog, True, "GCP authenticated successfully on VM")
    except Exception as ex:
        logger.exception("Auth GCP failed")
        _finish(page, dialog, False, f"Error: {ex}")

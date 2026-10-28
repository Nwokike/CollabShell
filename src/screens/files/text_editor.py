"""Shared editor for small UTF-8 files in the remote Colab filesystem."""

from __future__ import annotations

import logging

import flet as ft

from core import tokens
from core.notifications import show_notification
from services.colab.text_files import download_text_file, upload_text_file

logger = logging.getLogger("RemoteTextEditor")


def is_python_file(name: str) -> bool:
    return name.lower().endswith(".py")


async def open_text_file_editor(
    page: ft.Page,
    colab_service,
    session_name: str,
    auth_method: str,
    remote_path: str,
) -> None:
    try:
        text = await download_text_file(
            colab_service,
            remote_path,
            session_name=session_name,
            auth_method=auth_method,
        )
    except Exception as ex:
        logger.warning("Could not open remote text file %s: %s", remote_path, ex)
        show_notification(page, f"Could not open {remote_path}: {ex}", is_error=True)
        return

    editor = ft.TextField(
        value=text,
        multiline=True,
        min_lines=16,
        max_lines=32,
        text_style=ft.TextStyle(font_family="RobotoMono", size=tokens.FONT_SM),
        border=ft.OutlineInputBorder(border_radius=tokens.RADIUS_MD),
        expand=True,
    )
    is_saving = False

    async def _save(e=None):
        nonlocal is_saving
        if is_saving:
            return
        is_saving = True
        save_button.disabled = True
        page.update()
        try:
            await upload_text_file(
                colab_service,
                remote_path,
                editor.value or "",
                session_name=session_name,
                auth_method=auth_method,
            )
            page.pop_dialog()
            show_notification(page, f"Saved {remote_path}")
        except Exception as ex:
            logger.warning("Could not save remote text file %s: %s", remote_path, ex)
            show_notification(
                page, f"Could not save {remote_path}: {ex}", is_error=True
            )
        finally:
            is_saving = False
            save_button.disabled = False
            page.update()

    save_button = ft.FilledButton(
        "Save to Colab",
        icon=ft.Icons.CLOUD_UPLOAD_ROUNDED,
        on_click=lambda e: page.run_task(_save, e),
    )
    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(remote_path, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
        content=ft.Container(
            content=editor,
            width=tokens.DIALOG_WIDTH_LG,
            height=tokens.DIALOG_HEIGHT_LG,
        ),
        actions=[
            ft.TextButton("Cancel", on_click=lambda e: page.pop_dialog()),
            save_button,
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dialog)

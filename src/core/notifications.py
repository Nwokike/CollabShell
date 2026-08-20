"""Notification utilities using floating SnackBar overlay pattern (matching KTV Player standard)."""

from __future__ import annotations

import logging

import flet as ft

from core.theme import AppColors

logger = logging.getLogger("notifications")


def show_notification(
    page: ft.Page | None,
    message: str,
    is_error: bool = False,
    is_warning: bool = False,
    is_success: bool = False,
    persist: bool = False,
) -> None:
    """Show a floating SnackBar on page.overlay."""
    if not page:
        return

    if is_error:
        bgcolor = AppColors.ERROR
    elif is_warning:
        bgcolor = AppColors.WARNING
    elif is_success:
        bgcolor = AppColors.SUCCESS
    else:
        # Never leave bgcolor None: the SnackBar then falls back to the
        # theme's inverseSurface while ON_SURFACE text stays same-tone,
        # producing black-on-black (light mode) / white-on-white (dark).
        bgcolor = AppColors.DARK_BG

    try:
        snack = ft.SnackBar(
            content=ft.Text(message, color=ft.Colors.WHITE),
            bgcolor=bgcolor,
            show_close_icon=True,
            behavior=ft.SnackBarBehavior.FLOATING,
            dismiss_direction=ft.DismissDirection.HORIZONTAL,
            duration=3000 if not persist else None,
            open=True,
        )
        page.overlay.append(snack)
        page.update()
    except Exception as ex:
        logger.warning("Failed to show floating notification: %s", ex)


__all__ = ["show_notification"]

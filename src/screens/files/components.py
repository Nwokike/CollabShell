"""Filesystem UI components: breadcrumbs, empty state, and size formatter."""

from __future__ import annotations

import posixpath

import flet as ft

from core import tokens


def parent_path(path: str) -> str | None:
    """Parent directory of `path`, or None when already at filesystem root."""
    norm = posixpath.normpath(path or "/")
    if norm == "/":
        return None
    parent = posixpath.dirname(norm)
    return parent if parent else "/"


def fmt_size(size_bytes: float | None) -> str:
    """Format file bytes into human-readable B / KB / MB string."""
    if size_bytes is None:
        return ""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def build_empty_dir_view(on_upload) -> ft.Control:
    """Centered placeholder when current directory has zero files."""
    return ft.Container(
        content=ft.Column(
            [
                ft.Icon(
                    ft.Icons.FOLDER_OPEN_ROUNDED,
                    size=tokens.ICON_XXL,
                    color=ft.Colors.with_opacity(0.3, ft.Colors.ON_SURFACE),
                ),
                ft.Text(
                    "Empty directory",
                    size=tokens.FONT_MD,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    weight=ft.FontWeight.W_500,
                ),
                ft.Text(
                    "No files or folders found in this location",
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Container(height=tokens.SPACE_XS),
                ft.FilledTonalButton(
                    "Upload a file",
                    icon=ft.Icons.UPLOAD_ROUNDED,
                    on_click=on_upload,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=tokens.SPACE_SM,
        ),
        alignment=ft.Alignment.CENTER,
        padding=tokens.SPACE_XXL,
        expand=True,
    )


def build_breadcrumbs(path: str, on_navigate) -> ft.Control:
    """Interactive POSIX directory path breadcrumbs with chevrons.

    The root crumb navigates to the true filesystem root ("/") so users can
    browse above /content (the ColabService.ls backend supports any path).
    """
    norm = posixpath.normpath(path or "/")
    parts = [p for p in norm.split("/") if p]
    at_root = not parts
    root_crumb: ft.Control = (
        ft.Text(
            "/",
            size=tokens.FONT_SM,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.ON_SURFACE,
        )
        if at_root
        else ft.TextButton(
            "/",
            on_click=lambda e: on_navigate("/"),
            style=ft.ButtonStyle(
                padding=ft.Padding(4, 2, 4, 2),
                color=ft.Colors.PRIMARY,
            ),
        )
    )
    crumbs = [root_crumb]
    built = ""
    for i, part in enumerate(parts):
        built += f"/{part}"
        captured = built
        is_last = i == len(parts) - 1
        crumbs.append(
            ft.Icon(
                ft.Icons.CHEVRON_RIGHT_ROUNDED,
                size=tokens.ICON_SM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        )
        if is_last:
            crumbs.append(
                ft.Text(
                    part,
                    size=tokens.FONT_SM,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.ON_SURFACE,
                )
            )
        else:
            crumbs.append(
                ft.TextButton(
                    part,
                    on_click=lambda e, p=captured: on_navigate(p),
                    style=ft.ButtonStyle(
                        padding=ft.Padding(4, 2, 4, 2),
                        color=ft.Colors.PRIMARY,
                    ),
                )
            )
    return ft.Row(controls=crumbs, spacing=0, scroll=ft.ScrollMode.AUTO)

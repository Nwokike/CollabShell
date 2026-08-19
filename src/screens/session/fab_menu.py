"""Floating Action Button and overflow menu for the Session screen.

Ported from SpanInsight's screens/analysis/fab_menu.py — a mini FAB wrapping a
PopupMenuButton so notebook actions and Manage Files are reachable from both
the Notebook and Terminal tabs.
"""

from __future__ import annotations

import flet as ft

from core import tokens


def build_session_fab(
    has_session: bool = True,
    has_cells: bool = False,
    on_export_ipynb=None,
    on_import_ipynb=None,
    on_clear_all=None,
    on_manage_files=None,
) -> ft.FloatingActionButton | None:
    """Constructs the floating action button with contextual popup menu items."""
    if not has_session:
        return None

    menu_items = []
    if has_cells:
        menu_items.extend(
            [
                ft.PopupMenuItem(
                    content="Export .ipynb",
                    icon=ft.Icons.DOWNLOAD_ROUNDED,
                    on_click=on_export_ipynb,
                ),
                ft.PopupMenuItem(
                    content="Import .ipynb",
                    icon=ft.Icons.UPLOAD_FILE_ROUNDED,
                    on_click=on_import_ipynb,
                ),
                ft.PopupMenuItem(
                    content="Clear All Outputs",
                    icon=ft.Icons.DELETE_SWEEP_ROUNDED,
                    on_click=on_clear_all,
                ),
            ]
        )
    menu_items.append(
        ft.PopupMenuItem(
            content="Manage Files",
            icon=ft.Icons.FOLDER_ROUNDED,
            on_click=on_manage_files,
        )
    )

    return ft.FloatingActionButton(
        content=ft.PopupMenuButton(
            items=menu_items,
            icon=ft.Icons.MORE_VERT_ROUNDED,
            icon_color=ft.Colors.WHITE,
            icon_size=tokens.ICON_MD,
        ),
        bgcolor=ft.Colors.PRIMARY,
        mini=True,
    )

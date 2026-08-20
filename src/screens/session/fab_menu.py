"""Floating Action Button and overflow menu for the Session screen.

A mini FAB wrapping a PopupMenuButton (SpanInsight pattern). The menu is
context-aware: notebook actions on the Notebook tab, terminal actions on the
Terminal tab, with shared session actions (Manage Files, Restart, Stop) on
both — replacing the old bottom action row.
"""

from __future__ import annotations

import flet as ft

from core import tokens


def _item(content: str, icon, on_click, checked: bool | None = None) -> ft.PopupMenuItem:
    return ft.PopupMenuItem(content=content, icon=icon, on_click=on_click, checked=checked)


def _header(label: str) -> ft.PopupMenuItem:
    return ft.PopupMenuItem(
        content=ft.Text(label, weight=ft.FontWeight.BOLD), disabled=True
    )


def build_session_fab(
    mode: str = "notebook",
    has_session: bool = True,
    has_cells: bool = False,
    # Notebook actions
    on_export_ipynb=None,
    on_import_ipynb=None,
    on_clear_all=None,
    # Shared session actions
    on_manage_files=None,
    on_mount_drive=None,
    on_auth_gcp=None,
    on_open_browser=None,
    on_view_logs=None,
    on_restart=None,
    on_stop=None,
    # Terminal actions
    on_new_terminal=None,
    on_clear_terminal=None,
    on_copy=None,
    on_paste=None,
    # Terminal settings (FAB inherits the flet_terminal settings menu)
    term_settings: dict | None = None,
    on_term_theme=None,
    on_term_cursor=None,
    on_term_zoom_in=None,
    on_term_zoom_out=None,
    on_term_zoom_reset=None,
    on_term_toggle_blink=None,
    on_term_toggle_search=None,
) -> ft.FloatingActionButton | None:
    """Constructs the floating action button with contextual popup menu items."""
    if not has_session:
        return None

    menu_items: list[ft.PopupMenuItem] = []

    if mode == "terminal":
        ts = term_settings or {}
        menu_items.extend(
            [
                _item("New Terminal", ft.Icons.ADD_ROUNDED, on_new_terminal),
                _item("Copy Selection", ft.Icons.COPY_ALL_ROUNDED, on_copy),
                _item("Paste", ft.Icons.CONTENT_PASTE_ROUNDED, on_paste),
                _item("Clear Terminal", ft.Icons.CLEAR_ALL_ROUNDED, on_clear_terminal),
                ft.PopupMenuItem(),
                _header("Theme Presets"),
                _item(
                    "Dracula",
                    ft.Icons.PALETTE_ROUNDED,
                    lambda e: on_term_theme("Dracula") if on_term_theme else None,
                    ts.get("theme") == "Dracula",
                ),
                _item(
                    "JetBrains Dark",
                    ft.Icons.PALETTE_ROUNDED,
                    lambda e: (
                        on_term_theme("JetBrains Dark") if on_term_theme else None
                    ),
                    ts.get("theme") == "JetBrains Dark",
                ),
                _item(
                    "Matrix Green",
                    ft.Icons.PALETTE_ROUNDED,
                    lambda e: (
                        on_term_theme("Matrix Green") if on_term_theme else None
                    ),
                    ts.get("theme") == "Matrix Green",
                ),
                _item(
                    "Colab Light",
                    ft.Icons.PALETTE_ROUNDED,
                    lambda e: on_term_theme("Colab Light") if on_term_theme else None,
                    ts.get("theme") == "Colab Light",
                ),
                ft.PopupMenuItem(),
                _header("Cursor Style"),
                _item(
                    "Block",
                    ft.Icons.TEXT_FIELDS_ROUNDED,
                    lambda e: on_term_cursor("block") if on_term_cursor else None,
                    ts.get("cursor") == "block",
                ),
                _item(
                    "Underline",
                    ft.Icons.TEXT_FIELDS_ROUNDED,
                    lambda e: on_term_cursor("underline") if on_term_cursor else None,
                    ts.get("cursor") == "underline",
                ),
                _item(
                    "Bar",
                    ft.Icons.TEXT_FIELDS_ROUNDED,
                    lambda e: on_term_cursor("bar") if on_term_cursor else None,
                    ts.get("cursor") == "bar",
                ),
                ft.PopupMenuItem(),
                _header("Font Size / Zoom"),
                _item("Zoom In", ft.Icons.ADD_ROUNDED, on_term_zoom_in),
                _item("Zoom Out", ft.Icons.REMOVE_ROUNDED, on_term_zoom_out),
                _item(
                    f"Reset Zoom ({int(ts.get('zoom', 11))}px)",
                    ft.Icons.FIT_SCREEN_ROUNDED,
                    on_term_zoom_reset,
                ),
                ft.PopupMenuItem(),
                _header("Toggle Options"),
                _item(
                    "Cursor Blink",
                    ft.Icons.VISIBILITY_ROUNDED,
                    on_term_toggle_blink,
                    ts.get("blink", True),
                ),
                _item(
                    "Search Bar",
                    ft.Icons.SEARCH_ROUNDED,
                    on_term_toggle_search,
                    ts.get("search", False),
                ),
            ]
        )
    else:
        # Import is always available — you can import a notebook into an empty
        # one. Export and Clear All are only meaningful once cells exist.
        menu_items.append(
            _item("Import .ipynb", ft.Icons.UPLOAD_FILE_ROUNDED, on_import_ipynb)
        )
        if has_cells:
            menu_items.extend(
                [
                    _item("Export .ipynb", ft.Icons.DOWNLOAD_ROUNDED, on_export_ipynb),
                    _item(
                        "Clear All Outputs",
                        ft.Icons.DELETE_SWEEP_ROUNDED,
                        on_clear_all,
                    ),
                ]
            )
        menu_items.extend(
            [
                _item("Mount Drive", ft.Icons.ADD_TO_DRIVE_ROUNDED, on_mount_drive),
                _item("Auth GCP", ft.Icons.SECURITY_ROUNDED, on_auth_gcp),
                _item(
                    "Open in Browser", ft.Icons.OPEN_IN_BROWSER_ROUNDED, on_open_browser
                ),
                _item("View Logs", ft.Icons.HISTORY_ROUNDED, on_view_logs),
            ]
        )

    menu_items.append(
        _item("Manage Files", ft.Icons.FOLDER_ROUNDED, on_manage_files)
    )
    menu_items.extend(
        [
            _item("Restart Kernel", ft.Icons.REFRESH_ROUNDED, on_restart),
            _item("Stop Session", ft.Icons.STOP_CIRCLE_ROUNDED, on_stop),
        ]
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
        tooltip="Session actions",
    )

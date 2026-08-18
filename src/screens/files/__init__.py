"""FilesScreen — Modular Colab filesystem explorer, upload/download manager, and directory operations."""

from __future__ import annotations

import posixpath

import flet as ft

from components.file_item import build_file_item
from core import tokens
from core.styles import build_banner_ad
from screens.files.actions import (
    do_delete_async,
    do_new_folder_async,
    handle_download_async,
    handle_upload_async,
)
from screens.files.components import (
    build_breadcrumbs,
    build_empty_dir_view,
)
from state import AppStateCtx, ServiceCtx


@ft.component
def FilesScreen(session_name: str) -> ft.Control:
    """Colab file manager — browse, select, upload, download, delete, and create folders."""
    state = ft.use_context(AppStateCtx)
    services = ft.use_context(ServiceCtx)
    page = ft.context.page

    current_path, set_current_path = ft.use_state("/content")
    listing, set_listing = ft.use_state([])
    selected, set_selected = ft.use_state(set())
    selection_mode, set_selection_mode = ft.use_state(False)
    is_loading, set_is_loading = ft.use_state(False)
    error_msg, set_error_msg = ft.use_state("")

    # ── Fetch directory listing ───────────────────────────────────────────────
    async def _fetch(path: str):
        set_is_loading(True)
        set_error_msg("")
        try:
            files = await services.colab.ls(
                path, session_name=session_name, auth_method=state.auth_method
            )
            set_listing(files or [])
        except Exception as ex:
            set_error_msg(str(ex))
            set_listing([])
        finally:
            set_is_loading(False)

    ft.use_effect(
        lambda: page.run_task(_fetch, current_path), [current_path, session_name]
    )

    def _navigate(path: str):
        set_current_path(path)
        set_selected(set())
        set_selection_mode(False)

    def _clear_selection():
        set_selected(set())
        set_selection_mode(False)

    # ── Item tap / selection handlers ─────────────────────────────────────────
    def _on_file_tap(item: dict):
        if item.get("type") == "directory" or item.get("is_dir", False):
            _navigate(posixpath.normpath(posixpath.join(current_path, item["name"])))
        elif selection_mode:
            _toggle_select(item["name"])
        else:
            set_selection_mode(True)
            set_selected({item["name"]})

    def _toggle_select(name: str):
        new_sel = set(selected)
        if name in new_sel:
            new_sel.discard(name)
        else:
            new_sel.add(name)
        set_selected(new_sel)
        if not new_sel:
            set_selection_mode(False)

    # ── Action dialogs ────────────────────────────────────────────────────────
    def _open_new_folder_dialog():
        tf = ft.TextField(
            label="Folder name",
            autofocus=True,
            border_radius=tokens.RADIUS_MD,
            on_submit=lambda e: (
                page.pop_dialog(),
                page.run_task(
                    do_new_folder_async,
                    page,
                    services.colab,
                    current_path,
                    e.control.value or "",
                    session_name,
                    state.auth_method,
                    set_is_loading,
                    _fetch,
                ),
            ),
        )

        def _confirm_create(e):
            val = tf.value or ""
            page.pop_dialog()
            page.run_task(
                do_new_folder_async,
                page,
                services.colab,
                current_path,
                val,
                session_name,
                state.auth_method,
                set_is_loading,
                _fetch,
            )

        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text(
                    "New Folder", size=tokens.FONT_MD, weight=ft.FontWeight.W_600
                ),
                content=tf,
                actions=[
                    ft.TextButton("Cancel", on_click=lambda e: page.pop_dialog()),
                    ft.FilledButton("Create", on_click=_confirm_create),
                ],
            )
        )

    def _open_delete_dialog():
        names = list(selected)
        if not names:
            return

        def _confirm_delete(e):
            page.pop_dialog()
            page.run_task(
                do_delete_async,
                page,
                services.colab,
                current_path,
                names,
                session_name,
                state.auth_method,
                set_is_loading,
                _clear_selection,
                _fetch,
            )

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(f"Delete {len(names)} item(s)?"),
                content=ft.Text("This cannot be undone.", size=tokens.FONT_SM),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda e: page.pop_dialog()),
                    ft.FilledButton(
                        "Delete",
                        style=ft.ButtonStyle(
                            bgcolor=ft.Colors.ERROR, color=ft.Colors.WHITE
                        ),
                        on_click=_confirm_delete,
                    ),
                ],
            )
        )

    # ── Toolbar ───────────────────────────────────────────────────────────────
    if selection_mode and selected:
        toolbar = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Text(
                        f"{len(selected)} selected",
                        size=tokens.FONT_SM,
                        weight=ft.FontWeight.W_600,
                        color=ft.Colors.PRIMARY,
                        expand=True,
                    ),
                    ft.IconButton(
                        ft.Icons.DOWNLOAD_ROUNDED,
                        tooltip="Download",
                        on_click=lambda e: page.run_task(
                            handle_download_async,
                            page,
                            services.colab,
                            services.ad_service,
                            current_path,
                            selected,
                            listing,
                            session_name,
                            state.auth_method,
                            _clear_selection,
                        ),
                    ),
                    ft.IconButton(
                        ft.Icons.DELETE_OUTLINE_ROUNDED,
                        icon_color=ft.Colors.ERROR,
                        tooltip="Delete",
                        on_click=lambda e: _open_delete_dialog(),
                    ),
                    ft.IconButton(
                        ft.Icons.CLOSE_ROUNDED,
                        tooltip="Cancel selection",
                        on_click=lambda e: _clear_selection(),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(
                tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, tokens.SPACE_SM
            ),
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
        )
    else:
        toolbar = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Container(
                        content=build_breadcrumbs(current_path, _navigate),
                        expand=True,
                    ),
                    ft.Row(
                        controls=[
                            ft.IconButton(
                                ft.Icons.CHECKLIST_ROUNDED,
                                tooltip="Select items",
                                icon_color=ft.Colors.PRIMARY
                                if selection_mode
                                else None,
                                on_click=lambda e: set_selection_mode(
                                    not selection_mode
                                ),
                            ),
                            ft.IconButton(
                                ft.Icons.CREATE_NEW_FOLDER_ROUNDED,
                                tooltip="New folder",
                                on_click=lambda e: _open_new_folder_dialog(),
                            ),
                            ft.IconButton(
                                ft.Icons.UPLOAD_FILE_ROUNDED,
                                tooltip="Upload file",
                                on_click=lambda e: page.run_task(
                                    handle_upload_async,
                                    page,
                                    services.colab,
                                    current_path,
                                    session_name,
                                    state.auth_method,
                                    _fetch,
                                    state,
                                ),
                            ),
                            ft.IconButton(
                                ft.Icons.REFRESH_ROUNDED,
                                tooltip="Refresh",
                                on_click=lambda e: page.run_task(_fetch, current_path),
                            ),
                        ],
                        spacing=0,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(
                tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_MD, tokens.SPACE_XS
            ),
            bgcolor=ft.Colors.SURFACE,
        )

    # ── Body Content ──────────────────────────────────────────────────────────
    if error_msg:
        body: ft.Control = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(
                        ft.Icons.ERROR_OUTLINE_ROUNDED,
                        size=tokens.ICON_XXL,
                        color=ft.Colors.ERROR,
                    ),
                    ft.Text(
                        "Could not load files",
                        size=tokens.FONT_MD,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        weight=ft.FontWeight.W_500,
                    ),
                    ft.Text(
                        error_msg,
                        size=tokens.FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.OutlinedButton(
                        "Retry",
                        icon=ft.Icons.REFRESH_ROUNDED,
                        on_click=lambda e: page.run_task(_fetch, current_path),
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=tokens.SPACE_SM,
            ),
            alignment=ft.Alignment.CENTER,
            padding=tokens.SPACE_XXL,
            expand=True,
        )
    elif not listing and not is_loading:
        body = build_empty_dir_view(
            lambda e: page.run_task(
                handle_upload_async,
                page,
                services.colab,
                current_path,
                session_name,
                state.auth_method,
                _fetch,
                state,
            )
        )
    else:
        list_items = [
            build_file_item(
                item=item,
                is_selected=item["name"] in selected,
                selection_mode=selection_mode,
                on_tap=lambda e, i=item: _on_file_tap(i),
                on_long_press=lambda e, i=item: (
                    set_selection_mode(True),
                    _toggle_select(i["name"]),
                ),
            )
            for item in listing
        ]
        body = ft.ListView(
            controls=list_items,
            expand=True,
            spacing=tokens.SPACE_XXS,
            padding=ft.Padding(
                tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_MD
            ),
        )

    # ── Upload FAB (hidden during multi-selection) ────────────────────────────
    upload_fab = ft.FloatingActionButton(
        content=ft.Row(
            controls=[
                ft.Icon(ft.Icons.UPLOAD_FILE_ROUNDED, size=tokens.ICON_SM),
                ft.Text("Upload", size=tokens.FONT_SM, weight=ft.FontWeight.W_500),
            ],
            spacing=tokens.SPACE_XS,
            alignment=ft.MainAxisAlignment.CENTER,
        ),
        bgcolor=ft.Colors.PRIMARY,
        on_click=lambda e: page.run_task(
            handle_upload_async,
            page,
            services.colab,
            current_path,
            session_name,
            state.auth_method,
            _fetch,
            state,
        ),
        visible=not selection_mode,
    )

    content_col = ft.Column(
        controls=[
            toolbar,
            ft.ProgressBar(
                visible=is_loading,
                height=2,
                color=ft.Colors.PRIMARY,
                bgcolor=ft.Colors.TRANSPARENT,
            ),
            ft.Divider(height=1, thickness=1),
            build_banner_ad(page),
            ft.Container(content=body, expand=True, padding=0),
        ],
        spacing=0,
        expand=True,
    )

    return ft.Stack(
        controls=[
            content_col,
            ft.Container(
                content=upload_fab,
                right=tokens.SPACE_LG,
                bottom=tokens.SPACE_XL,
            ),
        ],
        expand=True,
    )


__all__ = ["FilesScreen"]

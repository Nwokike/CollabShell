"""Manage Files Modal Dialog — standalone Colab file browser dialog with live actions.

Ported from SpanInsight's screens/files/modal.py, adapted to Colab's action
signatures (auth_method, ad_service) and show_notification snackbars.
"""

from __future__ import annotations

import logging
import posixpath

import flet as ft

from components.file_item import build_file_item
from core import tokens
from core.notifications import show_notification
from screens.files.actions import (
    do_delete_async,
    do_new_folder_async,
    handle_download_async,
    handle_upload_async,
)
from screens.files.components import (
    build_breadcrumbs,
    build_empty_dir_view,
    parent_path,
)

logger = logging.getLogger("ManageFilesModal")


def show_manage_files_modal(
    page: ft.Page,
    colab,
    session_name: str,
    auth_method: str = "oauth2",
    ad_service=None,
    state=None,
):
    """Opens a modal dialog for Colab file management."""
    if not page or not colab or not session_name:
        return

    current_path = "/content"
    listing: list[dict] = []
    selected_files: set[str] = set()
    is_loading = False
    selection_mode = False

    breadcrumb_container = ft.Container(expand=True)
    action_row = ft.Row(spacing=tokens.SPACE_XS)
    list_container = ft.Container(
        content=ft.ProgressRing(),
        alignment=ft.Alignment.CENTER,
        expand=True,
    )

    dlg = ft.AlertDialog(
        title=ft.Row(
            controls=[
                ft.Icon(ft.Icons.FOLDER_ROUNDED, color=ft.Colors.PRIMARY),
                ft.Text(
                    "Manage Files",
                    weight=ft.FontWeight.W_600,
                    size=tokens.FONT_LG,
                ),
            ],
            spacing=tokens.SPACE_SM,
        ),
        content=ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                breadcrumb_container,
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=ft.Padding(
                            tokens.SPACE_SM,
                            tokens.SPACE_NONE,
                            tokens.SPACE_SM,
                            tokens.SPACE_NONE,
                        ),
                    ),
                    ft.Divider(height=tokens.DIVIDER_THICKNESS),
                    list_container,
                ],
                spacing=tokens.SPACE_XS,
                expand=True,
            ),
            width=tokens.DIALOG_WIDTH_LG,
            height=tokens.DIALOG_HEIGHT_LG,
        ),
        actions=[
            ft.Row(
                controls=[
                    action_row,
                    ft.Container(expand=True),
                    ft.TextButton(
                        "Close",
                        on_click=lambda _: page.pop_dialog(),
                    ),
                ],
                spacing=tokens.SPACE_SM,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.START,
    )

    def _render():
        nonlocal selection_mode
        # Update breadcrumbs (with go-up affordance)
        up_target = parent_path(current_path)
        breadcrumb_container.content = ft.Row(
            controls=[
                ft.IconButton(
                    ft.Icons.ARROW_UPWARD_ROUNDED,
                    tooltip="Go up",
                    icon_size=tokens.ICON_SM,
                    icon_color=ft.Colors.ON_SURFACE_VARIANT
                    if up_target is None
                    else None,
                    on_click=(
                        None if up_target is None else lambda _: _on_navigate(up_target)
                    ),
                ),
                ft.Container(
                    content=build_breadcrumbs(current_path, on_navigate=_on_navigate),
                    expand=True,
                ),
            ],
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Update action buttons
        n_sel = len(selected_files)
        actions: list[ft.Control] = []

        if selection_mode:
            has_sel = n_sel > 0
            actions.append(
                ft.Container(
                    content=ft.Text(
                        f"{n_sel} sel" if has_sel else "Tap to select",
                        size=tokens.FONT_XS,
                        weight=ft.FontWeight.W_600,
                        color=ft.Colors.PRIMARY
                        if has_sel
                        else ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    padding=ft.Padding(
                        tokens.SPACE_XS,
                        tokens.SPACE_NONE,
                        tokens.SPACE_XS,
                        tokens.SPACE_NONE,
                    ),
                )
            )
            actions.extend(
                [
                    ft.IconButton(
                        ft.Icons.DOWNLOAD_ROUNDED,
                        tooltip="Download",
                        icon_size=tokens.ICON_SM,
                        icon_color=ft.Colors.ON_SURFACE_VARIANT
                        if not has_sel
                        else None,
                        on_click=(
                            None
                            if not has_sel
                            else lambda _: page.run_task(
                                handle_download_async,
                                page,
                                colab,
                                ad_service,
                                current_path,
                                selected_files,
                                listing,
                                session_name,
                                auth_method,
                                _clear_selection,
                            )
                        ),
                    ),
                    ft.IconButton(
                        ft.Icons.DELETE_ROUNDED,
                        tooltip="Delete",
                        icon_size=tokens.ICON_SM,
                        icon_color=ft.Colors.ERROR
                        if has_sel
                        else ft.Colors.ON_SURFACE_VARIANT,
                        on_click=None if not has_sel else lambda _: _handle_delete(),
                    ),
                    ft.IconButton(
                        ft.Icons.CLOSE_ROUNDED,
                        tooltip="Cancel selection",
                        icon_size=tokens.ICON_SM,
                        on_click=lambda _: _clear_selection(),
                    ),
                ]
            )
        else:
            actions.extend(
                [
                    ft.IconButton(
                        ft.Icons.CHECKLIST_ROUNDED,
                        tooltip="Select items",
                        icon_size=tokens.ICON_SM,
                        on_click=lambda _: _enter_selection_mode(),
                    ),
                    ft.IconButton(
                        ft.Icons.UPLOAD_FILE_ROUNDED,
                        tooltip="Upload files",
                        icon_size=tokens.ICON_SM,
                        on_click=lambda _: page.run_task(
                            handle_upload_async,
                            page,
                            colab,
                            current_path,
                            session_name,
                            auth_method,
                            _fetch_listing,
                            state,
                        ),
                    ),
                    ft.IconButton(
                        ft.Icons.CREATE_NEW_FOLDER_ROUNDED,
                        tooltip="New folder",
                        icon_size=tokens.ICON_SM,
                        on_click=lambda _: _handle_new_folder(),
                    ),
                    ft.IconButton(
                        ft.Icons.REFRESH_ROUNDED,
                        tooltip="Refresh",
                        icon_size=tokens.ICON_SM,
                        on_click=lambda _: page.run_task(_fetch_listing, current_path),
                    ),
                ]
            )
        action_row.controls = actions

        # Update file list — spinner whenever the modal is busy, so folder
        # taps, go-up, and refreshes all give feedback instead of freezing on
        # the previous directory's stale listing.
        if is_loading:
            list_container.content = ft.Container(
                content=ft.ProgressRing(),
                alignment=ft.Alignment.CENTER,
                expand=True,
            )
        elif not listing:
            list_container.content = build_empty_dir_view(
                lambda _: page.run_task(
                    handle_upload_async,
                    page,
                    colab,
                    current_path,
                    session_name,
                    auth_method,
                    _fetch_listing,
                    state,
                )
            )
        else:
            list_items = [
                build_file_item(
                    file_info=item,
                    selected=(item["name"] in selected_files),
                    selection_mode=selection_mode,
                    on_click=lambda _, i=item: _on_item_click(i),
                )
                for item in listing
            ]
            list_container.content = ft.ListView(
                controls=list_items,
                expand=True,
                spacing=tokens.SPACE_XXS,
                padding=ft.Padding(
                    tokens.SPACE_SM,
                    tokens.SPACE_NONE,
                    tokens.SPACE_SM,
                    tokens.SPACE_SM,
                ),
            )

        try:
            dlg.update()
        except Exception:
            logger.exception("Suppressed exception")

    async def _fetch_listing(path: str):
        nonlocal is_loading, listing, current_path
        current_path = path
        is_loading = True
        _render()
        try:
            listing = await colab.ls(path, session_name, auth_method)
            selected_files.clear()
        except Exception as e:
            logger.error("ls failed: %s", e)
            show_notification(page, f"Failed: {e}", is_error=True)
        finally:
            is_loading = False
            _render()

    def _set_loading(val: bool):
        nonlocal is_loading
        is_loading = val
        _render()

    def _on_navigate(path: str):
        page.run_task(_fetch_listing, path)

    def _clear_selection():
        nonlocal selection_mode
        selected_files.clear()
        selection_mode = False
        _render()

    def _enter_selection_mode():
        nonlocal selection_mode
        selection_mode = True
        _render()

    def _on_item_click(item: dict):
        nonlocal current_path, selection_mode
        is_dir = item.get("type") == "directory" or item.get("is_dir", False)
        if selection_mode:
            # Folders are selectable too (downloaded as zip).
            name = item["name"]
            if name in selected_files:
                selected_files.remove(name)
                if not selected_files:
                    selection_mode = False
            else:
                selected_files.add(name)
            _render()
        elif is_dir:
            new_path = posixpath.normpath(posixpath.join(current_path, item["name"]))
            page.run_task(_fetch_listing, new_path)
        else:
            selected_files.clear()
            selected_files.add(item["name"])
            selection_mode = True
            _render()

    def _handle_delete():
        if not selected_files:
            return
        names = list(selected_files)
        names_str = "\n".join(f"• {n}" for n in names)

        del_dlg = ft.AlertDialog(
            title=ft.Text(f"Delete {len(names)} item(s)?"),
            content=ft.Text(
                f"This cannot be undone:\n{names_str}",
                size=tokens.FONT_SM,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: page.pop_dialog()),
                ft.FilledButton(
                    "Delete",
                    style=ft.ButtonStyle(bgcolor=ft.Colors.ERROR),
                    on_click=lambda _: (
                        page.pop_dialog(),
                        page.run_task(
                            do_delete_async,
                            page,
                            colab,
                            current_path,
                            names,
                            session_name,
                            auth_method,
                            _set_loading,
                            _clear_selection,
                            _fetch_listing,
                        ),
                    ),
                ),
            ],
        )
        page.show_dialog(del_dlg)

    def _handle_new_folder():
        tf = ft.TextField(label="Folder name", autofocus=True)
        folder_dlg = ft.AlertDialog(
            title=ft.Text("New Folder"),
            content=tf,
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: page.pop_dialog()),
                ft.FilledButton(
                    "Create",
                    on_click=lambda _: (
                        page.pop_dialog(),
                        page.run_task(
                            do_new_folder_async,
                            page,
                            colab,
                            current_path,
                            tf.value or "",
                            session_name,
                            auth_method,
                            _set_loading,
                            _fetch_listing,
                        ),
                    ),
                ),
            ],
        )
        page.show_dialog(folder_dlg)

    page.show_dialog(dlg)
    page.run_task(_fetch_listing, current_path)

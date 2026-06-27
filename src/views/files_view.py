"""Files view — remote file browser with upload, download, delete."""

from __future__ import annotations

import flet as ft
import os

from core import tokens
from core.styles import build_banner_ad
from core.theme import AppColors
from components.file_item import build_file_item


def build_files_view(
    page: ft.Page,
    colab_service,
    state,
    session_name: str,
    on_back=None,
    snack=None,
) -> ft.View:
    """Build the file browser view for a session."""

    current_path = state.current_path or "content"
    files = []
    is_loading = False

    file_picker = ft.FilePicker()
    page.overlay.append(file_picker)

    async def _load_files(path=None):
        nonlocal current_path, files, is_loading
        if path is not None:
            current_path = path
            state.current_path = path
        is_loading = True
        page.update()
        try:
            files = await colab_service.ls(
                path=current_path,
                session_name=session_name,
                auth_method=state.auth_method,
            )
            state.file_listing = files
        except Exception as ex:
            if snack:
                snack(f"Error: {ex}")
            files = []
        is_loading = False
        page.update()

    def _on_file_tap(file_info):
        if file_info.get("type") == "directory":
            new_path = f"{current_path}/{file_info['name']}"
            page.run_task(_load_files, new_path)
        else:
            _show_file_actions(file_info)

    def _show_file_actions(file_info):
        name = file_info.get("name", "")
        remote_path = f"{current_path}/{name}"

        async def _do_download(e):
            page.pop_dialog()
            if snack:
                snack(f"Downloading {name}...")
            try:
                # Save to a temp directory accessible on Android
                local_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                os.makedirs(local_dir, exist_ok=True)
                local_path = os.path.join(local_dir, name)
                await colab_service.download(
                    remote_path,
                    local_path,
                    session_name=session_name,
                    auth_method=state.auth_method,
                )
                if snack:
                    snack(f"✅ Saved to {local_path}")
            except Exception as ex:
                if snack:
                    snack(f"❌ {ex}")

        async def _do_delete(e):
            page.pop_dialog()

            confirm = ft.AlertDialog(
                title=ft.Text(f"Delete {name}?"),
                content=ft.Text("This cannot be undone."),
                actions=[
                    ft.TextButton(
                        content=ft.Text("Cancel"), on_click=lambda e: page.pop_dialog()
                    ),
                    ft.FilledButton(
                        "Delete",
                        on_click=lambda e: page.run_task(_confirm_delete, e),
                    ),
                ],
            )

            async def _confirm_delete(e):
                page.pop_dialog()
                if snack:
                    snack(f"Deleting {name}...")
                try:
                    await colab_service.rm(
                        remote_path,
                        session_name=session_name,
                        auth_method=state.auth_method,
                    )
                    if snack:
                        snack(f"✅ Deleted {name}")
                    await _load_files()
                except Exception as ex:
                    if snack:
                        snack(f"❌ {ex}")

            page.show_dialog(confirm)

        action_sheet = ft.BottomSheet(
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text(name, size=tokens.FONT_LG, weight=ft.FontWeight.W_600),
                        ft.Text(
                            remote_path,
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Divider(),
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.DOWNLOAD_ROUNDED),
                            title=ft.Text("Download"),
                            on_click=lambda e: page.run_task(_do_download, e),
                        ),
                        ft.ListTile(
                            leading=ft.Icon(
                                ft.Icons.DELETE_ROUNDED, color=AppColors.ERROR
                            ),
                            title=ft.Text("Delete", color=AppColors.ERROR),
                            on_click=lambda e: page.run_task(_do_delete, e),
                        ),
                    ],
                    tight=True,
                    spacing=tokens.SPACE_SM,
                ),
                padding=ft.Padding(
                    tokens.SPACE_XL, tokens.SPACE_XL, tokens.SPACE_XL, tokens.SPACE_XXL
                ),
            ),
        )
        page.show_dialog(action_sheet)

    # ── Upload ────────────────────────────────────────────────────────────────
    def _on_upload_picked(e: ft.FilePickerResultEvent):
        if e.files:
            local_path = e.files[0].path
            filename = os.path.basename(local_path)
            remote_path = f"{current_path}/{filename}"
            page.run_task(_do_upload, local_path, remote_path)

    file_picker.on_result = _on_upload_picked

    async def _do_upload(local_path, remote_path):
        state.is_uploading = True
        if snack:
            snack(f"Uploading {os.path.basename(local_path)}...")
        try:
            await colab_service.upload(
                local_path,
                remote_path,
                session_name=session_name,
                auth_method=state.auth_method,
            )
            if snack:
                snack(f"✅ Uploaded to {remote_path}")
            await _load_files()
        except Exception as ex:
            if snack:
                snack(f"❌ {ex}")
        state.is_uploading = False
        page.update()

    # ── Breadcrumb ────────────────────────────────────────────────────────────
    def _build_breadcrumb():
        parts = current_path.split("/")
        controls = []
        for i, part in enumerate(parts):
            path_so_far = "/".join(parts[: i + 1])
            is_last = i == len(parts) - 1
            controls.append(
                ft.TextButton(
                    part,
                    style=ft.ButtonStyle(
                        color=ft.Colors.PRIMARY
                        if not is_last
                        else ft.Colors.ON_SURFACE,
                        padding=ft.Padding(tokens.SPACE_SM, 0, tokens.SPACE_SM, 0),
                    ),
                    on_click=(lambda e, p=path_so_far: page.run_task(_load_files, p))
                    if not is_last
                    else None,
                )
            )
            if not is_last:
                controls.append(
                    ft.Text(
                        "/", size=tokens.FONT_SM, color=ft.Colors.ON_SURFACE_VARIANT
                    )
                )
        return ft.Row(controls=controls, spacing=0, wrap=True)

    def _on_navigate_up(e):
        parts = current_path.split("/")
        if len(parts) > 1:
            parent = "/".join(parts[:-1])
            page.run_task(_load_files, parent)

    # ── Build file list ───────────────────────────────────────────────────────
    def _build_file_list():
        if is_loading:
            return ft.Container(
                content=ft.ProgressRing(width=30, height=30),
                alignment=ft.Alignment.CENTER,
                padding=tokens.SPACE_XXL,
            )

        if not files:
            return ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Icon(
                            ft.Icons.FOLDER_OFF_ROUNDED,
                            size=48,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(
                            "Empty directory",
                            size=tokens.FONT_MD,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=tokens.SPACE_SM,
                ),
                alignment=ft.Alignment.CENTER,
                padding=tokens.SPACE_XXL,
            )

        return ft.Column(
            controls=[
                build_file_item(
                    file_info=f,
                    on_click=lambda e, fi=f: _on_file_tap(fi),
                )
                for f in files
            ],
            spacing=tokens.SPACE_XXS,
        )

    # ── AppBar ────────────────────────────────────────────────────────────────
    app_bar = ft.AppBar(
        leading=ft.IconButton(ft.Icons.ARROW_BACK_ROUNDED, on_click=on_back),
        title=ft.Text("Files", weight=ft.FontWeight.W_600),
        center_title=True,
        actions=[
            ft.IconButton(
                icon=ft.Icons.REFRESH_ROUNDED,
                on_click=lambda e: page.run_task(_load_files),
                tooltip="Refresh",
            ),
        ],
    )

    # ── FAB ───────────────────────────────────────────────────────────────────
    upload_fab = ft.FloatingActionButton(
        "Upload",
        icon=ft.Icons.UPLOAD_FILE_ROUNDED,
        on_click=lambda e: file_picker.pick_files(dialog_title="Select file to upload"),
    )

    # Load files on view creation
    page.run_task(_load_files)

    view_content = ft.Stack(
        controls=[
            ft.Column(
                controls=[
                    app_bar,
                    ft.Column(
                        controls=[
                            # Breadcrumb + Up button
                            ft.Container(
                                content=ft.Row(
                                    controls=[
                                        ft.IconButton(
                                            icon=ft.Icons.ARROW_UPWARD_ROUNDED,
                                            icon_size=tokens.ICON_MD,
                                            on_click=_on_navigate_up,
                                            tooltip="Go up",
                                        ),
                                        ft.Container(
                                            content=_build_breadcrumb(),
                                            expand=True,
                                        ),
                                    ],
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    spacing=tokens.SPACE_XS,
                                ),
                                padding=ft.Padding(
                                    tokens.SPACE_SM, 0, tokens.SPACE_SM, 0
                                ),
                            ),
                            ft.Divider(height=1),
                            # File list
                            ft.Container(
                                content=_build_file_list(),
                                padding=ft.Padding(
                                    tokens.SPACE_SM, 0, tokens.SPACE_SM, 0
                                ),
                                expand=True,
                            ),
                            build_banner_ad(page),
                        ],
                        spacing=0,
                        scroll=ft.ScrollMode.AUTO,
                        expand=True,
                    ),
                ],
                expand=True,
                spacing=0,
            ),
            ft.Container(
                content=upload_fab,
                alignment=ft.Alignment(1, 1),
                padding=ft.Padding(0, 0, tokens.SPACE_LG, tokens.SPACE_LG),
            ),
        ],
        expand=True,
    )

    return ft.View(
        f"/files?session={session_name}",
        [view_content],
        padding=0,
    )

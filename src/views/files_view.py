"""Files view — remote file browser with upload, download, delete."""

from __future__ import annotations

import flet as ft
import os
import posixpath

from core import tokens
from core.styles import build_banner_ad
from components.file_item import build_file_item


def build_files_view(
    page: ft.Page,
    colab_service,
    state,
    session_name: str,
    on_back=None,
    snack=None,
    theme_btn=None,
) -> ft.View:
    """Build the file browser view for a session."""

    current_path = state.current_path or "/content"
    files = []
    is_loading = False
    selected_files = set()

    file_picker = getattr(page, "file_picker", None)

    file_list_container = ft.Container(
        padding=ft.Padding(tokens.SPACE_SM, 0, tokens.SPACE_SM, 0),
        expand=True,
    )
    breadcrumb_container = ft.Container(
        expand=True,
    )
    action_bar_container = ft.Container()

    upload_fab = ft.FloatingActionButton(
        "Upload",
        icon=ft.Icons.UPLOAD_FILE_ROUNDED,
        on_click=lambda e: page.run_task(_on_upload_click, e),
    )

    async def _load_files(path=None):
        nonlocal current_path, files, is_loading
        if path is not None:
            current_path = path
            state.current_path = path
        is_loading = True

        selected_files.clear()
        action_bar_container.content = _build_action_bar()
        upload_fab.visible = True
        try:
            action_bar_container.update()
            upload_fab.update()
        except Exception:
            pass

        file_list_container.content = _build_file_list()
        try:
            file_list_container.update()
        except Exception:
            pass

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

        file_list_container.content = _build_file_list()
        breadcrumb_container.content = _build_breadcrumb()
        try:
            file_list_container.update()
            breadcrumb_container.update()
        except Exception:
            pass

    def _on_file_tap(file_info):
        name = file_info.get("name")
        if name in selected_files:
            selected_files.remove(name)
        else:
            selected_files.add(name)

        file_list_container.content = _build_file_list()
        action_bar_container.content = _build_action_bar()
        upload_fab.visible = len(selected_files) == 0
        try:
            file_list_container.update()
            action_bar_container.update()
            upload_fab.update()
        except Exception:
            pass

    async def _do_download_selected(e=None):
        selected_items = [f for f in files if f["name"] in selected_files]
        if not selected_items:
            return

        for item in selected_items:
            name = item["name"]
            is_dir = item.get("type") == "directory"
            remote_path = posixpath.normpath(posixpath.join(current_path, name))

            size_bytes = item.get("size")
            size_str = ""
            if size_bytes is not None:
                if size_bytes < 1024:
                    size_str = f" ({size_bytes} B)"
                elif size_bytes < 1024 * 1024:
                    size_str = f" ({size_bytes / 1024:.1f} KB)"
                else:
                    size_str = f" ({size_bytes / (1024 * 1024):.1f} MB)"
            elif is_dir:
                size_str = " (folder)"

            default_name = f"{name}.zip" if is_dir else name

            local_path = await page.file_picker.save_file(
                dialog_title=f"Save {default_name}",
                file_name=default_name,
            )
            if not local_path:
                continue

            prog_bar = ft.ProgressBar(
                color=ft.Colors.PRIMARY,
                bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY),
            )

            status_text = ft.Text(
                f"Downloading...{size_str}",
                size=tokens.FONT_XS,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )

            download_dialog = ft.AlertDialog(
                title=ft.Text(
                    f"Downloading {default_name}",
                    size=tokens.FONT_SM,
                    font_family="Outfit",
                ),
                content=ft.Column(
                    [
                        prog_bar,
                        status_text,
                    ],
                    spacing=tokens.SPACE_SM,
                    tight=True,
                ),
            )
            page.show_dialog(download_dialog)

            def _on_status(msg: str):
                status_text.value = msg
                try:
                    status_text.update()
                except Exception:
                    pass

            try:
                if is_dir:
                    await colab_service.download_folder(
                        remote_dir_path=remote_path,
                        local_zip_path=local_path,
                        session_name=session_name,
                        auth_method=state.auth_method,
                        on_status=_on_status,
                    )
                else:
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
            finally:
                download_dialog.open = False
                try:
                    page.update()
                except Exception:
                    pass

        # Clear selection after download
        selected_files.clear()
        file_list_container.content = _build_file_list()
        action_bar_container.content = _build_action_bar()
        upload_fab.visible = True
        try:
            file_list_container.update()
            action_bar_container.update()
            upload_fab.update()
        except Exception:
            pass

    async def _do_delete_selected(e=None):
        selected_items = [f for f in files if f["name"] in selected_files]
        if not selected_items:
            return

        names = [f["name"] for f in selected_items]
        names_str = ", ".join(names)

        def _close_confirm(e=None):
            confirm.open = False
            page.update()

        confirm = ft.AlertDialog(
            title=ft.Text(f"Delete {len(names)} item(s)?"),
            content=ft.Text(
                f"Are you sure you want to delete:\n{names_str}\n\nThis cannot be undone."
            ),
            actions=[
                ft.TextButton(content=ft.Text("Cancel"), on_click=_close_confirm),
                ft.FilledButton(
                    "Delete",
                    on_click=lambda e: page.run_task(_confirm_delete, names),
                ),
            ],
        )

        async def _confirm_delete(names_to_delete):
            _close_confirm()
            for name in names_to_delete:
                remote_path = posixpath.normpath(posixpath.join(current_path, name))
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
                except Exception as ex:
                    if snack:
                        snack(f"❌ {ex}")

            selected_files.clear()
            upload_fab.visible = True
            try:
                upload_fab.update()
            except Exception:
                pass
            await _load_files(current_path)

        page.show_dialog(confirm)

    def _build_action_bar():
        if not selected_files:
            return ft.Container()

        selected_items = [f for f in files if f["name"] in selected_files]
        num_selected = len(selected_files)

        can_open = num_selected == 1 and selected_items[0].get("type") == "directory"
        can_download = True

        actions = []
        if can_open:
            item = selected_items[0]
            raw_path = posixpath.join(current_path, item["name"])
            new_path = posixpath.normpath(raw_path)
            actions.append(
                ft.FilledButton(
                    "Open",
                    icon=ft.Icons.FOLDER_OPEN_ROUNDED,
                    on_click=lambda e: page.run_task(_load_files, new_path),
                )
            )

        if can_download:
            actions.append(
                ft.FilledTonalButton(
                    "Download",
                    icon=ft.Icons.DOWNLOAD_ROUNDED,
                    on_click=lambda e: page.run_task(_do_download_selected),
                )
            )

        actions.append(
            ft.TextButton(
                "Delete",
                icon=ft.Icons.DELETE_ROUNDED,
                style=ft.ButtonStyle(color=ft.Colors.ERROR),
                on_click=lambda e: page.run_task(_do_delete_selected),
            )
        )

        return ft.Container(
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
            padding=ft.Padding(
                tokens.SPACE_MD, tokens.SPACE_MD, tokens.SPACE_MD, tokens.SPACE_MD
            ),
            border_radius=ft.BorderRadius(
                top_left=tokens.RADIUS_LG,
                top_right=tokens.RADIUS_LG,
                bottom_left=0,
                bottom_right=0,
            ),
            shadow=ft.BoxShadow(
                spread_radius=1, blur_radius=10, color=ft.Colors.BLACK_12
            ),
            content=ft.Row(
                controls=[
                    ft.Text(
                        f"{num_selected} selected",
                        weight=ft.FontWeight.BOLD,
                        expand=True,
                    ),
                    *actions,
                ],
                alignment=ft.MainAxisAlignment.END,
            ),
        )

    # ── Upload ────────────────────────────────────────────────────────────────
    async def _on_upload_click(e=None):
        if not file_picker:
            return
        picked_files = await file_picker.pick_files(
            dialog_title="Select file to upload",
            with_data=True,
        )
        if not picked_files:
            return
        picked = picked_files[0]
        remote_path = posixpath.normpath(posixpath.join(current_path, picked.name))

        if picked.bytes is not None:
            # Android: content URI — write bytes to a temp file for the SDK
            tmp_dir = os.path.join(os.path.expanduser("~"), ".colab_uploads")
            os.makedirs(tmp_dir, exist_ok=True)
            tmp_path = os.path.join(tmp_dir, picked.name)
            with open(tmp_path, "wb") as f:
                f.write(picked.bytes)
            try:
                await _do_upload(tmp_path, remote_path, len(picked.bytes))
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
        elif picked.path is not None:
            # Desktop/Linux Native Path
            file_size = os.path.getsize(picked.path)
            await _do_upload(picked.path, remote_path, file_size)
        else:
            if snack:
                snack("Could not read file — picker did not return content.")
            return

    async def _do_upload(local_path: str, remote_path: str, file_size: int = None):
        state.is_uploading = True

        size_str = ""
        if file_size is not None:
            if file_size < 1024:
                size_str = f" ({file_size} B)"
            elif file_size < 1024 * 1024:
                size_str = f" ({file_size / 1024:.1f} KB)"
            else:
                size_str = f" ({file_size / (1024 * 1024):.1f} MB)"

        prog_bar = ft.ProgressBar(
            color=ft.Colors.PRIMARY,
            bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY),
        )

        upload_dialog = ft.AlertDialog(
            title=ft.Text(
                f"Uploading {os.path.basename(local_path)}",
                size=tokens.FONT_SM,
                font_family="Outfit",
            ),
            content=ft.Column(
                [
                    prog_bar,
                    ft.Text(
                        f"Uploading...{size_str}",
                        size=tokens.FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                spacing=tokens.SPACE_SM,
                tight=True,
            ),
        )
        page.show_dialog(upload_dialog)

        try:
            await colab_service.upload(
                local_path,
                remote_path,
                session_name=session_name,
                auth_method=state.auth_method,
            )
            if snack:
                snack(f"✅ Uploaded to {remote_path}")
            await _load_files(current_path)
        except Exception as ex:
            if snack:
                snack(f"❌ {ex}")
        finally:
            upload_dialog.open = False
            page.update()
            state.is_uploading = False

    # ── Breadcrumb ────────────────────────────────────────────────────────────
    def _build_breadcrumb():
        clean_path = posixpath.normpath(current_path)
        if clean_path == "." or not clean_path:
            clean_path = "/"
        parts = [p for p in clean_path.split("/") if p]
        controls = []
        controls.append(
            ft.TextButton(
                "/",
                style=ft.ButtonStyle(
                    color=ft.Colors.PRIMARY if parts else ft.Colors.ON_SURFACE,
                    padding=ft.Padding(tokens.SPACE_SM, 0, tokens.SPACE_SM, 0),
                ),
                on_click=(lambda e: page.run_task(_load_files, "/")) if parts else None,
            )
        )
        for i, part in enumerate(parts):
            path_so_far = "/" + "/".join(parts[: i + 1])
            is_last = i == len(parts) - 1
            controls.append(
                ft.Text("/", size=tokens.FONT_SM, color=ft.Colors.ON_SURFACE_VARIANT)
            )
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
        return ft.Row(controls=controls, spacing=0, wrap=True)

    def _on_navigate_up(e):
        if current_path and current_path != "/":
            parent = posixpath.dirname(posixpath.normpath(current_path))
            if not parent or parent == ".":
                parent = "/"
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
                            size=tokens.ICON_XXL,
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
                    selected=f.get("name") in selected_files,
                    on_click=lambda e, fi=f: _on_file_tap(fi),
                )
                for f in files
            ],
            spacing=tokens.SPACE_XXS,
        )

    # ── AppBar Actions ────────────────────────────────────────────────────────
    appbar_actions = [
        ft.IconButton(
            icon=ft.Icons.REFRESH_ROUNDED,
            on_click=lambda e: page.run_task(_load_files),
            tooltip="Refresh",
            icon_size=tokens.ICON_MD,
        ),
    ]
    if theme_btn:
        appbar_actions.append(theme_btn)

    # Load files on view creation
    page.run_task(_load_files)

    from components.brand_header import build_brand_header

    view_content = ft.Column(
        controls=[
            build_brand_header(),
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
                                breadcrumb_container,
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=tokens.SPACE_XS,
                        ),
                        padding=ft.Padding(tokens.SPACE_SM, 0, tokens.SPACE_SM, 0),
                    ),
                    ft.Divider(height=1),
                    # File list
                    file_list_container,
                    build_banner_ad(page),
                ],
                spacing=0,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
        ],
        expand=True,
        spacing=0,
    )

    return ft.View(
        route=f"/files?session={session_name}",
        controls=[view_content, action_bar_container],
        floating_action_button=upload_fab,
        padding=0,
        appbar=ft.AppBar(
            leading=ft.Container(
                content=ft.IconButton(
                    icon=ft.Icons.ARROW_BACK_ROUNDED,
                    on_click=on_back,
                    icon_size=tokens.ICON_MD,
                    tooltip="Back",
                ),
                padding=ft.Padding(tokens.SPACE_XS, 0, 0, 0),
            ),
            leading_width=48,
            title=ft.Text(
                "Files",
                size=tokens.FONT_LG,
                weight=ft.FontWeight.W_700,
                color=ft.Colors.ON_SURFACE,
            ),
            center_title=True,
            bgcolor=ft.Colors.TRANSPARENT,
            actions=appbar_actions,
        ),
    )

import os
import posixpath

import flet as ft

from core import tokens


async def on_upload_click_impl(ctrl, e=None):
    file_picker = getattr(ctrl.page, "file_picker", None)
    if not file_picker:
        return
    picked_files = await file_picker.pick_files(
        dialog_title="Select file to upload",
        with_data=bool(getattr(ctrl.page, "web", False)),
    )
    if not picked_files:
        return
    picked = picked_files[0]
    remote_path = posixpath.normpath(posixpath.join(ctrl.current_path, picked.name))

    if picked.bytes is not None:
        tmp_dir = os.path.join(os.path.expanduser("~"), ".colab_uploads")
        os.makedirs(tmp_dir, exist_ok=True)
        tmp_path = os.path.join(tmp_dir, picked.name)
        import asyncio

        def _write():
            with open(tmp_path, "wb") as f:
                f.write(picked.bytes)

        await asyncio.to_thread(_write)
        try:
            await do_upload_impl(ctrl, tmp_path, remote_path, len(picked.bytes))
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    elif picked.path is not None:
        file_size = os.path.getsize(picked.path)
        await do_upload_impl(ctrl, picked.path, remote_path, file_size)
    else:
        if ctrl.snack:
            ctrl.snack("Could not read file — picker did not return content.")


async def do_upload_impl(
    ctrl, local_path: str, remote_path: str, file_size: int | None = None
):
    ctrl.state.is_uploading = True
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
    ctrl.page.show_dialog(upload_dialog)

    try:
        await ctrl.colab_service.upload(
            local_path,
            remote_path,
            session_name=ctrl.session_name,
            auth_method=ctrl.state.auth_method,
        )
        if ctrl.snack:
            ctrl.snack(f"✅ Uploaded to {remote_path}")
        await ctrl.load_files(ctrl.current_path)
    except Exception as ex:
        if ctrl.snack:
            ctrl.snack(f"❌ {ex}")
    finally:
        upload_dialog.open = False
        ctrl.page.update()
        ctrl.state.is_uploading = False


async def do_download_selected_impl(ctrl, e=None):
    selected_items = [f for f in ctrl.files if f["name"] in ctrl.selected_files]
    if not selected_items:
        return

    if ctrl.state and getattr(ctrl.state, "ad_service", None):
        await ctrl.state.ad_service.show_interstitial()

    for item in selected_items:
        name = item["name"]
        is_dir = item.get("type") == "directory"
        remote_path = posixpath.normpath(posixpath.join(ctrl.current_path, name))

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

        if ctrl.page.platform in [
            ft.PagePlatform.ANDROID,
            ft.PagePlatform.ANDROID_TV,
            ft.PagePlatform.IOS,
        ]:
            dl_dir = "/storage/emulated/0/Download"
            if not os.path.exists(dl_dir):
                dl_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            os.makedirs(dl_dir, exist_ok=True)

            name_part, ext_part = os.path.splitext(default_name)
            counter = 1
            unique_name = default_name
            while os.path.exists(os.path.join(dl_dir, unique_name)):
                unique_name = f"{name_part} ({counter}){ext_part}"
                counter += 1
            local_path = os.path.join(dl_dir, unique_name)
        else:
            try:
                local_path = await ctrl.page.file_picker.save_file(
                    dialog_title=f"Save {default_name}",
                    file_name=default_name,
                )
            except ValueError:
                dl_dir = "/storage/emulated/0/Download"
                if not os.path.exists(dl_dir):
                    dl_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                os.makedirs(dl_dir, exist_ok=True)

                name_part, ext_part = os.path.splitext(default_name)
                counter = 1
                unique_name = default_name
                while os.path.exists(os.path.join(dl_dir, unique_name)):
                    unique_name = f"{name_part} ({counter}){ext_part}"
                    counter += 1
                local_path = os.path.join(dl_dir, unique_name)

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
        ctrl.page.show_dialog(download_dialog)

        def _on_status(msg: str, status_text=status_text):
            status_text.value = msg
            try:
                status_text.update()
            except Exception:
                pass

        try:
            if is_dir:
                await ctrl.colab_service.download_folder(
                    remote_dir_path=remote_path,
                    local_zip_path=local_path,
                    session_name=ctrl.session_name,
                    auth_method=ctrl.state.auth_method,
                    on_status=_on_status,
                )
            else:
                await ctrl.colab_service.download(
                    remote_path,
                    local_path,
                    session_name=ctrl.session_name,
                    auth_method=ctrl.state.auth_method,
                )
            if ctrl.snack:
                ctrl.snack(f"✅ Saved to {local_path}")
        except Exception as ex:
            if ctrl.snack:
                ctrl.snack(f"❌ {ex}")
        finally:
            download_dialog.open = False
            try:
                ctrl.page.update()
            except Exception:
                pass

    ctrl.selected_files.clear()
    ctrl.file_list_container.content = ctrl.build_file_list()
    ctrl.action_bar_container.content = ctrl.build_action_bar()
    ctrl.upload_fab.visible = True
    try:
        ctrl.file_list_container.update()
        ctrl.action_bar_container.update()
        ctrl.upload_fab.update()
    except Exception:
        pass


async def do_delete_selected_impl(ctrl, e=None):
    selected_items = [f for f in ctrl.files if f["name"] in ctrl.selected_files]
    if not selected_items:
        return

    names = [f["name"] for f in selected_items]
    names_str = ", ".join(names)

    def _close_confirm(e=None):
        confirm.open = False
        ctrl.page.update()

    confirm = ft.AlertDialog(
        title=ft.Text(f"Delete {len(names)} item(s)?"),
        content=ft.Text(
            f"Are you sure you want to delete:\n{names_str}\n\nThis cannot be undone."
        ),
        actions=[
            ft.TextButton(content=ft.Text("Cancel"), on_click=_close_confirm),
            ft.FilledButton(
                "Delete",
                on_click=lambda e: ctrl.page.run_task(_confirm_delete, names),
            ),
        ],
    )

    async def _confirm_delete(names_to_delete):
        _close_confirm()
        for name in names_to_delete:
            remote_path = posixpath.normpath(posixpath.join(ctrl.current_path, name))
            if ctrl.snack:
                ctrl.snack(f"Deleting {name}...")
            try:
                await ctrl.colab_service.rm(
                    remote_path,
                    session_name=ctrl.session_name,
                    auth_method=ctrl.state.auth_method,
                )
                if ctrl.snack:
                    ctrl.snack(f"✅ Deleted {name}")
            except Exception as ex:
                if ctrl.snack:
                    ctrl.snack(f"❌ {ex}")

        ctrl.selected_files.clear()
        ctrl.upload_fab.visible = True
        try:
            ctrl.upload_fab.update()
        except Exception:
            pass
        await ctrl.load_files(ctrl.current_path)

    ctrl.page.show_dialog(confirm)

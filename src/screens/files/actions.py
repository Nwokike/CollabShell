"""File transfer and manipulation actions: upload, download, delete, new folder."""

from __future__ import annotations

import asyncio
import logging
import os
import posixpath

import flet as ft

from core import tokens
from core.notifications import show_notification
from screens.files.components import fmt_size

logger = logging.getLogger("ColabFilesActions")


def _snack(page: ft.Page, message: str, is_error: bool = False):
    show_notification(page, message, is_error=is_error)


async def handle_upload_async(
    page: ft.Page,
    colab_service,
    current_path: str,
    session_name: str,
    auth_method: str,
    fetch_listing_fn,
    state=None,
):
    """FilePicker dialog to upload local files to the Colab filesystem."""
    picked_files = await page.file_picker.pick_files(
        dialog_title="Select file to upload",
        allow_multiple=True,
        with_data=bool(getattr(page, "web", False)),
    )
    if not picked_files:
        return

    for picked in picked_files:
        remote_path = posixpath.normpath(posixpath.join(current_path, picked.name))

        if picked.bytes is not None:
            # Android / Web: no direct local path — write bytes to temporary cache file
            tmp_dir = os.path.join(os.path.expanduser("~"), ".colab_uploads")
            os.makedirs(tmp_dir, exist_ok=True)
            tmp_path = os.path.join(tmp_dir, picked.name)

            def _write_bytes(_p=tmp_path, _b=picked.bytes):
                with open(_p, "wb") as _f:
                    _f.write(_b)

            await asyncio.to_thread(_write_bytes)
            local_path = tmp_path
            cleanup = True
            file_size = len(picked.bytes)
        elif picked.path is not None:
            local_path = picked.path
            cleanup = False
            file_size = os.path.getsize(picked.path)
        else:
            _snack(
                page,
                "Could not read file — picker did not return content.",
                is_error=True,
            )
            continue

        size_str = fmt_size(file_size)
        prog_bar = ft.ProgressBar(
            color=ft.Colors.PRIMARY,
            bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY),
        )
        upload_dialog = ft.AlertDialog(
            title=ft.Row(
                controls=[
                    ft.Icon(
                        ft.Icons.UPLOAD_FILE_ROUNDED,
                        color=ft.Colors.PRIMARY,
                        size=tokens.ICON_MD,
                    ),
                    ft.Text(
                        "Uploading file",
                        size=tokens.FONT_MD,
                        weight=ft.FontWeight.W_600,
                    ),
                ],
                spacing=tokens.SPACE_SM,
            ),
            content=ft.Column(
                [
                    ft.Text(
                        picked.name,
                        size=tokens.FONT_SM,
                        weight=ft.FontWeight.W_500,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    prog_bar,
                    ft.Text(
                        f"Uploading to {current_path} · {size_str}",
                        size=tokens.FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                spacing=tokens.SPACE_SM,
                tight=True,
            ),
        )
        if state:
            state.is_uploading = True
        page.show_dialog(upload_dialog)

        try:
            await colab_service.upload(
                local_path,
                remote_path,
                session_name=session_name,
                auth_method=auth_method,
            )
            _snack(page, f"✅ Uploaded to {remote_path}")
        except Exception as ex:
            logger.error("Upload failed: %s", ex)
            _snack(page, f"❌ {ex}", is_error=True)
        finally:
            upload_dialog.open = False
            try:
                page.update()
            except Exception:
                logger.exception("Suppressed exception")
            if state:
                state.is_uploading = False
            if cleanup:
                try:
                    os.unlink(local_path)
                except Exception:
                    logger.exception("Suppressed exception")
    await fetch_listing_fn(current_path)


async def handle_download_async(
    page: ft.Page,
    colab_service,
    ad_service,
    current_path: str,
    selected_files: set[str],
    listing: list[dict],
    session_name: str,
    auth_method: str,
    clear_selection_fn,
):
    """Download selected files/directories locally with Ad gating and mobile fallback."""
    selected_items = [f for f in listing if f["name"] in selected_files]
    if not selected_items:
        return

    async def _do_downloads():
        for item in selected_items:
            name = item["name"]
            is_dir = item.get("type") == "directory" or item.get("is_dir", False)
            remote_path = posixpath.normpath(posixpath.join(current_path, name))

            size_str = fmt_size(item.get("size")) if not is_dir else "folder"
            default_name = f"{name}.zip" if is_dir else name

            if page.platform.is_mobile():
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
                    local_path = await page.file_picker.save_file(
                        dialog_title=f"Save {default_name}",
                        file_name=default_name,
                    )
                except ValueError, Exception:
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
                f"Downloading... ({size_str})",
                size=tokens.FONT_XS,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
            dl_dialog = ft.AlertDialog(
                title=ft.Text(f"Downloading {default_name}", size=tokens.FONT_SM),
                content=ft.Column(
                    [prog_bar, status_text],
                    spacing=tokens.SPACE_SM,
                    tight=True,
                ),
            )
            page.show_dialog(dl_dialog)

            def _on_status(msg: str, _st=status_text):
                _st.value = msg
                try:
                    _st.update()
                except Exception:
                    logger.exception("Suppressed exception")

            try:
                if is_dir:
                    await colab_service.download_folder(
                        remote_dir_path=remote_path,
                        local_zip_path=local_path,
                        session_name=session_name,
                        auth_method=auth_method,
                        on_status=_on_status,
                    )
                else:
                    await colab_service.download(
                        remote_path,
                        local_path,
                        session_name=session_name,
                        auth_method=auth_method,
                    )
                _snack(page, f"✅ Saved to {local_path}")
            except Exception as ex:
                logger.error("Download failed: %s", ex)
                _snack(page, f"❌ {ex}", is_error=True)
            finally:
                dl_dialog.open = False
                try:
                    page.update()
                except Exception:
                    logger.exception("Suppressed exception")
        clear_selection_fn()

    if ad_service:
        await ad_service.show_rewarded_interstitial(on_close=_do_downloads)
    else:
        await _do_downloads()


async def do_delete_async(
    page: ft.Page,
    colab_service,
    current_path: str,
    names: list[str],
    session_name: str,
    auth_method: str,
    set_is_loading_fn,
    clear_selection_fn,
    fetch_listing_fn,
):
    """Batch deletes remote files/folders from the VM."""
    set_is_loading_fn(True)
    failed = []
    for name in names:
        remote = posixpath.normpath(posixpath.join(current_path, name))
        try:
            await colab_service.rm(
                remote, session_name=session_name, auth_method=auth_method
            )
        except Exception as ex:
            failed.append(f"{name}: {ex}")

    if failed:
        _snack(
            page,
            f"❌ Some deletes failed:\n{chr(10).join(failed)}",
            is_error=True,
        )
    else:
        _snack(page, f"✅ Deleted {len(names)} item(s)")

    clear_selection_fn()
    await fetch_listing_fn(current_path)


async def do_new_folder_async(
    page: ft.Page,
    colab_service,
    current_path: str,
    name: str,
    session_name: str,
    auth_method: str,
    set_is_loading_fn,
    fetch_listing_fn,
):
    """Creates a new directory on the remote Colab VM."""
    folder_name = name.strip()
    if not folder_name:
        return
    set_is_loading_fn(True)
    try:
        folder_path = posixpath.normpath(posixpath.join(current_path, folder_name))
        await colab_service.exec_code(
            f"import os; os.makedirs('{folder_path}', exist_ok=True)",
            session_name=session_name,
            auth_method=auth_method,
        )
        _snack(page, f"✅ Created folder: {folder_name}")
    except Exception as ex:
        logger.error("Create folder failed: %s", ex)
        _snack(page, f"❌ {ex}", is_error=True)
    finally:
        await fetch_listing_fn(current_path)

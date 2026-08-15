"""FilesScreen — remote file browser with download/upload/delete and selection mode."""

from __future__ import annotations

import flet as ft

from components.file_item import build_file_item
from core import tokens
from core.styles import build_banner_ad
from core.theme import AppColors
from state import AppStateCtx, ServiceCtx


def _breadcrumbs(path: str, on_navigate) -> ft.Control:
    parts = [p for p in path.split("/") if p]
    crumbs = [
        ft.TextButton(
            "/",
            on_click=lambda e: on_navigate("/content"),
            style=ft.ButtonStyle(padding=ft.Padding(0, 0, 0, 0)),
        )
    ]
    built = ""
    for i, part in enumerate(parts):
        built += f"/{part}"
        captured = built
        is_last = i == len(parts) - 1
        crumbs.append(
            ft.Text("›", size=tokens.FONT_SM, color=ft.Colors.ON_SURFACE_VARIANT)
        )
        if is_last:
            crumbs.append(
                ft.Text(part, size=tokens.FONT_SM, weight=ft.FontWeight.W_600)
            )
        else:
            crumbs.append(
                ft.TextButton(
                    part,
                    on_click=lambda e, p=captured: on_navigate(p),
                    style=ft.ButtonStyle(padding=ft.Padding(0, 0, 0, 0)),
                )
            )
    return ft.Row(controls=crumbs, spacing=2, scroll=ft.ScrollMode.AUTO)


@ft.component
def FilesScreen(session_name: str) -> ft.Control:
    state = ft.use_context(AppStateCtx)
    services = ft.use_context(ServiceCtx)
    page = ft.context.page

    current_path, set_path = ft.use_state("/content")
    listing, set_listing = ft.use_state([])
    selected, set_selected = ft.use_state(set())
    selection_mode, set_mode = ft.use_state(False)
    is_loading, set_loading = ft.use_state(False)
    error_msg, set_error = ft.use_state("")

    async def _fetch(path: str):
        set_loading(True)
        set_error("")
        try:
            files = await services.colab.list_files(
                session_name, path=path, auth_method=state.auth_method
            )
            set_listing(files or [])
        except Exception as ex:
            set_error(str(ex))
            set_listing([])
        finally:
            set_loading(False)

    ft.use_effect(
        lambda: page.run_task(_fetch, current_path), [current_path, session_name]
    )

    def _navigate(path: str):
        set_path(path)
        set_selected(set())
        set_mode(False)

    def _on_file_tap(item: dict):
        if item.get("is_dir"):
            _navigate(f"{current_path.rstrip('/')}/{item['name']}")
        else:
            if selection_mode:
                _toggle_select(item["name"])

    def _toggle_select(name: str):
        new_sel = set(selected)
        if name in new_sel:
            new_sel.discard(name)
        else:
            new_sel.add(name)
        set_selected(new_sel)
        if not new_sel:
            set_mode(False)

    def _on_long_press(item: dict):
        set_mode(True)
        _toggle_select(item["name"])

    # ── Download ──────────────────────────────────────────────────────────────
    async def _download_selected(e=None):
        names = list(selected)
        if not names:
            return
        page.snack_bar = ft.SnackBar(ft.Text(f"⬇ Downloading {len(names)} file(s)..."))
        page.snack_bar.open = True
        page.update()
        for name in names:
            remote = f"{current_path.rstrip('/')}/{name}"
            try:
                import os

                dl_dir = "/storage/emulated/0/Download"
                if not os.path.exists(dl_dir):
                    dl_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                os.makedirs(dl_dir, exist_ok=True)
                await services.colab.download_file(
                    session_name,
                    remote_path=remote,
                    local_dir=dl_dir,
                    auth_method=state.auth_method,
                )
            except Exception as ex:
                page.snack_bar = ft.SnackBar(
                    ft.Text(f"❌ {name}: {ex}"), bgcolor=ft.Colors.ERROR
                )
                page.snack_bar.open = True
                page.update()
        page.snack_bar = ft.SnackBar(
            ft.Text("✅ Download complete"), bgcolor=AppColors.SUCCESS
        )
        page.snack_bar.open = True
        page.update()
        set_selected(set())
        set_mode(False)

    # ── Delete ────────────────────────────────────────────────────────────────
    async def _delete_selected(e=None):
        names = list(selected)
        if not names:
            return

        async def _do_delete():
            for name in names:
                remote = f"{current_path.rstrip('/')}/{name}"
                try:
                    await services.colab.delete_file(
                        session_name, path=remote, auth_method=state.auth_method
                    )
                except Exception as ex:
                    page.snack_bar = ft.SnackBar(
                        ft.Text(f"❌ {name}: {ex}"), bgcolor=ft.Colors.ERROR
                    )
                    page.snack_bar.open = True
                    page.update()
            set_selected(set())
            set_mode(False)
            await _fetch(current_path)

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(f"Delete {len(names)} item(s)?"),
                content=ft.Text("This cannot be undone."),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda e: page.pop_dialog()),
                    ft.FilledButton(
                        "Delete",
                        style=ft.ButtonStyle(
                            bgcolor=ft.Colors.ERROR, color=ft.Colors.WHITE
                        ),
                        on_click=lambda e: (
                            page.pop_dialog(),
                            page.run_task(_do_delete),
                        ),
                    ),
                ],
            )
        )

    # ── Upload ────────────────────────────────────────────────────────────────
    async def _upload(e=None):
        files = await page.file_picker.pick_files(allow_multiple=True)
        if not files:
            return
        state.is_uploading = True
        for f in files:
            try:
                await services.colab.upload_file(
                    session_name,
                    local_path=f.path,
                    remote_dir=current_path,
                    auth_method=state.auth_method,
                )
            except Exception as ex:
                page.snack_bar = ft.SnackBar(
                    ft.Text(f"❌ {f.name}: {ex}"), bgcolor=ft.Colors.ERROR
                )
                page.snack_bar.open = True
                page.update()
        state.is_uploading = False
        await _fetch(current_path)

    # ── Build body ────────────────────────────────────────────────────────────
    if is_loading:
        body: ft.Control = ft.Container(
            content=ft.ProgressRing(width=tokens.SPINNER_LG, height=tokens.SPINNER_LG),
            alignment=ft.Alignment.CENTER,
            padding=tokens.SPACE_XXL,
        )
    elif error_msg:
        body = ft.Container(
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
                    ),
                    ft.Text(
                        error_msg,
                        size=tokens.FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
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
        )
    elif not listing:
        body = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(
                        ft.Icons.FOLDER_OPEN_ROUNDED,
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
    else:
        body = ft.Column(
            controls=[
                build_file_item(
                    item=item,
                    is_selected=item["name"] in selected,
                    selection_mode=selection_mode,
                    on_tap=lambda e, item=item: _on_file_tap(item),
                    on_long_press=lambda e, item=item: _on_long_press(item),
                )
                for item in listing
            ],
            spacing=0,
        )

    # ── Toolbar ───────────────────────────────────────────────────────────────
    if selection_mode and selected:
        toolbar = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Text(
                        f"{len(selected)} selected",
                        size=tokens.FONT_SM,
                        weight=ft.FontWeight.W_500,
                        expand=True,
                    ),
                    ft.IconButton(
                        ft.Icons.DOWNLOAD_ROUNDED,
                        tooltip="Download",
                        on_click=lambda e: page.run_task(_download_selected, e),
                    ),
                    ft.IconButton(
                        ft.Icons.DELETE_OUTLINE_ROUNDED,
                        icon_color=ft.Colors.ERROR,
                        tooltip="Delete",
                        on_click=lambda e: page.run_task(_delete_selected, e),
                    ),
                    ft.IconButton(
                        ft.Icons.CLOSE_ROUNDED,
                        tooltip="Cancel",
                        on_click=lambda e: (set_mode(False), set_selected(set())),
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
                    _breadcrumbs(current_path, _navigate),
                    ft.Row(
                        controls=[
                            ft.IconButton(
                                ft.Icons.UPLOAD_ROUNDED,
                                tooltip="Upload",
                                on_click=lambda e: page.run_task(_upload, e),
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
                tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, tokens.SPACE_SM
            ),
            bgcolor=ft.Colors.SURFACE,
        )

    return ft.Column(
        controls=[
            toolbar,
            ft.Divider(height=1, thickness=1),
            build_banner_ad(page),
            ft.Container(content=body, expand=True, padding=0),
        ],
        spacing=0,
        expand=True,
    )

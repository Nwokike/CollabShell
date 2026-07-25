import posixpath

import flet as ft

from components.file_item import build_file_item
from core import tokens


async def load_files_impl(ctrl, path=None):
    if path is not None:
        ctrl.current_path = path
        ctrl.state.current_path = path
    ctrl.is_loading = True

    ctrl.selected_files.clear()
    ctrl.action_bar_container.content = ctrl.build_action_bar()
    ctrl.upload_fab.visible = True
    try:
        ctrl.action_bar_container.update()
        ctrl.upload_fab.update()
    except Exception:
        pass

    ctrl.file_list_container.content = ctrl.build_file_list()
    try:
        ctrl.file_list_container.update()
    except Exception:
        pass

    try:
        ctrl.files = await ctrl.colab_service.ls(
            path=ctrl.current_path,
            session_name=ctrl.session_name,
            auth_method=ctrl.state.auth_method,
        )
        ctrl.state.file_listing = ctrl.files
    except Exception as ex:
        if ctrl.snack:
            ctrl.snack(f"Error: {ex}")
        ctrl.files = []
    ctrl.is_loading = False

    ctrl.file_list_container.content = ctrl.build_file_list()
    ctrl.breadcrumb_container.content = ctrl.build_breadcrumb()
    try:
        ctrl.file_list_container.update()
        ctrl.breadcrumb_container.update()
    except Exception:
        pass


def on_file_tap_impl(ctrl, file_info):
    name = file_info.get("name")
    if name in ctrl.selected_files:
        ctrl.selected_files.remove(name)
    else:
        ctrl.selected_files.add(name)

    ctrl.file_list_container.content = ctrl.build_file_list()
    ctrl.action_bar_container.content = ctrl.build_action_bar()
    ctrl.upload_fab.visible = len(ctrl.selected_files) == 0
    try:
        ctrl.file_list_container.update()
        ctrl.action_bar_container.update()
        ctrl.upload_fab.update()
    except Exception:
        pass


def build_breadcrumb_impl(ctrl):
    clean_path = posixpath.normpath(ctrl.current_path)
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
            on_click=(lambda e: ctrl.page.run_task(ctrl.load_files, "/"))
            if parts
            else None,
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
                    color=ft.Colors.PRIMARY if not is_last else ft.Colors.ON_SURFACE,
                    padding=ft.Padding(tokens.SPACE_SM, 0, tokens.SPACE_SM, 0),
                ),
                on_click=(
                    lambda e, p=path_so_far: ctrl.page.run_task(ctrl.load_files, p)
                )
                if not is_last
                else None,
            )
        )
    return ft.Row(controls=controls, spacing=0, wrap=True)


def build_file_list_impl(ctrl):
    if ctrl.is_loading:
        return ft.Container(
            content=ft.ProgressRing(width=tokens.SPINNER_LG, height=tokens.SPINNER_LG),
            alignment=ft.Alignment.CENTER,
            padding=tokens.SPACE_XXL,
        )

    if not ctrl.files:
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
                selected=f.get("name") in ctrl.selected_files,
                on_click=lambda e, fi=f: ctrl.on_file_tap(fi),
            )
            for f in ctrl.files
        ],
        spacing=tokens.SPACE_XXS,
    )

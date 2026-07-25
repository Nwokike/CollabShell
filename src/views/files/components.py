import posixpath

import flet as ft

from core import tokens
from views.files.actions import do_delete_selected_impl, do_download_selected_impl


def build_action_bar_impl(ctrl):
    if not ctrl.selected_files:
        return ft.Container()

    selected_items = [f for f in ctrl.files if f["name"] in ctrl.selected_files]
    num_selected = len(ctrl.selected_files)

    can_open = num_selected == 1 and selected_items[0].get("type") == "directory"
    can_download = True

    actions = []
    if can_open:
        item = selected_items[0]
        raw_path = posixpath.join(ctrl.current_path, item["name"])
        new_path = posixpath.normpath(raw_path)
        actions.append(
            ft.FilledButton(
                "Open",
                icon=ft.Icons.FOLDER_OPEN_ROUNDED,
                on_click=lambda e: ctrl.page.run_task(ctrl.load_files, new_path),
            )
        )

    if can_download:
        actions.append(
            ft.FilledTonalButton(
                "Download",
                icon=ft.Icons.DOWNLOAD_ROUNDED,
                on_click=lambda e: ctrl.page.run_task(do_download_selected_impl, ctrl),
            )
        )

    actions.append(
        ft.TextButton(
            "Delete",
            icon=ft.Icons.DELETE_ROUNDED,
            style=ft.ButtonStyle(color=ft.Colors.ERROR),
            on_click=lambda e: ctrl.page.run_task(do_delete_selected_impl, ctrl),
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
        shadow=ft.BoxShadow(spread_radius=1, blur_radius=10, color=ft.Colors.BLACK_12),
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

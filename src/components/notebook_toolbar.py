import flet as ft
from core import tokens
from core.theme import AppColors


def build_notebook_toolbar(
    on_add_code,
    on_add_markdown,
    on_clear_all,
    on_export_ipynb=None,
    on_import_ipynb=None,
    on_open_terminal=None,
) -> ft.Container:
    trailing = [
        ft.IconButton(
            ft.Icons.UPLOAD_FILE_ROUNDED,
            tooltip="Import IPYNB",
            on_click=on_import_ipynb,
            icon_size=tokens.ICON_SM,
        )
        if on_import_ipynb
        else ft.Container(),
        ft.IconButton(
            ft.Icons.DOWNLOAD_ROUNDED,
            tooltip="Export IPYNB",
            on_click=on_export_ipynb,
            icon_size=tokens.ICON_SM,
        )
        if on_export_ipynb
        else ft.Container(),
        ft.IconButton(
            ft.Icons.DELETE_SWEEP_ROUNDED,
            tooltip="Clear All Outputs",
            on_click=on_clear_all,
            icon_color=AppColors.ERROR,
            icon_size=tokens.ICON_SM,
        ),
    ]

    return ft.Container(
        content=ft.Row(
            controls=[
                ft.FilledButton(
                    "+ Code",
                    icon=ft.Icons.CODE_ROUNDED,
                    on_click=on_add_code,
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=tokens.RADIUS_MD),
                    ),
                ),
                ft.FilledButton(
                    "+ Markdown",
                    icon=ft.Icons.EDIT_NOTE_ROUNDED,
                    on_click=on_add_markdown,
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE),
                        color=ft.Colors.ON_SURFACE,
                        shape=ft.RoundedRectangleBorder(radius=tokens.RADIUS_MD),
                    ),
                ),
                ft.FilledButton(
                    "Terminal",
                    icon=ft.Icons.TERMINAL_ROUNDED,
                    on_click=on_open_terminal,
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.PRIMARY),
                        color=ft.Colors.PRIMARY,
                        shape=ft.RoundedRectangleBorder(radius=tokens.RADIUS_MD),
                    ),
                )
                if on_open_terminal
                else ft.Container(),
                ft.Container(expand=True),
                *trailing,
            ],
            alignment=ft.MainAxisAlignment.START,
            spacing=tokens.SPACE_SM,
        ),
        padding=ft.Padding(
            tokens.SPACE_MD, tokens.SPACE_SM, tokens.SPACE_MD, tokens.SPACE_SM
        ),
        bgcolor=ft.Colors.with_opacity(0.8, ft.Colors.SURFACE),
        blur=ft.Blur(10, 10, ft.BlurTileMode.MIRROR),
        border=ft.Border(
            top=ft.BorderSide(1, ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE))
        ),
    )

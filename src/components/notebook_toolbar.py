import flet as ft

from core import tokens


def build_notebook_toolbar(
    on_add_code,
    on_add_markdown,
    on_clear_all=None,
    on_export_ipynb=None,
    on_import_ipynb=None,
    on_open_terminal=None,
) -> ft.Container:
    """Bottom toolbar for adding cells. Import/export are also exposed here
    (in addition to the session FAB overflow menu) so they're easy to reach."""
    trailing = [
        ft.IconButton(
            ft.Icons.UPLOAD_FILE_ROUNDED,
            tooltip="Import IPYNB or PY",
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

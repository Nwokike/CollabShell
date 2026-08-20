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
    """Bottom toolbar for adding cells. Import/export/clear-all moved to the
    session FAB overflow menu to avoid duplicate controls."""
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

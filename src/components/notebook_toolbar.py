import flet as ft
from core import tokens
from core.theme import AppColors


def build_notebook_toolbar(
    on_add_code,
    on_add_markdown,
    on_clear_all,
) -> ft.Container:
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
                ft.IconButton(
                    ft.Icons.DELETE_SWEEP_ROUNDED,
                    tooltip="Clear All Outputs",
                    on_click=on_clear_all,
                    icon_color=AppColors.ERROR,
                ),
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

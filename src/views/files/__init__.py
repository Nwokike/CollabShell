import flet as ft

from components.brand_header import build_brand_header
from core import tokens
from core.styles import build_banner_ad
from views.files.controller import FilesController


def build_files_view(
    page: ft.Page,
    colab_service,
    state,
    session_name: str,
    on_back=None,
    snack=None,
    theme_btn=None,
) -> ft.View:
    ctrl = FilesController(
        page=page,
        colab_service=colab_service,
        state=state,
        session_name=session_name,
        on_back=on_back,
        snack=snack,
        theme_btn=theme_btn,
    )

    appbar_actions = [
        ft.IconButton(
            icon=ft.Icons.REFRESH_ROUNDED,
            on_click=lambda e: page.run_task(ctrl.load_files),
            tooltip="Refresh",
            icon_size=tokens.ICON_MD,
        ),
    ]
    if theme_btn:
        appbar_actions.append(theme_btn)

    page.run_task(ctrl.load_files)

    view_content = ft.Column(
        controls=[
            build_brand_header(),
            ft.Column(
                controls=[
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.IconButton(
                                    icon=ft.Icons.ARROW_UPWARD_ROUNDED,
                                    icon_size=tokens.ICON_MD,
                                    on_click=ctrl.on_navigate_up,
                                    tooltip="Go up",
                                ),
                                ctrl.breadcrumb_container,
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=tokens.SPACE_XS,
                        ),
                        padding=ft.Padding(tokens.SPACE_SM, 0, tokens.SPACE_SM, 0),
                    ),
                    ft.Divider(height=1),
                    ctrl.file_list_container,
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
        controls=[view_content, ctrl.action_bar_container],
        floating_action_button=ctrl.upload_fab,
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

import flet as ft

from core import tokens
from views.onboarding.controller import make_slide_controller
from views.onboarding.oauth_handler import make_auth_handlers


def build_onboarding_view(
    page: ft.Page,
    colab_service,
    state,
    storage,
    on_complete=None,
    snack=None,
) -> ft.View:
    current_page = {"index": 0}
    indicator_row = ft.Ref[ft.Row]()
    slide_container = ft.Ref[ft.Container]()
    next_btn = ft.Ref[ft.FilledButton]()
    back_btn = ft.Ref[ft.TextButton]()

    sign_in_btn = ft.Ref[ft.FilledButton]()
    auth_code_field = ft.Ref[ft.TextField]()
    auth_status_text = ft.Ref[ft.Text]()
    auth_url_text = ft.Ref[ft.Text]()
    verify_btn = ft.Ref[ft.FilledTonalButton]()

    start_auth, submit_code = make_auth_handlers(
        page,
        colab_service,
        state,
        sign_in_btn,
        auth_url_text,
        auth_code_field,
        verify_btn,
        auth_status_text,
        next_btn,
    )

    build_slide, build_indicators, _update_view, on_next, on_back, on_swipe = (
        make_slide_controller(
            page,
            state,
            storage,
            on_complete,
            current_page,
            slide_container,
            indicator_row,
            back_btn,
            next_btn,
            sign_in_btn,
            auth_url_text,
            auth_code_field,
            verify_btn,
            auth_status_text,
            start_auth,
            submit_code,
        )
    )

    nav_row = ft.Container(
        content=ft.Row(
            controls=[
                ft.TextButton(
                    content=ft.Text("Back"),
                    ref=back_btn,
                    on_click=on_back,
                    visible=False,
                ),
                ft.Row(
                    ref=indicator_row,
                    controls=build_indicators(),
                    spacing=tokens.SPACE_SM,
                ),
                ft.FilledButton(
                    content=ft.Text("Next"),
                    ref=next_btn,
                    on_click=on_next,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(
            tokens.SPACE_LG, tokens.SPACE_MD, tokens.SPACE_LG, tokens.SPACE_XL
        ),
    )

    slide_content_container = ft.GestureDetector(
        content=ft.Container(
            ref=slide_container,
            content=build_slide(0),
            expand=True,
            padding=ft.Padding(tokens.SPACE_XL, 0, tokens.SPACE_XL, 0),
        ),
        on_horizontal_drag_end=on_swipe,
    )

    return ft.View(
        route="/onboarding",
        controls=[
            ft.SafeArea(
                content=ft.Column(
                    controls=[slide_content_container, nav_row],
                    expand=True,
                    spacing=0,
                ),
                expand=True,
            )
        ],
        padding=0,
    )

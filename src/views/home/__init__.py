import flet as ft

from components.brand_header import build_brand_header
from core import constants, tokens
from core.styles import build_banner_ad
from core.theme import AppColors
from views.home.actions import action_button, show_session_selector
from views.home.sessions import build_sessions_section


def build_home_view(
    page: ft.Page,
    colab_service,
    state,
    on_new_session=None,
    on_session_tap=None,
    navigate=None,
    on_refresh=None,
    storage=None,
) -> ft.View:
    header = build_brand_header()

    auth_status_chip = ft.Container(
        content=ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.CHECK_CIRCLE_ROUNDED
                    if state.is_authenticated
                    else ft.Icons.WARNING_ROUNDED,
                    size=tokens.ICON_SM,
                    color=AppColors.SUCCESS
                    if state.is_authenticated
                    else AppColors.WARNING,
                ),
                ft.Text(
                    f"Signed in as {state.auth_email}"
                    if state.is_authenticated
                    else "Not signed in",
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            spacing=tokens.SPACE_SM,
            alignment=ft.MainAxisAlignment.START,
        ),
        padding=ft.Padding(
            tokens.SPACE_MD,
            tokens.SPACE_SM,
            tokens.SPACE_MD,
            tokens.SPACE_SM,
        ),
        border_radius=tokens.RADIUS_PILL,
        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
        margin=ft.Margin(tokens.SPACE_LG, 0, tokens.SPACE_LG, tokens.SPACE_SM),
    )

    quick_actions = ft.Container(
        content=ft.Row(
            controls=[
                action_button(
                    ft.Icons.NOTE_ADD_ROUNDED,
                    "Notebooks",
                    lambda e: show_session_selector(
                        page, colab_service, state, "notebook", on_new_session, navigate
                    ),
                ),
                action_button(
                    ft.Icons.TERMINAL_ROUNDED,
                    "Terminal",
                    lambda e: show_session_selector(
                        page, colab_service, state, "terminal", on_new_session, navigate
                    ),
                    AppColors.BADGE_TPU,
                ),
                action_button(
                    ft.Icons.FOLDER_ROUNDED,
                    "Cloud Files",
                    lambda e: show_session_selector(
                        page, colab_service, state, "files", on_new_session, navigate
                    ),
                    AppColors.BADGE_GPU,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_EVENLY,
        ),
        padding=ft.Padding(tokens.SPACE_SM, 0, tokens.SPACE_SM, 0),
    )

    sessions_section_header, sessions_list, load_sessions = build_sessions_section(
        page, colab_service, state, on_session_tap, storage
    )

    content = ft.Column(
        controls=[
            header,
            auth_status_chip,
            quick_actions,
            ft.Divider(height=tokens.SPACE_SM, color=ft.Colors.TRANSPARENT),
            sessions_section_header,
            sessions_list,
            ft.Divider(height=tokens.SPACE_SM, color=ft.Colors.TRANSPARENT),
            build_banner_ad(page),
        ],
        spacing=0,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    return ft.View(
        route="/home",
        controls=[content],
        padding=0,
        appbar=ft.AppBar(
            title=ft.Text(constants.APP_NAME, weight=ft.FontWeight.BOLD),
            center_title=False,
            bgcolor=ft.Colors.SURFACE,
        ),
    )

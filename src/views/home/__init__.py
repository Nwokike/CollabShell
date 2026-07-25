import flet as ft

from components.brand_header import build_brand_header
from core import constants, tokens
from core.styles import build_native_ad
from core.theme import AppColors
from views.home.actions import action_button
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
                    lambda e: page.run_task(navigate, "/notebooks_tab"),
                ),
                action_button(
                    ft.Icons.TERMINAL_ROUNDED,
                    "Terminal",
                    lambda e: page.run_task(navigate, "/terminals_tab"),
                    AppColors.BADGE_TPU,
                ),
                action_button(
                    ft.Icons.FOLDER_ROUNDED,
                    "Cloud Files",
                    lambda e: page.run_task(navigate, "/files_tab"),
                    AppColors.BADGE_GPU,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_EVENLY,
        ),
        padding=ft.Padding(tokens.SPACE_SM, 0, tokens.SPACE_SM, 0),
    )

    def _feature_card(icon: str, title: str, desc: str, color: str) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Container(
                        content=ft.Icon(icon, size=tokens.ICON_LG, color=color),
                        width=tokens.ICON_CONTAINER_SM,
                        height=tokens.ICON_CONTAINER_SM,
                        border_radius=tokens.RADIUS_MD,
                        bgcolor=ft.Colors.with_opacity(tokens.OPACITY_ACCENT, color),
                        alignment=ft.Alignment.CENTER,
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(
                                title, size=tokens.FONT_SM, weight=ft.FontWeight.W_600
                            ),
                            ft.Text(
                                desc,
                                size=tokens.FONT_XS,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                                max_lines=3,
                                overflow="ellipsis",
                            ),
                        ],
                        spacing=tokens.SPACE_NANO,
                        expand=True,
                    ),
                ],
                spacing=tokens.SPACE_MD,
                vertical_alignment="start",
            ),
            padding=tokens.SPACE_LG,
            border_radius=tokens.RADIUS_MD,
            bgcolor=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.ON_SURFACE),
            border=ft.Border.all(
                tokens.DIVIDER_THICKNESS,
                ft.Colors.with_opacity(tokens.OPACITY_CONTAINER, ft.Colors.ON_SURFACE),
            ),
        )

    def _step_row(number: str, title: str, desc: str) -> ft.Row:
        return ft.Row(
            controls=[
                ft.Container(
                    content=ft.Text(
                        number,
                        size=tokens.FONT_SM,
                        weight=ft.FontWeight.W_700,
                        color=ft.Colors.WHITE,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    width=tokens.STEP_BADGE_SIZE,
                    height=tokens.STEP_BADGE_SIZE,
                    border_radius=tokens.STEP_BADGE_RADIUS,
                    bgcolor=ft.Colors.PRIMARY,
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Column(
                    controls=[
                        ft.Text(title, size=tokens.FONT_SM, weight=ft.FontWeight.W_600),
                        ft.Text(
                            desc,
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    spacing=tokens.SPACE_XXS,
                    expand=True,
                ),
            ],
            spacing=tokens.SPACE_MD,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    features_section = ft.Container(
        content=ft.Column(
            controls=[
                ft.Text(
                    "What Collab Shell Can Do",
                    size=tokens.FONT_MD,
                    weight=ft.FontWeight.W_600,
                ),
                ft.Container(height=tokens.SPACE_SM),
                _feature_card(
                    ft.Icons.MENU_BOOK_ROUNDED,
                    "Interactive Jupyter Notebooks",
                    "Open and run .ipynb notebooks, execute code cell by cell, and view rich Markdown and outputs.",
                    AppColors.BADGE_GPU,
                ),
                _feature_card(
                    ft.Icons.TERMINAL_ROUNDED,
                    "Full Interactive Terminal",
                    "Real-time bash shell access to your cloud runtime with live stdin/stdout streaming.",
                    AppColors.BADGE_TPU,
                ),
                _feature_card(
                    ft.Icons.MEMORY_ROUNDED,
                    "Free Hardware Accelerators",
                    "Harness Google Colab's free CPU, T4 GPU, and TPU v2/v3 runtimes for heavy computation.",
                    ft.Colors.PRIMARY,
                ),
                _feature_card(
                    ft.Icons.FOLDER_SPECIAL_ROUNDED,
                    "Cloud File Explorer",
                    "Browse, upload, download, and manage remote workspace files in your Colab container.",
                    AppColors.SUCCESS,
                ),
            ],
            spacing=tokens.SPACE_MD,
        ),
        padding=ft.Padding(
            left=tokens.SPACE_LG,
            right=tokens.SPACE_LG,
            top=tokens.SPACE_LG,
            bottom=tokens.SPACE_SM,
        ),
    )

    how_it_works = ft.Container(
        content=ft.Column(
            controls=[
                ft.Text(
                    "How It Works",
                    size=tokens.FONT_MD,
                    weight=ft.FontWeight.W_600,
                ),
                ft.Container(height=tokens.SPACE_SM),
                _step_row(
                    "1", "Sign In", "Authenticate securely with your Google account"
                ),
                _step_row(
                    "2",
                    "Create Session",
                    "Start a workspace session and select your hardware",
                ),
                _step_row(
                    "3",
                    "Start Coding",
                    "Navigate to Notebooks or Terminal from the bottom bar",
                ),
            ],
            spacing=tokens.SPACE_MD,
        ),
        padding=ft.Padding(
            left=tokens.SPACE_LG,
            right=tokens.SPACE_LG,
            top=tokens.SPACE_LG,
            bottom=tokens.SPACE_SM,
        ),
    )

    sessions_section_header, sessions_list, _load_sessions = build_sessions_section(
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
            build_native_ad(page, size="medium"),
            ft.Divider(height=tokens.SPACE_SM, color=ft.Colors.TRANSPARENT),
            features_section,
            build_native_ad(page, size="small"),
            how_it_works,
            build_native_ad(page, size="medium"),
            ft.Container(height=tokens.ICON_XXXL),
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

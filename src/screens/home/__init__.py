"""HomeScreen — session list, quick actions, offline banner, and feature overview."""

import logging

import flet as ft

from components.brand_header import build_brand_header
from components.new_session_sheet import show_new_session_sheet
from components.session_card import build_session_card
from core import constants, tokens
from core.styles import build_banner_ad, glass_card
from core.theme import AppColors, adaptive_glass_bg
from screens.home.cards import action_button, feature_card, step_row
from state import AppStateCtx, ControllerMethodsCtx, ServiceCtx

logger = logging.getLogger("HomeScreen")


@ft.component
def HomeScreen() -> ft.Control:
    """Landing dashboard — active sessions, quick action launch, features and guide."""
    state = ft.use_context(AppStateCtx)
    services = ft.use_context(ServiceCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    page = ft.context.page

    sessions, set_sessions = ft.use_state([])
    is_loading, set_loading = ft.use_state(False)

    async def _load_sessions():
        set_loading(True)
        try:
            data = await services.colab.list_sessions(auth_method=state.auth_method)
            state.active_sessions = data or []
            set_sessions(list(state.active_sessions))
            # Clean up orphaned notebooks
            try:
                names = [s.get("name") for s in state.active_sessions if s.get("name")]
                await services.storage.cleanup_orphaned_notebooks(names)
            except Exception as ex:
                logger.warning("Orphaned notebook cleanup non-fatal error: %s", ex)
        except Exception:
            logger.exception("Failed to load active sessions")
            state.active_sessions = []
            set_sessions([])
        finally:
            set_loading(False)

    ft.on_mounted(lambda: page.run_task(_load_sessions))

    def _on_session_tap(session: dict):
        controller.open_session(session.get("name", ""), "notebook")

    def _on_new_session(mode: str):
        show_new_session_sheet(
            page=page,
            state=state,
            colab_service=services.colab,
            ad_service=services.ad_service,
            on_session_created=lambda name: controller.open_session(name, mode),
            snack_func=controller.show_snack,
            mode=mode,
            ignore_warning=False,
        )

    # ── Offline banner ────────────────────────────────────────────────────────
    offline_banner = ft.Container(
        content=ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.WIFI_OFF_ROUNDED,
                    color=ft.Colors.ON_ERROR_CONTAINER,
                    size=tokens.ICON_SM,
                ),
                ft.Text(
                    "You're offline. Some features may be unavailable.",
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_ERROR_CONTAINER,
                    expand=True,
                ),
            ],
            spacing=tokens.SPACE_SM,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(
            tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, tokens.SPACE_SM
        ),
        bgcolor=ft.Colors.ERROR_CONTAINER,
        visible=not state.is_online,
    )

    # ── Update banner ─────────────────────────────────────────────────────────
    update_banner = ft.Container(
        content=ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.SYSTEM_UPDATE_ROUNDED,
                    color=ft.Colors.ON_TERTIARY_CONTAINER,
                    size=tokens.ICON_SM,
                ),
                ft.Text(
                    f"Update available: v{state.update_available_version}",
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_TERTIARY_CONTAINER,
                    expand=True,
                ),
                ft.TextButton(
                    "Update",
                    style=ft.ButtonStyle(color=ft.Colors.ON_TERTIARY_CONTAINER),
                    on_click=lambda e: page.run_task(
                        ft.UrlLauncher().launch_url,
                        getattr(
                            constants,
                            "PLAY_STORE_URL",
                            "https://play.google.com/store/apps/details?id=ng.kiri.collabshell",
                        ),
                    ),
                ),
            ],
            spacing=tokens.SPACE_SM,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(
            tokens.SPACE_LG, tokens.SPACE_SM, tokens.SPACE_LG, tokens.SPACE_SM
        ),
        bgcolor=ft.Colors.TERTIARY_CONTAINER,
        visible=bool(state.update_available_version),
    )

    # ── Auth status chip ──────────────────────────────────────────────────────
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
        bgcolor=adaptive_glass_bg(),
        margin=ft.Margin(tokens.SPACE_LG, 0, tokens.SPACE_LG, tokens.SPACE_SM),
    )

    # ── Sessions list content ─────────────────────────────────────────────────
    if is_loading:
        sessions_content: ft.Control = ft.Container(
            content=ft.ProgressRing(width=tokens.SPINNER_LG, height=tokens.SPINNER_LG),
            alignment=ft.Alignment.CENTER,
            padding=tokens.SPACE_XXL,
        )
    elif not sessions:
        sessions_content = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(
                        ft.Icons.STORAGE_ROUNDED,
                        size=tokens.ICON_XXL,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    ft.Text(
                        "No active sessions",
                        size=tokens.FONT_MD,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        weight=ft.FontWeight.W_500,
                    ),
                    ft.Text(
                        "Tap New Notebook, Terminal, or Files to create one.",
                        size=tokens.FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=tokens.SPACE_SM,
            ),
            alignment=ft.Alignment.CENTER,
            padding=tokens.SPACE_XXL,
        )
    else:
        sessions_content = ft.Column(
            controls=[
                build_session_card(
                    session=s, on_click=lambda e, s=s: _on_session_tap(s)
                )
                for s in sessions
            ],
            spacing=0,
        )

    # ── Features section ──────────────────────────────────────────────────────
    features_section = ft.Container(
        content=ft.Column(
            controls=[
                ft.Text(
                    "What CollabShell Can Do",
                    size=tokens.FONT_MD,
                    weight=ft.FontWeight.W_600,
                ),
                ft.Container(height=tokens.SPACE_SM),
                feature_card(
                    ft.Icons.MENU_BOOK_ROUNDED,
                    "Interactive Jupyter Notebooks",
                    "Open and run .ipynb notebooks, execute code cell by cell, and view rich Markdown and outputs.",
                    AppColors.BADGE_GPU,
                ),
                feature_card(
                    ft.Icons.TERMINAL_ROUNDED,
                    "Full Interactive Terminal",
                    "Real-time bash shell access to your cloud runtime with live stdin/stdout streaming.",
                    AppColors.BADGE_TPU,
                ),
                feature_card(
                    ft.Icons.MEMORY_ROUNDED,
                    "Free Hardware Accelerators",
                    "Harness Google Colab's free CPU, T4 GPU, and TPU v2/v3 runtimes for heavy computation.",
                    ft.Colors.PRIMARY,
                ),
                feature_card(
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

    # ── How It Works section ──────────────────────────────────────────────────
    how_it_works = ft.Container(
        content=ft.Column(
            controls=[
                ft.Text(
                    "How It Works",
                    size=tokens.FONT_MD,
                    weight=ft.FontWeight.W_600,
                ),
                ft.Container(height=tokens.SPACE_SM),
                step_row(
                    "1",
                    "Sign In",
                    "Authenticate securely with your Google account",
                ),
                step_row(
                    "2",
                    "Create Session",
                    "Start a workspace session and select your hardware",
                ),
                step_row(
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

    return ft.Column(
        controls=[
            build_brand_header(),
            offline_banner,
            update_banner,
            auth_status_chip,
            # Quick actions
            ft.Container(
                content=ft.Column(
                    controls=[
                        glass_card(
                            ft.Row(
                                controls=[
                                    action_button(
                                        ft.Icons.EDIT_NOTE_ROUNDED,
                                        constants.LBL_NEW_NOTEBOOK,
                                        lambda e: _on_new_session("notebook"),
                                    ),
                                    action_button(
                                        ft.Icons.TERMINAL_ROUNDED,
                                        constants.LBL_NEW_TERMINAL,
                                        lambda e: _on_new_session("terminal"),
                                    ),
                                    action_button(
                                        ft.Icons.FOLDER_ROUNDED,
                                        constants.LBL_FILES,
                                        lambda e: _on_new_session("files"),
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_AROUND,
                            ),
                            margin=ft.Margin(
                                tokens.SPACE_LG,
                                tokens.SPACE_XS,
                                tokens.SPACE_LG,
                                tokens.SPACE_XS,
                            ),
                        ),
                    ],
                ),
                padding=ft.Padding(0, tokens.SPACE_SM, 0, 0),
            ),
            # Sessions header & list
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Text(
                            constants.LBL_ACTIVE_SESSIONS,
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.W_700,
                            color=ft.Colors.PRIMARY,
                            style=ft.TextStyle(letter_spacing=1),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.REFRESH_ROUNDED,
                            icon_size=tokens.ICON_SM,
                            tooltip="Refresh",
                            on_click=lambda e: page.run_task(_load_sessions),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding(
                    tokens.SPACE_LG, tokens.SPACE_MD, tokens.SPACE_LG, tokens.SPACE_XS
                ),
            ),
            ft.Container(
                content=sessions_content,
                padding=ft.Padding(
                    tokens.SPACE_LG, 0, tokens.SPACE_LG, tokens.SPACE_LG
                ),
            ),
            build_banner_ad(page),
            features_section,
            build_banner_ad(page),
            how_it_works,
            ft.Container(height=tokens.ICON_XXXL),
        ],
        spacing=0,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

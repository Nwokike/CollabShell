"""HomeScreen — Dashboard overview with quick actions, active sessions, feature cards, and guides."""

from __future__ import annotations

import flet as ft

from components.brand_header import build_brand_header
from components.session_card import build_session_card
from core import constants, tokens
from core.styles import build_banner_ad, glass_card, section_header
from core.theme import AppColors
from state import AppStateCtx, ControllerMethodsCtx, ServiceCtx


def _action_button(icon, label, on_click, color=None) -> ft.Control:
    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Container(
                    content=ft.Icon(
                        icon,
                        size=tokens.ICON_LG,
                        color=color or ft.Colors.PRIMARY,
                    ),
                    width=tokens.CARD_ICON_CONTAINER,
                    height=tokens.CARD_ICON_CONTAINER,
                    border_radius=tokens.RADIUS_MD,
                    bgcolor=ft.Colors.with_opacity(
                        tokens.OPACITY_ACCENT, color or ft.Colors.PRIMARY
                    ),
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Text(
                    label,
                    size=tokens.FONT_XS,
                    weight=ft.FontWeight.W_500,
                    text_align=ft.TextAlign.CENTER,
                    color=ft.Colors.ON_SURFACE,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=tokens.SPACE_XS,
        ),
        on_click=on_click,
        ink=True,
        border_radius=tokens.RADIUS_MD,
        padding=tokens.SPACE_SM,
    )


def _feature_card(icon, title: str, desc: str, color: str) -> ft.Container:
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
                            title,
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.W_600,
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
            vertical_alignment=ft.CrossAxisAlignment.START,
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


@ft.component
def HomeScreen() -> ft.Control:
    """Home dashboard screen with actions, sessions, and educational content."""
    state = ft.use_context(AppStateCtx)
    services = ft.use_context(ServiceCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    page = ft.context.page

    # Refresh sessions on mount
    async def _refresh():
        try:
            sessions = await services.colab.list_sessions(auth_method=state.auth_method)
            state.active_sessions = sessions or []
        except Exception:
            pass

    ft.on_mounted(lambda: page.run_task(_refresh))

    def _on_new_session(mode: str):
        controller.show_new_session_sheet(mode)

    # ── Offline banner ────────────────────────────────────────────────────────
    offline_banner = ft.Container(
        content=ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.CLOUD_OFF_ROUNDED,
                    size=tokens.ICON_SM,
                    color=AppColors.WARNING,
                ),
                ft.Text(
                    "No internet connection",
                    size=tokens.FONT_XS,
                    color=AppColors.WARNING,
                    weight=ft.FontWeight.W_600,
                ),
            ],
            spacing=tokens.SPACE_XS,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=ft.Colors.with_opacity(0.12, AppColors.WARNING),
        padding=ft.Padding(0, tokens.SPACE_XS, 0, tokens.SPACE_XS),
        visible=not state.is_online,
        alignment=ft.Alignment.CENTER,
    )

    # ── Auth Status Chip ──────────────────────────────────────────────────────
    auth_status_chip = ft.Container(
        content=ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.ACCOUNT_CIRCLE_ROUNDED
                    if state.is_authenticated
                    else ft.Icons.ERROR_ROUNDED,
                    size=tokens.ICON_SM,
                    color=AppColors.SUCCESS
                    if state.is_authenticated
                    else AppColors.WARNING,
                ),
                ft.Text(
                    f"Signed in as {state.auth_email}"
                    if state.is_authenticated
                    else "Not signed in · Tap to sign in",
                    size=tokens.FONT_XS,
                    weight=ft.FontWeight.W_500,
                    color=ft.Colors.ON_SURFACE,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=tokens.SPACE_XS,
        ),
        padding=ft.Padding(
            tokens.SPACE_MD, tokens.SPACE_XS, tokens.SPACE_MD, tokens.SPACE_XS
        ),
        border_radius=tokens.RADIUS_PILL,
        bgcolor=ft.Colors.with_opacity(tokens.OPACITY_SUBTLE, ft.Colors.ON_SURFACE),
        border=ft.Border.all(
            tokens.DIVIDER_THICKNESS,
            ft.Colors.with_opacity(tokens.OPACITY_CONTAINER, ft.Colors.ON_SURFACE),
        ),
        alignment=ft.Alignment.CENTER,
        margin=ft.Margin(tokens.SPACE_LG, 0, tokens.SPACE_LG, 0),
    )

    # ── Quick Actions ─────────────────────────────────────────────────────────
    quick_actions = ft.Container(
        content=ft.Column(
            controls=[
                glass_card(
                    ft.Row(
                        controls=[
                            _action_button(
                                ft.Icons.EDIT_NOTE_ROUNDED,
                                constants.LBL_NEW_NOTEBOOK,
                                lambda e: _on_new_session("notebook"),
                            ),
                            _action_button(
                                ft.Icons.TERMINAL_ROUNDED,
                                constants.LBL_NEW_TERMINAL,
                                lambda e: _on_new_session("terminal"),
                            ),
                            _action_button(
                                ft.Icons.FOLDER_ROUNDED,
                                constants.LBL_FILES,
                                lambda e: _on_new_session("files"),
                            ),
                            _action_button(
                                ft.Icons.HISTORY_ROUNDED,
                                constants.LBL_HISTORY,
                                lambda e: controller.open_history(),
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
    )

    # ── Active Sessions Section ───────────────────────────────────────────────
    session_cards = []
    if state.active_sessions:
        for s in state.active_sessions:
            name = s.get("name", "Unknown")
            session_cards.append(
                build_session_card(
                    session=s,
                    on_click=lambda e, n=name: controller.open_session(n, "notebook"),
                )
            )
    else:
        session_cards.append(
            ft.Container(
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
                        ),
                        ft.Text(
                            "Create a notebook or terminal to begin",
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
        )

    # ── Educational / Feature sections ────────────────────────────────────────
    features_section = ft.Container(
        content=ft.Column(
            controls=[
                section_header("WHAT COLAB SHELL CAN DO"),
                ft.Container(height=tokens.SPACE_XS),
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
        padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, 0),
    )

    how_it_works = ft.Container(
        content=ft.Column(
            controls=[
                section_header("HOW IT WORKS"),
                ft.Container(height=tokens.SPACE_XS),
                _step_row(
                    "1",
                    "Sign In",
                    "Authenticate securely with your Google account",
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
        padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, 0),
    )

    return ft.Column(
        controls=[
            offline_banner,
            build_brand_header(),
            auth_status_chip,
            quick_actions,
            ft.Container(height=tokens.SPACE_SM),
            section_header(constants.LBL_ACTIVE_SESSIONS.upper()),
            ft.Column(controls=session_cards, spacing=0),
            build_banner_ad(page),
            ft.Container(height=tokens.SPACE_SM),
            features_section,
            build_banner_ad(page),
            ft.Container(height=tokens.SPACE_SM),
            how_it_works,
            ft.Container(height=tokens.SPACE_XXXL),
        ],
        spacing=0,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )


__all__ = ["HomeScreen"]

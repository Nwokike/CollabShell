"""Home view — dashboard with sessions, quick actions, and auth status."""

from __future__ import annotations

import flet as ft

from core import tokens
from core.styles import section_header, build_banner_ad
from core.theme import AppColors
from components.session_card import build_session_card


def build_home_view(
    page: ft.Page,
    colab_service,
    state,
    on_new_session=None,
    on_session_tap=None,
    on_quick_run=None,
    on_refresh=None,
) -> ft.View:
    """Build the home dashboard view."""

    # ── Header ────────────────────────────────────────────────────────────────
    header = ft.Container(
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Container(
                            content=ft.Image(
                                src="icon.png",
                                width=40,
                                height=40,
                                fit=ft.BoxFit.CONTAIN,
                            ),
                            width=60,
                            height=60,
                            border_radius=tokens.RADIUS_LG,
                            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.PRIMARY),
                            alignment=ft.Alignment.CENTER,
                        ),
                        ft.Text(
                            "Cloud GPUs from your phone",
                            size=tokens.FONT_LG,
                            weight=ft.FontWeight.W_700,
                            expand=True,
                        ),
                    ],
                    spacing=tokens.SPACE_LG,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                # Auth status chip
                ft.Container(
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
                    ),
                    padding=ft.Padding(
                        tokens.SPACE_MD,
                        tokens.SPACE_SM,
                        tokens.SPACE_MD,
                        tokens.SPACE_SM,
                    ),
                    border_radius=tokens.RADIUS_PILL,
                    bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.ON_SURFACE),
                ),
            ],
            spacing=tokens.SPACE_MD,
        ),
        padding=ft.Padding(
            tokens.SPACE_LG, tokens.SPACE_LG, tokens.SPACE_LG, tokens.SPACE_SM
        ),
    )

    # ── Quick Actions ─────────────────────────────────────────────────────────
    def _action_button(icon, label, on_click, color=None):
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(
                        content=ft.Icon(
                            icon, size=tokens.ICON_XL, color=color or ft.Colors.PRIMARY
                        ),
                        width=56,
                        height=56,
                        border_radius=tokens.RADIUS_MD,
                        bgcolor=ft.Colors.with_opacity(0.1, color or ft.Colors.PRIMARY),
                        alignment=ft.Alignment.CENTER,
                    ),
                    ft.Text(
                        label,
                        size=tokens.FONT_XS,
                        text_align=ft.TextAlign.CENTER,
                        weight=ft.FontWeight.W_500,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=tokens.SPACE_SM,
            ),
            on_click=on_click,
            expand=True,
            ink=True,
            padding=ft.Padding(
                tokens.SPACE_SM, tokens.SPACE_MD, tokens.SPACE_SM, tokens.SPACE_MD
            ),
            border_radius=tokens.RADIUS_MD,
        )

    quick_actions = ft.Container(
        content=ft.Row(
            controls=[
                _action_button(
                    ft.Icons.ROCKET_LAUNCH_ROUNDED, "New\nSession", on_new_session
                ),
                _action_button(
                    ft.Icons.BOLT_ROUNDED,
                    "Quick\nRun",
                    on_quick_run,
                    AppColors.BADGE_TPU,
                ),
                _action_button(
                    ft.Icons.CREDIT_CARD_ROUNDED,
                    "Manage\nCompute",
                    lambda e: page.run_task(
                        ft.UrlLauncher().launch_url,
                        "https://colab.research.google.com/signup",
                    ),
                    AppColors.BADGE_GPU,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_EVENLY,
        ),
        padding=ft.Padding(tokens.SPACE_SM, 0, tokens.SPACE_SM, 0),
    )

    # ── Sessions List ─────────────────────────────────────────────────────────
    sessions_section_header = section_header("ACTIVE SESSIONS")

    if state.active_sessions:
        session_cards = [
            build_session_card(
                session=s,
                on_click=lambda e, sn=s["name"]: (
                    on_session_tap(sn) if on_session_tap else None
                ),
            )
            for s in state.active_sessions
        ]
    else:
        session_cards = [
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Icon(
                            ft.Icons.CLOUD_OFF_ROUNDED,
                            size=48,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(
                            "No active sessions",
                            size=tokens.FONT_MD,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            weight=ft.FontWeight.W_500,
                        ),
                        ft.Text(
                            "Tap 'New Session' to create a cloud runtime",
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=tokens.SPACE_SM,
                ),
                padding=ft.Padding(
                    tokens.SPACE_XL, tokens.SPACE_XXL, tokens.SPACE_XL, tokens.SPACE_XXL
                ),
                alignment=ft.Alignment.CENTER,
            )
        ]

    sessions_list = ft.Container(
        content=ft.Column(
            controls=session_cards,
            spacing=tokens.SPACE_SM,
        ),
        padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, 0),
    )

    # ── Full view ─────────────────────────────────────────────────────────────
    content = ft.Column(
        controls=[
            header,
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
    )

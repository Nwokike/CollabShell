"""Home view — dashboard with sessions, quick actions, and auth status."""

from __future__ import annotations

import asyncio

import flet as ft

from core import tokens, constants
from core.styles import build_banner_ad
from core.theme import AppColors
from components.session_card import build_session_card


def build_home_view(
    page: ft.Page,
    colab_service,
    state,
    on_new_session=None,
    on_session_tap=None,
    on_quick_run=None,
    on_quick_terminal=None,
    on_cloud_files=None,
    on_refresh=None,
    storage=None,
) -> ft.View:
    """Build the home dashboard view."""

    # ── Header ────────────────────────────────────────────────────────────────
    from components.brand_header import build_brand_header

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

    # ── Quick Actions ─────────────────────────────────────────────────────────
    def _action_button(icon, label, on_click, color=None):
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(
                        content=ft.Icon(
                            icon, size=tokens.ICON_XL, color=color or ft.Colors.PRIMARY
                        ),
                        width=tokens.CARD_ICON_CONTAINER,
                        height=tokens.CARD_ICON_CONTAINER,
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
                    ft.Icons.NOTEBOOK_ROUNDED,
                    "New\nNotebook",
                    on_new_session,
                ),
                _action_button(
                    ft.Icons.TERMINAL_ROUNDED,
                    "Quick\nTerminal",
                    on_quick_terminal
                    if on_quick_terminal
                    else (on_quick_run if on_quick_run else on_new_session),
                    AppColors.BADGE_TPU,
                ),
                _action_button(
                    ft.Icons.FOLDER_ROUNDED,
                    "Cloud\nFiles",
                    on_cloud_files,
                    AppColors.BADGE_GPU,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_EVENLY,
        ),
        padding=ft.Padding(tokens.SPACE_SM, 0, tokens.SPACE_SM, 0),
    )

    # ── Sessions List ─────────────────────────────────────────────────────────
    sessions_list = ft.Container(
        content=ft.Column(spacing=tokens.SPACE_SM),
        padding=ft.Padding(tokens.SPACE_LG, 0, tokens.SPACE_LG, 0),
    )

    async def _update_sessions_ui():
        sessions_list.content.controls.clear()
        if state.is_loading:
            sessions_list.content.controls.append(
                ft.Container(
                    content=ft.ProgressRing(width=30, height=30),
                    alignment=ft.Alignment.CENTER,
                    padding=ft.Padding(0, tokens.SPACE_XXL, 0, tokens.SPACE_XXL),
                )
            )
        elif not state.active_sessions:
            sessions_list.content.controls.append(
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Icon(
                                ft.Icons.CLOUD_OFF_ROUNDED,
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
                                "Tap 'New Session' to create a cloud runtime",
                                size=tokens.FONT_XS,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=tokens.SPACE_SM,
                    ),
                    padding=ft.Padding(
                        tokens.SPACE_XL,
                        tokens.SPACE_XXL,
                        tokens.SPACE_XL,
                        tokens.SPACE_XXL,
                    ),
                    alignment=ft.Alignment.CENTER,
                )
            )
        for s in state.active_sessions:
            sessions_list.content.controls.append(
                build_session_card(
                    session=s,
                    on_click=lambda e, sn=s["name"]: (
                        on_session_tap(sn) if on_session_tap else None
                    ),
                )
            )
        await asyncio.sleep(0)
        page.update()

    async def _load_sessions():
        await asyncio.sleep(0.1)  # Let the view mount on mobile
        try:
            state.is_loading = True
            await _update_sessions_ui()
            sessions = await colab_service.list_sessions(auth_method=state.auth_method)
            state.active_sessions = sessions
            state.is_loading = False

            # Clean up notebook cache for deleted sessions (the method
            # short-circuits safely when the list is empty).
            if storage:
                active_names = [s["name"] for s in state.active_sessions]
                page.run_task(storage.cleanup_orphaned_notebooks, active_names)

            await _update_sessions_ui()
        except Exception:
            state.is_loading = False
            await _update_sessions_ui()

    sessions_section_header = ft.Container(
        content=ft.Row(
            controls=[
                ft.Text(
                    "ACTIVE SESSIONS",
                    size=tokens.FONT_SM,
                    weight=ft.FontWeight.W_700,
                    color=ft.Colors.PRIMARY,
                    style=ft.TextStyle(letter_spacing=1),
                ),
                ft.IconButton(
                    icon=ft.Icons.REFRESH_ROUNDED,
                    icon_size=tokens.ICON_SM,
                    tooltip="Refresh active sessions",
                    on_click=lambda e: page.run_task(_load_sessions),
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(
            left=tokens.SPACE_LG,
            right=tokens.SPACE_LG,
            top=tokens.SPACE_MD,
            bottom=tokens.SPACE_XS,
        ),
    )

    page.run_task(_load_sessions)

    # ── Full view ─────────────────────────────────────────────────────────────
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

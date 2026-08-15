"""Session selector tab for Notebooks, Terminals, and Cloud Files."""

from __future__ import annotations

import flet as ft

from components.session_card import build_session_card
from core import constants, tokens
from core.styles import build_banner_ad, section_header
from state import AppStateCtx, ControllerMethodsCtx


@ft.component
def SessionSelectorTab(mode: str) -> ft.Control:
    """Tab screen allowing user to pick an active session or create a new one.

    mode: "notebook" | "terminal" | "files"
    """
    state = ft.use_context(AppStateCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    page = ft.context.page

    def _on_select(session_name: str):
        controller.open_session(session_name, mode)

    def _on_new(e):
        controller.show_new_session_sheet(mode)

    # Top action: New Session
    new_session_btn = ft.Container(
        content=ft.ListTile(
            leading=ft.Icon(ft.Icons.ADD_ROUNDED, color=ft.Colors.ON_SURFACE),
            title=ft.Text(
                constants.LBL_NEW_SESSION,
                color=ft.Colors.ON_SURFACE,
                weight=ft.FontWeight.W_600,
            ),
        ),
        on_click=_on_new,
        margin=ft.Margin(tokens.SPACE_LG, tokens.SPACE_MD, tokens.SPACE_LG, 0),
        ink=True,
    )

    controls = []
    if not state.active_sessions:
        controls.append(
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
                            "Create a new session to get started.",
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
    else:
        for s in state.active_sessions:
            name = s.get("name", "Unknown")
            controls.append(
                build_session_card(
                    session=s,
                    on_click=lambda e, n=name: _on_select(n),
                )
            )

    return ft.Column(
        controls=[
            new_session_btn,
            build_banner_ad(page),
            section_header(constants.LBL_ACTIVE_SESSIONS.upper()),
            ft.Column(controls=controls, spacing=0),
        ],
        spacing=0,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

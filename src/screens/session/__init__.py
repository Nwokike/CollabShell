"""SessionScreen — Notebook and Terminal tabs for a running Colab session."""

from __future__ import annotations

import flet as ft

from core import tokens
from screens.session.layout import build_status_header
from screens.session.notebook_view import NotebookView
from screens.session.terminal_panel import build_terminal_panel
from state import AppStateCtx, ControllerMethodsCtx, ServiceCtx


@ft.component
def SessionScreen(session_name: str, mode: str, on_back) -> ft.Control:
    """Top-level session screen with Notebook/Terminal tab switching."""
    state = ft.use_context(AppStateCtx)
    services = ft.use_context(ServiceCtx)
    controller = ft.use_context(ControllerMethodsCtx)
    page = ft.context.page

    active_tab, set_tab = ft.use_state(0 if mode == "notebook" else 1)
    terminal_ready, set_terminal_ready = ft.use_state(mode == "terminal")
    terminal_init_ref = ft.use_ref(None)

    def _switch_to_terminal():
        if not terminal_ready:
            set_terminal_ready(True)
        set_tab(1)

    ft.use_effect(
        lambda: (
            page.run_task(terminal_init_ref.current)
            if terminal_ready and terminal_init_ref.current
            else None
        ),
        [terminal_ready],
    )

    # ── Terminal panel (built once on first access) ───────────────────────────
    if terminal_ready:
        terminal_panel, terminal_init_func = build_terminal_panel(
            page,
            session_name,
            services.colab,
            snack=controller.show_snack,
        )
        terminal_init_ref.current = terminal_init_func
    else:
        terminal_panel = ft.Container()

    # ── Status header ─────────────────────────────────────────────────────────
    status_header = build_status_header(
        page=page,
        session_name=session_name,
        state=state,
        colab_service=services.colab,
    )

    # ── Tab bar ───────────────────────────────────────────────────────────────
    def _on_tab_change(e):
        idx = int(e.data) if e and e.data else 0
        if idx == 1 and not terminal_ready:
            set_terminal_ready(True)
        set_tab(idx)

    tab_bar = ft.Tabs(
        selected_index=active_tab,
        on_change=_on_tab_change,
        expand=False,
        tabs=[
            ft.Tab(
                text="Notebook",
                icon=ft.Icons.EDIT_NOTE_ROUNDED,
            ),
            ft.Tab(
                text="Terminal",
                icon=ft.Icons.TERMINAL_ROUNDED,
            ),
        ],
    )

    # ── Content area ──────────────────────────────────────────────────────────
    content = ft.Stack(
        controls=[
            ft.Container(
                content=NotebookView(
                    session_name=session_name,
                    initial_mode=mode,
                    on_switch_terminal=_switch_to_terminal,
                ),
                expand=True,
                visible=active_tab == 0,
            ),
            ft.Container(
                content=terminal_panel,
                expand=True,
                visible=active_tab == 1,
            ),
        ],
        expand=True,
    )

    header_bar = ft.Container(
        content=ft.Row(
            controls=[
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK_ROUNDED,
                    on_click=lambda e: on_back(),
                    icon_size=tokens.ICON_MD,
                    tooltip="Back to Home",
                ),
                ft.Text(
                    "Active Session",
                    size=tokens.FONT_LG,
                    weight=ft.FontWeight.W_700,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=tokens.SPACE_SM,
        ),
        padding=ft.Padding(
            tokens.SPACE_SM, tokens.SPACE_SM, tokens.SPACE_LG, tokens.SPACE_SM
        ),
        bgcolor=ft.Colors.SURFACE,
    )

    return ft.Column(
        controls=[
            header_bar,
            status_header,
            tab_bar,
            content,
        ],
        spacing=0,
        expand=True,
    )


__all__ = ["NotebookView", "SessionScreen"]

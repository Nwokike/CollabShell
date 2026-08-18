"""SessionScreen — Notebook and Terminal tabs for a running Colab session."""

from __future__ import annotations

import flet as ft

from core import tokens
from screens.session.layout import build_status_header
from screens.session.notebook_view import NotebookView
from screens.session.terminal_panel import TerminalPanel, TerminalPanelState
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
    # Stable panel state survives re-renders; the TerminalPanel component
    # subscribes to it and manages its own WebSocket lifecycle.
    terminal_ps_ref = ft.use_ref(lambda: TerminalPanelState())

    def _switch_to_terminal():
        if not terminal_ready:
            set_terminal_ready(True)
        set_tab(1)

    # ── Terminal panel (mounted lazily on first access) ───────────────────────
    if terminal_ready:
        terminal_panel = TerminalPanel(
            terminal_ps_ref.current,
            session_name,
            services.colab,
            snack=controller.show_snack,
        )
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
        selected = e.control.selected if e and e.control else [str(active_tab)]
        val = selected[0] if selected else "0"
        idx = int(val) if val.isdigit() else 0
        if idx == 1 and not terminal_ready:
            set_terminal_ready(True)
        set_tab(idx)

    tab_bar = ft.SegmentedButton(
        selected=[str(active_tab)],
        allow_empty_selection=False,
        on_change=_on_tab_change,
        segments=[
            ft.Segment(
                value="0",
                label=ft.Text("Notebook"),
                icon=ft.Icon(ft.Icons.EDIT_NOTE_ROUNDED),
            ),
            ft.Segment(
                value="1",
                label=ft.Text("Terminal"),
                icon=ft.Icon(ft.Icons.TERMINAL_ROUNDED),
            ),
        ],
    )

    # ── Content area ──────────────────────────────────────────────────────────
    content = ft.Stack(
        controls=[
            ft.Container(
                content=NotebookView(
                    session_name=session_name,
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

    theme_icon = (
        ft.Icons.BRIGHTNESS_AUTO_ROUNDED
        if state.theme_mode == ft.ThemeMode.SYSTEM
        else ft.Icons.LIGHT_MODE_ROUNDED
        if state.theme_mode == ft.ThemeMode.LIGHT
        else ft.Icons.DARK_MODE_ROUNDED
    )
    theme_tooltip = (
        "System Theme"
        if state.theme_mode == ft.ThemeMode.SYSTEM
        else "Light Theme"
        if state.theme_mode == ft.ThemeMode.LIGHT
        else "Dark Theme"
    )
    theme_btn = ft.IconButton(
        icon=theme_icon,
        icon_size=tokens.ICON_SM,
        tooltip=theme_tooltip,
        on_click=lambda e: controller.toggle_theme(),
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
                ft.Container(expand=True),
                theme_btn,
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

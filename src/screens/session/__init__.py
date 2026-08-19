"""SessionScreen — Notebook and Terminal tabs for a running Colab session."""

from __future__ import annotations

import flet as ft

from core import tokens
from screens.files.modal import show_manage_files_modal
from screens.session.fab_menu import build_session_fab
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

    # ── FAB (overflow menu reachable from both Notebook and Terminal tabs) ──
    # NotebookView registers its action handlers into this ref and reports its
    # cell count via set_cells_version so the FAB menu stays in sync.
    cells_version, set_cells_version = ft.use_state(0)
    nb_actions_ref = ft.use_ref(dict)

    def _sync_fab():
        if not page or not page.views:
            return
        actions = nb_actions_ref.current

        def _call(name: str):
            fn = actions.get(name)
            if fn:
                fn()

        fab = build_session_fab(
            has_session=bool(session_name),
            has_cells=cells_version > 0,
            on_export_ipynb=lambda e: _call("export_ipynb"),
            on_import_ipynb=lambda e: _call("import_ipynb"),
            on_clear_all=lambda e: _call("clear_all"),
            on_manage_files=lambda e: show_manage_files_modal(
                page,
                services.colab,
                session_name,
                auth_method=state.auth_method,
                ad_service=services.ad_service,
                state=state,
            ),
        )
        try:
            page.views[0].floating_action_button = fab
            page.update()
        except Exception:
            pass

    def _cleanup_fab():
        if page and page.views:
            try:
                page.views[0].floating_action_button = None
                page.update()
            except Exception:
                pass

    ft.use_effect(_sync_fab, [session_name, cells_version], cleanup=_cleanup_fab)

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
                    register_actions=lambda actions: nb_actions_ref.current.update(
                        actions
                    ),
                    on_cells_change=set_cells_version,
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

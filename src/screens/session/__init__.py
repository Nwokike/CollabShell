"""SessionScreen — Notebook and Terminal tabs for a running Colab session."""

from __future__ import annotations

import logging

import flet as ft

from core import tokens
from core.shortcuts import SUPPRESS, shortcuts_router
from core.styles import hardware_badge, status_dot
from screens.files.modal import show_manage_files_modal
from screens.session.fab_menu import build_session_fab
from screens.session.layout import build_tab_switcher
from screens.session.notebook_view import NotebookView
from screens.session.terminal_panel import TerminalPanel, TerminalPanelState
from screens.session.vm_ops import on_auth_gcp, on_mount_drive
from state import AppStateCtx, ControllerMethodsCtx, ServiceCtx

logger = logging.getLogger(__name__)


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

    # ── Keyboard shortcut context ────────────────────────────────────────────
    # While the Terminal tab is active the page-level handler must ignore ALL
    # keys: terminal combos are owned by flet_terminal's Dart interceptor
    # (zero PTY leakage) and any global binding (e.g. Ctrl+1..5) would leak
    # its control bytes into the shell. The refs are refreshed every render
    # so the once-registered provider always reads current values.
    session_kb_ref = ft.use_ref(lambda: {"tab": 0, "nb_bindings": []})
    session_kb_ref.current["tab"] = active_tab

    def _session_bindings():
        if session_kb_ref.current["tab"] == 1:
            return SUPPRESS
        return session_kb_ref.current["nb_bindings"]

    def _register_session_shortcuts():
        return shortcuts_router.register(_session_bindings)

    ft.on_mounted(_register_session_shortcuts)

    # ── Shared session actions (used by the FAB on both tabs) ────────────────
    async def _do_restart():
        controller.show_snack("Restarting kernel...")
        try:
            await services.colab.restart_kernel(
                session_name, auth_method=state.auth_method
            )
            controller.show_snack("✅ Kernel restarted")
        except Exception as ex:
            controller.show_snack(f"❌ {ex}", is_error=True)

    def _on_restart(e=None):
        def _close(ev=None):
            page.pop_dialog()

        def _confirm(ev):
            page.pop_dialog()
            page.run_task(_do_restart)

        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Restart Kernel?"),
                content=ft.Text(
                    "This will restart the Python kernel. All variables will be lost."
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=_close),
                    ft.FilledButton("Restart", on_click=_confirm),
                ],
            )
        )

    async def _do_stop():
        controller.show_snack("Stopping session...")
        try:
            await services.colab.stop_session(
                session_name, auth_method=state.auth_method
            )
            controller.show_snack("✅ Session terminated")
            try:
                state.active_sessions = (
                    await services.colab.list_sessions(auth_method=state.auth_method)
                    or []
                )
            except Exception:
                logger.exception("Suppressed exception")
            controller.close_session()
        except Exception as ex:
            controller.show_snack(f"❌ {ex}", is_error=True)

    def _on_stop(e=None):
        def _close(ev=None):
            page.pop_dialog()

        def _confirm(ev):
            page.pop_dialog()
            page.run_task(_do_stop)

        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Stop Session?"),
                content=ft.Text(
                    "This will terminate the session and release all resources."
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=_close),
                    ft.FilledButton("Stop", on_click=_confirm),
                ],
            )
        )

    # ── FAB (context-aware overflow menu for both tabs) ───────────────────────
    # NotebookView and TerminalPanel register their action handlers into these
    # refs; the FAB rebuilds when the tab or cell count changes.
    cells_version, set_cells_version = ft.use_state(0)
    nb_actions_ref = ft.use_ref(dict)
    term_actions_ref = ft.use_ref(dict)

    def _sync_fab():
        if not page or not page.views:
            return
        nb_actions = nb_actions_ref.current
        term_actions = term_actions_ref.current

        def _call(registry: dict, name: str, *args):
            fn = registry.get(name)
            if fn:
                fn(*args)

        ts = terminal_ps_ref.current
        fab = build_session_fab(
            mode="terminal" if active_tab == 1 else "notebook",
            has_session=bool(session_name),
            has_cells=cells_version > 0,
            # Notebook
            on_export_ipynb=lambda e: _call(nb_actions, "export_ipynb"),
            on_import_ipynb=lambda e: _call(nb_actions, "import_ipynb"),
            on_clear_all=lambda e: _call(nb_actions, "clear_all"),
            # Shared
            on_manage_files=lambda e: show_manage_files_modal(
                page,
                services.colab,
                session_name,
                auth_method=state.auth_method,
                ad_service=services.ad_service,
                state=state,
            ),
            on_mount_drive=lambda e: page.run_task(
                on_mount_drive,
                page=page,
                session_name=session_name,
                colab_service=services.colab,
                state=state,
                snack=controller.show_snack,
            ),
            on_auth_gcp=lambda e: page.run_task(
                on_auth_gcp,
                page=page,
                session_name=session_name,
                colab_service=services.colab,
                state=state,
                snack=controller.show_snack,
            ),
            on_open_browser=lambda e: page.run_task(
                ft.UrlLauncher().launch_url,
                f"https://colab.research.google.com/drive/{session_name}",
            ),
            on_view_logs=lambda e: controller.open_history(session_name),
            on_restart=_on_restart,
            on_stop=_on_stop,
            # Terminal
            on_new_terminal=lambda e: _call(term_actions, "new_terminal"),
            on_clear_terminal=lambda e: _call(term_actions, "clear_terminal"),
            on_copy=lambda e: _call(term_actions, "copy"),
            on_paste=lambda e: _call(term_actions, "paste"),
            # Terminal settings (FAB inherits the flet_terminal settings menu)
            term_settings={
                "theme": ts.theme,
                "blink": ts.blink,
                "search": ts.search,
                "zoom": ts.zoom,
            },
            on_term_theme=lambda name: _call(term_actions, "theme", name),
            on_term_zoom_in=lambda e=None: _call(term_actions, "zoom_in"),
            on_term_zoom_out=lambda e=None: _call(term_actions, "zoom_out"),
            on_term_zoom_reset=lambda e=None: _call(term_actions, "zoom_reset"),
            on_term_toggle_blink=lambda e=None: _call(term_actions, "toggle_blink"),
            on_term_toggle_search=lambda e=None: _call(term_actions, "toggle_search"),
        )
        try:
            page.views[0].floating_action_button = fab
            page.update()
        except Exception:
            logger.exception("Suppressed exception")

    def _cleanup_fab():
        if page and page.views:
            try:
                page.views[0].floating_action_button = None
                page.update()
            except Exception:
                logger.exception("Suppressed exception")

    ft.use_effect(
        _sync_fab,
        [session_name, cells_version, active_tab, state.terminal_settings_rev],
        cleanup=_cleanup_fab,
    )

    def _switch_to_terminal():
        if not terminal_ready:
            set_terminal_ready(True)
        set_tab(1)

    def _switch_tab(idx: int):
        if idx == 1 and not terminal_ready:
            set_terminal_ready(True)
        set_tab(idx)

    # ── Terminal panel (mounted lazily on first access) ───────────────────────
    if terminal_ready:
        terminal_panel = TerminalPanel(
            terminal_ps_ref.current,
            session_name,
            services.colab,
            snack=controller.show_snack,
            register_actions=lambda actions: term_actions_ref.current.update(actions),
        )
    else:
        terminal_panel = ft.Container()

    # ── Session info (merged into the header, SpanInsight-style) ─────────────
    _session = next(
        (
            s
            for s in getattr(state, "active_sessions", [])
            if s.get("name") == session_name
        ),
        None,
    )
    _accel = (_session or {}).get("accelerator", "NONE")
    _variant = (_session or {}).get("variant", "DEFAULT")
    _is_running = (_session or {}).get("running") is not None
    _status_text = (_session or {}).get("status", "IDLE")

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
                    register_bindings=lambda bindings: (
                        session_kb_ref.current.__setitem__("nb_bindings", bindings)
                    ),
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
                ft.Container(
                    content=status_dot(_is_running),
                    tooltip=f"Session {_status_text}",
                ),
                ft.Text(
                    session_name or "Active Session",
                    size=tokens.FONT_LG,
                    weight=ft.FontWeight.W_700,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    expand=True,
                    tooltip=session_name,
                ),
                hardware_badge(_accel, _variant),
                build_tab_switcher(active_tab, _switch_tab),
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
            content,
        ],
        spacing=0,
        expand=True,
    )


__all__ = ["NotebookView", "SessionScreen"]

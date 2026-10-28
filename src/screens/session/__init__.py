"""SessionScreen — Notebook and Terminal tabs for a running Colab session."""

from __future__ import annotations

import logging

import flet as ft

from components.shortcuts_help import build_help_button
from core import tokens
from core.shortcuts import SUPPRESS, shortcuts_router
from core.styles import hardware_badge, shape_chip, status_dot
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
    runtime_status, set_runtime_status = ft.use_state("checking")
    # Stable panel state survives re-renders; the TerminalPanel component
    # subscribes to it and manages its own WebSocket lifecycle.
    terminal_ps_ref = ft.use_ref(lambda: TerminalPanelState())

    async def _verify_runtime():
        from services.colab.session_ops import SessionListError

        try:
            sessions = await services.colab.list_sessions(auth_method=state.auth_method)
        except SessionListError:
            set_runtime_status("unknown")
        except Exception:
            logger.exception("Could not verify runtime assignment")
            set_runtime_status("unknown")
        else:
            state.active_sessions = sessions or []
            if any(session.get("name") == session_name for session in sessions or []):
                set_runtime_status("active")
            else:
                set_runtime_status("ended")

    ft.use_effect(
        lambda: page.run_task(_verify_runtime),
        [session_name],
    )

    # ── Session ended modal ──────────────────────────────────────────────────
    # When the runtime is authoritatively confirmed as ended (not just unknown),
    # show a modal that forces the user back to Home. This replaces the passive
    # banner-only behavior.
    ended_modal_shown, set_ended_modal_shown = ft.use_state(False)

    def _show_ended_modal():
        if runtime_status == "ended" and not ended_modal_shown:
            set_ended_modal_shown(True)
            page.show_dialog(
                ft.AlertDialog(
                    title=ft.Text("Session Not Found"),
                    content=ft.Text(
                        "This Colab runtime no longer exists on the server. "
                        "Its kernel and remote files are unavailable. "
                        "Local notebook and script drafts are preserved on this screen."
                    ),
                    actions=[
                        ft.FilledButton(
                            "Return to Home",
                            on_click=lambda e: (page.pop_dialog(), on_back()),
                        ),
                    ],
                    actions_alignment=ft.MainAxisAlignment.END,
                    modal=True,
                )
            )

        ft.use_effect(_show_ended_modal, [runtime_status, ended_modal_shown])

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
    # Per-session env override store: plain memory-only dict shared between
    # the header env icon (opens the dialog) and the notebook view (reads it
    # at exec time). Rebuilt only when the session screen rebuilds; the dialog
    # mutates it in place so both sides always see the same object.
    session_env_override: dict = {}

    def _open_env_dialog(e=None):
        from components.env_dialog import show_env_override_dialog

        show_env_override_dialog(
            page, state, session_env_override, on_save=lambda _env: None
        )

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
            on_rename_notebook=lambda e: _call(nb_actions, "rename_notebook"),
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
            # AI. Each panel registers its own handler, and each is always
            # offered: a menu entry that only opens a "turn it on" notice is
            # worse than no entry.
            on_ai_explain=lambda e: _call(term_actions, "explain"),
            on_ai_explain_cell=lambda e: _call(nb_actions, "ask_ai_active"),
            on_ai_suggest_hardware=lambda e: _call(nb_actions, "suggest_hardware"),
            on_open_assistant=lambda e: controller.open_assistant(),
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

    def _focus_terminal_tab():
        # Desktop only: returning to the Terminal tab restores keyboard focus
        # so Dart-intercepted shortcuts keep working without re-clicking the
        # canvas. Mobile skips this — requestFocus pops the soft keyboard.
        if active_tab != 1:
            return
        try:
            if page.platform.is_mobile():
                return
        except Exception:
            return
        ts = terminal_ps_ref.current
        entry = next((t for t in ts.terminals if t.id == ts.active_id), None)
        if entry is not None and entry.mt is not None:
            try:
                entry.mt.focus()
            except RuntimeError:
                pass
        return

    ft.use_effect(_focus_terminal_tab, [active_tab])

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
    _shape = (_session or {}).get("machine_shape", "STANDARD")
    _is_running = (_session or {}).get("running") is not None
    _status_text = (_session or {}).get("status", "IDLE")
    # Env indicator reflects persisted defaults (the override dialog pre-fills
    # from these). Per-session memory-only overrides live in the notebook view
    # and are shown there; the header stays truthful about stored config.
    _env_count = len(getattr(state, "default_env", {}) or {}) + len(
        session_env_override
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
                    register_bindings=lambda bindings: (
                        session_kb_ref.current.__setitem__("nb_bindings", bindings)
                    ),
                    session_env_override=session_env_override,
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

    is_offline = not state.is_online
    runtime_message = (
        "Offline. Remote actions are unavailable; local edits remain on this screen."
        if is_offline
        else "Colab no longer lists this runtime. Its kernel and remote files are "
        "unavailable; local notebook and script drafts remain on this screen."
        if runtime_status == "ended"
        else "Could not verify this runtime. Its status is unknown; this does not "
        "confirm that it ended."
    )
    runtime_banner = ft.Container(
        content=ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.CLOUD_OFF_ROUNDED,
                    color=ft.Colors.ON_ERROR_CONTAINER,
                    size=tokens.ICON_SM,
                ),
                ft.Text(
                    runtime_message,
                    color=ft.Colors.ON_ERROR_CONTAINER,
                    size=tokens.FONT_XS,
                    expand=True,
                ),
                ft.TextButton("Back to Home", on_click=lambda e: on_back()),
            ],
            spacing=tokens.SPACE_SM,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=ft.Colors.ERROR_CONTAINER,
        padding=ft.Padding(
            tokens.SPACE_MD, tokens.SPACE_XS, tokens.SPACE_MD, tokens.SPACE_XS
        ),
        visible=is_offline or runtime_status in ("ended", "unknown"),
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
                # Badge rail scrolls horizontally on narrow screens (visible
                # scrollbar, Sherlock/LM-Router pattern) so the hardware/shape
                # chips, tab switcher, help, and theme controls are never
                # silently clipped the way HIDDEN-scroll did on laptops.
                ft.Row(
                    controls=[
                        hardware_badge(_accel, _variant),
                        shape_chip(_shape),
                        *(
                            [
                                ft.IconButton(
                                    icon=ft.Icons.TUNE_ROUNDED,
                                    icon_size=tokens.ICON_SM,
                                    tooltip=(
                                        f"Environment variables ({_env_count} set) — "
                                        "tap to manage"
                                    ),
                                    on_click=_open_env_dialog,
                                )
                            ]
                            if _env_count
                            else []
                        ),
                        build_tab_switcher(active_tab, _switch_tab),
                        build_help_button(
                            page,
                            lambda: (
                                "terminal"
                                if session_kb_ref.current["tab"] == 1
                                else "notebook"
                            ),
                        ),
                        theme_btn,
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=tokens.SPACE_SM,
                    scroll=ft.ScrollMode.AUTO,
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
            runtime_banner,
            content,
        ],
        spacing=0,
        expand=True,
    )


__all__ = ["NotebookView", "SessionScreen"]

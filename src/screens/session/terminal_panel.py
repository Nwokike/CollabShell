"""Native Colab Terminal panel — declarative component using flet_terminal.

Panel state (tabs, active tab, status) is an @ft.observable
model; the `TerminalPanel` component re-renders reactively on every change.
WebSocket clients live in the panel state and are closed on unmount.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable

import flet as ft
from flet_terminal import BUILTIN_THEMES, MobileTerminal

from core import tokens
from core.state import state as app_state
from core.theme import AppColors, is_light_theme

logger = logging.getLogger("colab")


def _active_theme_name(page: ft.Page | None = None) -> str:
    """Terminal theme that follows the app's light/dark mode."""
    return "Colab Light" if is_light_theme(page) else "JetBrains Dark"


def _is_mounted(control) -> bool:
    """Safely check if control is attached to the page without raising RuntimeError."""
    if control is None:
        return False
    return getattr(control, "_page", None) is not None


async def _get_terminal_session(colab_service, session_name: str):
    """Retrieve endpoint, url, and token for session_name from Colab's store."""
    try:

        def _get():
            from colab_cli.common import State

            st = State()
            s = st.store.get(session_name)
            if not s:
                all_names = list(st.store.list().keys())
                logger.error(
                    "Session '%s' not found. Available: %s",
                    session_name,
                    all_names or "(none)",
                )
                return None
            return {
                "name": s.name,
                "url": s.url,
                "endpoint": s.endpoint,
                "token": s.token,
            }

        return await asyncio.to_thread(_get)
    except Exception as e:
        logger.error("Failed to get session data: %s", e)
        return None


@ft.observable
class TerminalEntry:
    """One terminal tab: its widget, WebSocket client, and readiness."""

    def __init__(self, tid: int, mt: MobileTerminal):
        self.id = tid
        self.mt = mt
        self.client = None
        self.pending_stdout: list = []
        self.ready = False


@ft.observable
class TerminalPanelState:
    """Observable state driving the whole panel UI."""

    def __init__(self):
        self.terminals: list = []
        self.active_id = 1
        self.next_id = 1
        self.status = "Ready"
        self.status_ok = False
        self.connecting = False
        # Active terminal settings (drive the FAB menu; session/session_sync
        # bumps terminal_settings_rev after a change so checkmarks refresh).
        self.theme = "JetBrains Dark"
        self.blink = True
        self.search = False
        self.zoom = 11.0


@ft.component
def TerminalPanel(
    ps: TerminalPanelState,
    session_name: str,
    colab_service,
    snack: Callable[[str], None] | None = None,
    register_actions: Callable[[dict], None] | None = None,
) -> ft.Control:
    """Multi-terminal panel with tab management, theming, and WS lifecycle.

    `ps` is passed as an observable argument so Flet auto-subscribes this
    component to it — any mutation re-renders the panel. The terminal color
    theme follows the app's light/dark mode.
    """
    page = ft.context.page

    def _active_entry():
        return next((t for t in ps.terminals if t.id == ps.active_id), None)

    # ── Terminal lifecycle ────────────────────────────────────────────────────
    async def _create_terminal():
        new_id = ps.next_id
        ps.next_id = new_id + 1
        ps.active_id = new_id

        session_info = await _get_terminal_session(colab_service, session_name)
        if not session_info:
            ps.status = "Session not found."
            ps.status_ok = False
            if snack:
                snack("Session not found in store.")
            return

        theme_name = _active_theme_name(page)
        mt = MobileTerminal(
            show_search=False,
            show_settings=False,
            scrollback=10000,
            font_family="JetBrains Mono",
            font_size=11.0,
            theme=BUILTIN_THEMES.get(theme_name),
            auto_focus=False,
            expand=True,
        )

        entry = TerminalEntry(new_id, mt)
        # New terminals inherit the panel's current settings.
        if not ps.blink:
            mt.toggle_cursor_blink()
        while mt.font_size < ps.zoom:
            mt.zoom_in()

        def _safe_run_task(task_fn, *args):
            try:
                if getattr(page, "_session", getattr(page, "session", None)):
                    page.run_task(task_fn, *args)
            except RuntimeError:
                pass

        def _write_to_terminal(text: str):
            if (
                getattr(mt._terminal, "_channel", None) is not None
                and getattr(mt._terminal, "_channel_ready", False)
                and getattr(mt._terminal, "_dart_ready", False)
            ):
                mt.send_bytes(text.encode("utf-8", errors="ignore"))
            else:
                mt.write(text)

        def _on_stdout(text: str):
            if entry.ready and _is_mounted(mt):
                try:
                    _write_to_terminal(text)
                    return
                except Exception as ex:
                    logger.debug("Buffering stdout: %s", ex)
            entry.pending_stdout.append(text)

        def _on_status(msg: str, ok: bool):
            if ps.active_id == entry.id:
                ps.status = msg
                ps.status_ok = ok
                ps.connecting = not ok

        def _on_bytes(payload: bytes | str):
            if entry.client:
                data = (
                    payload
                    if isinstance(payload, bytes)
                    else payload.encode("utf-8", errors="ignore")
                )
                _safe_run_task(entry.client.send_input, data)

        def _on_resize(ev):
            if entry.client and ev.data:
                try:
                    info = json.loads(ev.data)
                    _safe_run_task(
                        entry.client.set_size,
                        info.get("rows", 24),
                        info.get("cols", 80),
                    )
                except Exception as ex:
                    logger.debug("Error handling terminal resize: %s", ex)

        # Wire every handler BEFORE the widget enters the observable tree.
        # Appending to ps.terminals triggers a component re-render that freezes
        # the rendered subtree; declared props (on_data/on_resize) can only be
        # assigned while the control is still unfrozen.
        mt.set_on_bytes(_on_bytes)
        mt.on_data = lambda e: _on_bytes(
            e.data if isinstance(e.data, str) else str(e.data)
        )
        mt.on_resize = _on_resize

        ps.terminals.append(entry)
        ps.status = f"Connecting Terminal {new_id}…"
        ps.status_ok = False
        ps.connecting = True

        # Wait for the widget to mount before opening the WebSocket
        for _ in range(40):
            if _is_mounted(mt):
                break
            await asyncio.sleep(0.05)

        try:
            ws_url = await asyncio.to_thread(
                colab_service.create_terminal_ws_url,
                session_info["url"],
                session_info["token"],
            )

            client = colab_service.get_terminal_client(ws_url, _on_stdout, _on_status)
            entry.client = client

            await client.connect()
            entry.ready = True

            if entry.pending_stdout and _is_mounted(mt):
                for chunk in entry.pending_stdout:
                    try:
                        _write_to_terminal(chunk)
                    except Exception:
                        pass
                entry.pending_stdout.clear()

            if entry.client:
                # Colab PTYs open in /root; move to the shared data dir.
                _safe_run_task(entry.client.send_input, "cd /content\r\n")

        except Exception as ex:
            logger.error("Terminal %s init failed: %s", new_id, ex)
            if ps.active_id == new_id:
                ps.status = f"Error: {ex}"
                ps.status_ok = False
                ps.connecting = False
            if snack:
                snack(f"Terminal {new_id} error: {ex}")

    def _close_terminal(tid: int):
        idx = next((i for i, t in enumerate(ps.terminals) if t.id == tid), -1)
        if idx == -1:
            return
        entry = ps.terminals.pop(idx)
        if entry.client:
            try:
                entry.client.close()
            except Exception:
                pass

        if not ps.terminals:
            page.run_task(_create_terminal)
            return

        if ps.active_id == tid:
            new_idx = max(0, idx - 1)
            ps.active_id = ps.terminals[new_idx].id

    def _close_all_clients():
        for t in ps.terminals:
            if t.client:
                try:
                    t.client.close()
                except Exception:
                    pass

    async def _init_panel():
        _close_all_clients()
        ps.terminals.clear()
        await _create_terminal()

    # ── Actions exposed to the SessionScreen FAB overflow menu ───────────────
    def _changed_settings():
        app_state.terminal_settings_rev += 1

    def _for_each_mt(fn):
        for t in ps.terminals:
            fn(t.mt)

    def _set_theme(name: str):
        ps.theme = name
        _for_each_mt(lambda mt: mt.set_theme(name))
        _changed_settings()

    def _zoom_in():
        _for_each_mt(lambda mt: mt.zoom_in())
        entry = _active_entry()
        if entry:
            ps.zoom = entry.mt.font_size
        _changed_settings()

    def _zoom_out():
        _for_each_mt(lambda mt: mt.zoom_out())
        entry = _active_entry()
        if entry:
            ps.zoom = entry.mt.font_size
        _changed_settings()

    def _zoom_reset():
        _for_each_mt(lambda mt: mt.reset_zoom())
        entry = _active_entry()
        if entry:
            ps.zoom = entry.mt.font_size
        _changed_settings()

    def _toggle_blink():
        _for_each_mt(lambda mt: mt.toggle_cursor_blink())
        ps.blink = not ps.blink
        _changed_settings()

    def _toggle_search():
        ps.search = not ps.search
        want = ps.search
        _for_each_mt(lambda mt: mt.toggle_search() if mt.show_search != want else None)
        _changed_settings()

    def _clear_terminal():
        entry = _active_entry()
        if entry and entry.client:
            # Ctrl+L: bash clears the screen and redraws the prompt at top.
            page.run_task(entry.client.send_input, b"\x0c")

    async def _copy_selection():
        entry = _active_entry()
        if not entry:
            return
        text = await entry.mt.get_selection_async()
        if not text:
            if snack:
                snack("Nothing selected — long-press or drag to select text.")
            return
        try:
            await ft.Clipboard().set(text)
            entry.mt.clear_selection()
            if snack:
                snack("📋 Copied to clipboard")
        except Exception as ex:
            if snack:
                snack(f"Copy failed: {ex}", is_error=True)

    if register_actions:
        register_actions(
            {
                "new_terminal": lambda: page.run_task(_create_terminal),
                "clear_terminal": _clear_terminal,
                "copy": lambda: page.run_task(_copy_selection),
                "paste": lambda: (
                    _active_entry().mt.paste() if _active_entry() else None
                ),
                # Settings (consumed by the FAB menu, with live checkmarks)
                "theme": _set_theme,
                "zoom_in": _zoom_in,
                "zoom_out": _zoom_out,
                "zoom_reset": _zoom_reset,
                "toggle_blink": _toggle_blink,
                "toggle_search": _toggle_search,
                "font_size": lambda: (
                    _active_entry().mt.font_size if _active_entry() else ps.zoom
                ),
            }
        )

    # Self-initialize on mount; close all sockets on unmount.
    ft.on_mounted(lambda: page.run_task(_init_panel))
    ft.use_effect(lambda: None, [], cleanup=_close_all_clients)

    # Follow the app's light/dark mode: re-apply the terminal theme whenever
    # the requested mode changes or the OS flips brightness in SYSTEM mode.
    def _apply_app_theme():
        name = _active_theme_name(page)
        for t in ps.terminals:
            t.mt.set_theme(name)
        ps.theme = name
        _changed_settings()

    ft.use_effect(_apply_app_theme, [app_state.theme_mode, app_state.theme_revision])

    # ── Render ────────────────────────────────────────────────────────────────
    status_bar = ft.Container(
        content=ft.Row(
            controls=[
                ft.ProgressRing(
                    width=14,
                    height=14,
                    stroke_width=2,
                    visible=ps.connecting,
                ),
                ft.Text(
                    ps.status,
                    size=tokens.FONT_XS,
                    color=(
                        AppColors.SUCCESS
                        if ps.status_ok
                        else ft.Colors.ON_SURFACE_VARIANT
                    ),
                    expand=True,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=tokens.SPACE_SM,
        ),
        padding=ft.Padding(
            tokens.SPACE_MD, tokens.SPACE_XS, tokens.SPACE_MD, tokens.SPACE_XS
        ),
        bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
    )

    tab_buttons = []
    for t in ps.terminals:
        is_active = t.id == ps.active_id
        tab_buttons.append(
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Icon(
                            ft.Icons.TERMINAL_ROUNDED,
                            size=tokens.ICON_XS,
                            color=ft.Colors.PRIMARY
                            if is_active
                            else ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.Text(
                            f"Term {t.id}",
                            size=tokens.FONT_XS,
                            color=ft.Colors.PRIMARY
                            if is_active
                            else ft.Colors.ON_SURFACE,
                            weight=ft.FontWeight.W_600
                            if is_active
                            else ft.FontWeight.NORMAL,
                        ),
                        ft.GestureDetector(
                            content=ft.Icon(
                                ft.Icons.CLOSE_ROUNDED,
                                size=tokens.ICON_XS,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                            on_tap=lambda e, x=t.id: _close_terminal(x),
                        ),
                    ],
                    spacing=tokens.SPACE_XXS,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding(
                    tokens.SPACE_SM, tokens.SPACE_XXS, tokens.SPACE_XS, tokens.SPACE_XXS
                ),
                border_radius=tokens.RADIUS_SM,
                bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY)
                if is_active
                else ft.Colors.TRANSPARENT,
                on_click=lambda e, x=t.id: setattr(ps, "active_id", x),
                ink=True,
            )
        )
    tab_buttons.append(
        ft.IconButton(
            icon=ft.Icons.ADD_ROUNDED,
            icon_size=tokens.ICON_SM,
            tooltip="New Terminal",
            on_click=lambda e: page.run_task(_create_terminal),
        )
    )

    # Inline zoom controls: tap repeatedly to zoom in/out without opening the
    # FAB (each tap is one step). Mirrors the flet_terminal example appbar.
    zoom_out_btn = ft.IconButton(
        icon=ft.Icons.ZOOM_OUT,
        icon_size=tokens.ICON_SM,
        tooltip="Zoom Out",
        on_click=lambda e: _zoom_out(),
    )
    zoom_in_btn = ft.IconButton(
        icon=ft.Icons.ZOOM_IN,
        icon_size=tokens.ICON_SM,
        tooltip="Zoom In",
        on_click=lambda e: _zoom_in(),
    )

    # Theme cycle button: each tap advances through the four presets and the
    # icon reflects the active theme (like the app's light/dark mode switch).
    _theme_cycle = ["Dracula", "JetBrains Dark", "Matrix Green", "Colab Light"]
    _theme_icons = {
        "Dracula": ft.Icons.DARK_MODE_ROUNDED,
        "JetBrains Dark": ft.Icons.CODE_ROUNDED,
        "Matrix Green": ft.Icons.GRID_ON_ROUNDED,
        "Colab Light": ft.Icons.LIGHT_MODE_ROUNDED,
    }

    def _cycle_theme():
        idx = _theme_cycle.index(ps.theme) if ps.theme in _theme_cycle else 0
        _set_theme(_theme_cycle[(idx + 1) % len(_theme_cycle)])

    theme_btn = ft.IconButton(
        icon=_theme_icons.get(ps.theme, ft.Icons.PALETTE_ROUNDED),
        icon_size=tokens.ICON_SM,
        tooltip=f"Theme: {ps.theme} (tap to cycle)",
        on_click=lambda e: _cycle_theme(),
    )
    search_btn = ft.IconButton(
        icon=ft.Icons.SEARCH_ROUNDED,
        icon_size=tokens.ICON_SM,
        tooltip="Toggle Search Bar",
        icon_color=ft.Colors.PRIMARY if ps.search else None,
        on_click=lambda e: _toggle_search(),
    )

    switcher_box = ft.Container(
        content=ft.Row(
            controls=[
                ft.Container(
                    content=ft.Row(
                        controls=tab_buttons,
                        spacing=tokens.SPACE_XS,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                    expand=True,
                ),
                search_btn,
                theme_btn,
                zoom_out_btn,
                zoom_in_btn,
            ],
            spacing=tokens.SPACE_XS,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(tokens.SPACE_SM, 0, tokens.SPACE_SM, 0),
        bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.ON_SURFACE),
    )

    # Stable MobileTerminal instances wrapped in declarative visibility boxes
    stack_children = [
        ft.Container(
            content=t.mt,
            visible=t.id == ps.active_id,
            expand=True,
            key=ft.ValueKey(f"term_{t.id}"),
        )
        for t in ps.terminals
    ]

    return ft.Column(
        controls=[
            status_bar,
            switcher_box,
            ft.Stack(controls=stack_children, expand=True),
        ],
        spacing=0,
        expand=True,
    )


__all__ = ["TerminalPanel"]

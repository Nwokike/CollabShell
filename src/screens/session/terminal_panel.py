"""Native Colab Terminal panel — declarative component using flet_terminal.

Panel state (tabs, active tab, fullscreen, status) is an @ft.observable
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
from core.theme import AppColors

logger = logging.getLogger("colab")


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
        self.is_fullscreen = False
        self.status = "Ready"
        self.status_ok = False
        self.connecting = False


@ft.component
def TerminalPanel(
    ps: TerminalPanelState,
    session_name: str,
    colab_service,
    snack: Callable[[str], None] | None = None,
) -> ft.Control:
    """Multi-terminal panel with tab management, fullscreen, and WS lifecycle.

    `ps` is passed as an observable argument so Flet auto-subscribes this
    component to it — any mutation re-renders the panel.
    """
    page = ft.context.page

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

        mt = MobileTerminal(
            show_search=False,
            show_settings=True,
            scrollback=10000,
            font_family="JetBrains Mono",
            font_size=11.0,
            theme=BUILTIN_THEMES.get("JetBrains Dark", None),
            auto_focus=False,
            expand=True,
        )

        entry = TerminalEntry(new_id, mt)
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

            client = colab_service.get_terminal_client(ws_url, _on_stdout, _on_status)
            entry.client = client

            def _safe_run_task(task_fn, *args):
                try:
                    if getattr(page, "_session", getattr(page, "session", None)):
                        page.run_task(task_fn, *args)
                except RuntimeError:
                    pass

            def _on_bytes(payload: bytes | str):
                if not ps.is_fullscreen and payload:
                    ps.is_fullscreen = True
                if entry.client:
                    data = (
                        payload
                        if isinstance(payload, bytes)
                        else payload.encode("utf-8", errors="ignore")
                    )
                    _safe_run_task(entry.client.send_input, data)

            mt.set_on_bytes(_on_bytes)
            mt.on_data = lambda e: _on_bytes(
                e.data if isinstance(e.data, str) else str(e.data)
            )

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

            mt.on_resize = _on_resize
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
                _safe_run_task(entry.client.send_input, "\r")

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
        ps.is_fullscreen = False
        _close_all_clients()
        ps.terminals.clear()
        await _create_terminal()

    # Self-initialize on mount; close all sockets on unmount.
    ft.on_mounted(lambda: page.run_task(_init_panel))
    ft.use_effect(lambda: None, [], cleanup=_close_all_clients)

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
                ft.IconButton(
                    icon=ft.Icons.FULLSCREEN_EXIT_ROUNDED
                    if ps.is_fullscreen
                    else ft.Icons.FULLSCREEN_ROUNDED,
                    icon_size=tokens.ICON_SM,
                    tooltip="Toggle Fullscreen",
                    on_click=lambda e: setattr(
                        ps, "is_fullscreen", not ps.is_fullscreen
                    ),
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

    switcher_box = ft.Container(
        content=ft.Row(
            controls=tab_buttons, spacing=tokens.SPACE_XS, scroll=ft.ScrollMode.AUTO
        ),
        padding=ft.Padding(tokens.SPACE_SM, 0, tokens.SPACE_SM, 0),
        bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.ON_SURFACE),
        visible=not ps.is_fullscreen,
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

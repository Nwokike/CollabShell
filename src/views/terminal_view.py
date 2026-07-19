"""Terminal view — real Colab PTY shell with persistent multi-terminal tabs.

Uses `flet_terminal.MobileTerminal` (powered by `xterm.dart` and `DataChannel`)
connected directly to remote Colab WebSockets, featuring a horizontal pill switcher
bar that avoids swipe conflicts and lets you open multiple persistent terminals
(`+ New Terminal`) without disconnecting active tabs in the background.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable, Optional

import flet as ft
from flet_terminal import MobileTerminal, BUILTIN_THEMES

from core import tokens
from core.theme import AppColors

logger = logging.getLogger(__name__)


def build_terminal_panel(
    page: ft.Page,
    session_name: str,
    colab_service,
    snack: Optional[Callable[[str], None]] = None,
) -> tuple[ft.Container, Callable[[], None]]:
    """Build native multi-tab terminal panel and return (container, init_task)."""
    _spinner_ref = ft.Ref[ft.ProgressRing]()
    _status_ref = ft.Ref[ft.Text]()
    _session_info = None

    _terminals: list[dict] = []
    _active_tab_id = 0

    _switcher_row = ft.Row(
        controls=[],
        spacing=tokens.SPACE_XS,
        scroll=ft.ScrollMode.AUTO,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    _switcher_container = ft.Container(
        content=_switcher_row,
        padding=ft.Padding(
            tokens.SPACE_MD, tokens.SPACE_XS, tokens.SPACE_MD, tokens.SPACE_XS
        ),
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
    )

    _terminal_stack = ft.Stack(
        controls=[],
        expand=True,
    )

    status = ft.Container(
        content=ft.Row(
            controls=[
                ft.ProgressRing(ref=_spinner_ref, width=16, height=16, stroke_width=2),
                ft.Text(
                    ref=_status_ref,
                    value="Loading session…",
                    size=tokens.FONT_SM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Container(expand=True),
            ],
            spacing=tokens.SPACE_MD,
        ),
        padding=ft.Padding(
            tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
        ),
    )

    def _refresh_switcher():
        controls = []
        for t in _terminals:
            tid = t["id"]
            is_active = tid == _active_tab_id

            tab_pill = ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Text(
                            f"Terminal {tid}",
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.BOLD
                            if is_active
                            else ft.FontWeight.NORMAL,
                            color=AppColors.PRIMARY
                            if is_active
                            else ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.CLOSE_ROUNDED,
                            icon_size=14,
                            style=ft.ButtonStyle(
                                padding=2,
                                visual_density=ft.VisualDensity.COMPACT,
                                color=AppColors.ERROR
                                if is_active
                                else ft.Colors.ON_SURFACE_VARIANT,
                            ),
                            tooltip="Close terminal",
                            on_click=lambda e, id_val=tid: _close_terminal(id_val),
                        ),
                    ],
                    spacing=2,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding(10, 4, 6, 4),
                border_radius=16,
                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST
                if is_active
                else ft.Colors.TRANSPARENT,
                border=ft.Border(
                    left=ft.BorderSide(
                        1, AppColors.PRIMARY if is_active else ft.Colors.OUTLINE_VARIANT
                    ),
                    top=ft.BorderSide(
                        1, AppColors.PRIMARY if is_active else ft.Colors.OUTLINE_VARIANT
                    ),
                    right=ft.BorderSide(
                        1, AppColors.PRIMARY if is_active else ft.Colors.OUTLINE_VARIANT
                    ),
                    bottom=ft.BorderSide(
                        1, AppColors.PRIMARY if is_active else ft.Colors.OUTLINE_VARIANT
                    ),
                ),
                ink=True,
                on_click=lambda e, id_val=tid: _select_terminal(id_val),
            )
            controls.append(tab_pill)

        controls.append(
            ft.IconButton(
                icon=ft.Icons.ADD_CIRCLE_OUTLINE_ROUNDED,
                tooltip="New Terminal Tab",
                icon_size=20,
                icon_color=AppColors.PRIMARY,
                on_click=lambda e: page.run_task(_create_and_connect_terminal),
            )
        )
        _switcher_row.controls = controls
        if page:
            page.update()

    def _select_terminal(tid: int):
        nonlocal _active_tab_id
        _active_tab_id = tid
        for t in _terminals:
            t["mt"].visible = t["id"] == _active_tab_id
        _refresh_switcher()

    def _close_terminal(tid: int):
        nonlocal _active_tab_id
        target = None
        for i, t in enumerate(_terminals):
            if t["id"] == tid:
                target = _terminals.pop(i)
                break

        if target:
            if target.get("client"):
                try:
                    target["client"].close()
                except Exception:
                    pass
            if target.get("mt") in _terminal_stack.controls:
                _terminal_stack.controls.remove(target["mt"])

        if not _terminals:
            page.run_task(_create_and_connect_terminal)
        elif _active_tab_id == tid:
            _select_terminal(_terminals[-1]["id"])
        else:
            _refresh_switcher()

    async def _create_and_connect_terminal(e=None):
        nonlocal _session_info, _active_tab_id
        if not _session_info:
            _session_info = await _get_terminal_session(colab_service, session_name)
            if not _session_info:
                if _status_ref.current:
                    _status_ref.current.value = "Session not found"
                    _status_ref.current.color = AppColors.ERROR
                if _spinner_ref.current:
                    _spinner_ref.current.visible = False
                if page:
                    page.update()
                if snack:
                    snack("Session not found — create one first")
                return

        new_id = max([t["id"] for t in _terminals], default=0) + 1
        _active_tab_id = new_id

        for t in _terminals:
            t["mt"].visible = False

        mt = MobileTerminal(
            show_extra_keys=True,
            show_search=True,
            show_settings=True,
            scrollback=10000,
            font_family="JetBrains Mono",
            font_size=13.0,
            theme=BUILTIN_THEMES.get("JetBrains Dark", None),
            expand=True,
            visible=True,
        )

        term_entry = {
            "id": new_id,
            "mt": mt,
            "client": None,
            "pending_stdout": [],
            "ready": False,
        }
        _terminals.append(term_entry)
        _terminal_stack.controls.append(mt)
        _refresh_switcher()

        if _status_ref.current:
            _status_ref.current.value = f"Connecting Terminal {new_id}…"
            _status_ref.current.color = ft.Colors.ON_SURFACE_VARIANT
        if _spinner_ref.current:
            _spinner_ref.current.visible = True
        if page:
            page.update()

        # Wait until Flet assigns a UID to mt so mt.write() won't throw error 201
        for _ in range(40):
            if mt.page and getattr(mt, "uid", None):
                break
            await asyncio.sleep(0.05)

        try:
            colab_ws_url = await asyncio.to_thread(
                colab_service.create_terminal_ws_url,
                _session_info["url"],
                _session_info["token"],
            )

            def _on_stdout(text: str):
                if term_entry["ready"] and mt.page and getattr(mt, "uid", None):
                    try:
                        mt.write(text)
                        return
                    except Exception as ex:
                        logger.debug("Buffering stdout: %s", ex)
                term_entry["pending_stdout"].append(text)

            def _on_status(msg: str, ok: bool):
                if _active_tab_id == term_entry["id"]:
                    if _status_ref.current:
                        _status_ref.current.value = msg
                        _status_ref.current.color = (
                            AppColors.SUCCESS if ok else ft.Colors.ON_SURFACE_VARIANT
                        )
                    if _spinner_ref.current:
                        _spinner_ref.current.visible = not ok
                    if page:
                        page.update()

            client = colab_service.get_terminal_client(
                colab_ws_url, _on_stdout, _on_status
            )
            term_entry["client"] = client

            def _on_terminal_bytes(payload: bytes):
                if term_entry.get("client"):
                    page.run_task(term_entry["client"].send_input, payload)

            mt.set_on_bytes(_on_terminal_bytes)

            def _on_terminal_resize(ev):
                if term_entry.get("client") and ev.data:
                    try:
                        info = json.loads(ev.data)
                        cols = info.get("cols", 80)
                        rows = info.get("rows", 24)
                        page.run_task(term_entry["client"].set_size, rows, cols)
                    except Exception as ex:
                        logger.debug("Error handling terminal resize: %s", ex)

            mt.on_resize = _on_terminal_resize
            await client.connect()

            term_entry["ready"] = True
            if term_entry["pending_stdout"] and mt.page and getattr(mt, "uid", None):
                for chunk in term_entry["pending_stdout"]:
                    try:
                        mt.write(chunk)
                    except Exception:
                        pass
                term_entry["pending_stdout"].clear()

        except Exception as ex:
            logger.error("Terminal %s init failed: %s", new_id, ex)
            if _active_tab_id == new_id:
                if _status_ref.current:
                    _status_ref.current.value = f"Error: {ex}"
                    _status_ref.current.color = AppColors.ERROR
                if _spinner_ref.current:
                    _spinner_ref.current.visible = False
                if page:
                    page.update()
            if snack:
                snack(f"Terminal {new_id} error: {ex}")

    async def _init_panel():
        if _terminals:
            for t in _terminals:
                if t.get("client"):
                    try:
                        t["client"].close()
                    except Exception:
                        pass
            _terminals.clear()
            _terminal_stack.controls.clear()
        await _create_and_connect_terminal()

    panel = ft.Container(
        content=ft.Column(
            controls=[status, _switcher_container, _terminal_stack],
            spacing=0,
            expand=True,
        ),
        expand=True,
    )

    return panel, _init_panel


def build_terminal_view(
    page: ft.Page,
    colab_service,
    session_name: str,
    state=None,
    on_back=None,
    snack: Optional[Callable[[str], None]] = None,
    theme_btn=None,
) -> ft.View:
    """Build a view with the native Colab terminal control."""
    panel, init_func = build_terminal_panel(page, session_name, colab_service, snack)
    page.run_task(init_func)

    refresh_btn = ft.IconButton(
        icon=ft.Icons.REFRESH_ROUNDED,
        tooltip="Reconnect / Refresh Terminals",
        icon_size=tokens.ICON_MD,
        on_click=lambda e: page.run_task(init_func, e),
    )
    appbar_actions = [refresh_btn]
    if theme_btn:
        appbar_actions.append(theme_btn)

    view = ft.View(
        route=f"/terminal?session={session_name}",
        controls=[panel],
        padding=0,
        appbar=ft.AppBar(
            leading=ft.Container(
                content=ft.IconButton(
                    icon=ft.Icons.ARROW_BACK_ROUNDED,
                    on_click=on_back,
                    icon_size=tokens.ICON_MD,
                    tooltip="Back",
                ),
                padding=ft.Padding(tokens.SPACE_XS, 0, 0, 0),
            ),
            leading_width=48,
            title=ft.Text("Terminal", size=tokens.FONT_LG, weight=ft.FontWeight.W_700),
            center_title=True,
            bgcolor=ft.Colors.TRANSPARENT,
            actions=appbar_actions,
        ),
    )

    return view


# ── Shared helpers ────────────────────────────────────────────────────────────


async def _get_terminal_session(colab_service, session_name: str):
    """Retrieve endpoint, url, and token for *session_name* from Colab's store."""
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

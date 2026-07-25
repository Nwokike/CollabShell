"""Terminal view — real Colab PTY shell with persistent multi-terminal tabs.

Uses `flet_terminal.MobileTerminal` (powered by `xterm.dart` and `DataChannel`)
connected directly to remote Colab WebSockets, featuring a horizontal pill switcher
bar that avoids swipe conflicts and lets you open multiple persistent terminals.
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
    on_fullscreen_change: Optional[Callable[[bool], None]] = None,
) -> tuple[ft.Container, Callable[[], None]]:
    """Build native multi-tab terminal panel and return (container, init_task)."""
    _spinner = ft.Ref[ft.ProgressRing]()
    _status = ft.Ref[ft.Text]()
    _session_info = None

    _terminals: list[dict] = []
    _active_id = 0
    _is_fullscreen = {"value": False}

    _switcher_row = ft.Row(
        controls=[],
        spacing=tokens.SPACE_XS,
        scroll=ft.ScrollMode.AUTO,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    _switcher_box = ft.Container(
        content=_switcher_row,
        padding=ft.Padding(
            tokens.SPACE_MD, tokens.SPACE_MICRO, tokens.SPACE_MD, tokens.SPACE_MICRO
        ),
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
    )
    _stack = ft.Stack(controls=[], expand=True)

    def _set_fullscreen(val: bool):
        _is_fullscreen["value"] = val
        status_bar.visible = True
        _switcher_box.visible = True
        _refresh_switcher()
        if on_fullscreen_change:
            try:
                on_fullscreen_change(val)
            except Exception:
                pass
        if page:
            try:
                page.update()
            except RuntimeError:
                pass

    status_bar = ft.Container(
        content=ft.Row(
            controls=[
                ft.ProgressRing(
                    ref=_spinner,
                    width=tokens.ICON_XS,
                    height=tokens.ICON_XS,
                    stroke_width=tokens.SPACE_NANO,
                ),
                ft.Text(
                    ref=_status,
                    value="Loading session…",
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Container(expand=True),
            ],
            spacing=tokens.SPACE_SM,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(
            tokens.SPACE_MD, tokens.SPACE_NANO, tokens.SPACE_MD, tokens.SPACE_NANO
        ),
    )

    def _refresh_switcher():
        ctrls = []
        for t in _terminals:
            tid = t["id"]
            active = tid == _active_id
            c = ft.Colors.PRIMARY if active else ft.Colors.ON_SURFACE_VARIANT
            border = ft.BorderSide(
                1, ft.Colors.PRIMARY if active else ft.Colors.OUTLINE_VARIANT
            )
            ctrls.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Text(
                                f"Terminal {tid}",
                                size=tokens.FONT_XS,
                                weight=ft.FontWeight.BOLD
                                if active
                                else ft.FontWeight.NORMAL,
                                color=c,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.CLOSE_ROUNDED,
                                icon_size=tokens.ICON_MICRO,
                                style=ft.ButtonStyle(
                                    padding=tokens.SPACE_MICRO,
                                    visual_density=ft.VisualDensity.COMPACT,
                                    color=AppColors.ERROR if active else c,
                                ),
                                tooltip="Close terminal",
                                on_click=lambda e, id_val=tid: _close_terminal(id_val),
                            ),
                        ],
                        spacing=tokens.SPACE_MICRO,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding(
                        tokens.SPACE_SM,
                        tokens.SPACE_NANO,
                        tokens.SPACE_XS,
                        tokens.SPACE_NANO,
                    ),
                    border_radius=tokens.RADIUS_MD,
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST
                    if active
                    else ft.Colors.TRANSPARENT,
                    border=ft.Border(
                        left=border, top=border, right=border, bottom=border
                    ),
                    ink=True,
                    on_click=lambda e, id_val=tid: _select_terminal(id_val),
                )
            )
        ctrls.append(
            ft.IconButton(
                icon=ft.Icons.ADD_CIRCLE_OUTLINE_ROUNDED,
                tooltip="New Terminal Tab",
                icon_size=tokens.ICON_SM,
                style=ft.ButtonStyle(
                    padding=tokens.SPACE_MICRO, visual_density=ft.VisualDensity.COMPACT
                ),
                icon_color=ft.Colors.PRIMARY,
                on_click=lambda e: page.run_task(_create_terminal),
            )
        )
        is_fs = _is_fullscreen["value"]
        ctrls.append(
            ft.IconButton(
                icon=ft.Icons.FULLSCREEN_EXIT_ROUNDED
                if is_fs
                else ft.Icons.FULLSCREEN_ROUNDED,
                tooltip="Exit Fullscreen Mode"
                if is_fs
                else "Full Screen Terminal Mode",
                icon_size=tokens.ICON_SM,
                style=ft.ButtonStyle(
                    padding=tokens.SPACE_MICRO, visual_density=ft.VisualDensity.COMPACT
                ),
                icon_color=ft.Colors.PRIMARY,
                on_click=lambda e: _set_fullscreen(not _is_fullscreen["value"]),
            )
        )
        _switcher_row.controls = ctrls
        if page:
            page.update()

    def _select_terminal(tid: int):
        nonlocal _active_id
        _active_id = tid
        for t in _terminals:
            t["mt"].visible = t["id"] == _active_id
        _refresh_switcher()

    def _close_terminal(tid: int):
        nonlocal _active_id
        target = next((t for t in _terminals if t["id"] == tid), None)
        if target:
            _terminals.remove(target)
            if target.get("client"):
                try:
                    target["client"].close()
                except Exception:
                    pass
            if target.get("mt") in _stack.controls:
                _stack.controls.remove(target["mt"])

        if not _terminals:
            page.run_task(_create_terminal)
        elif _active_id == tid:
            _select_terminal(_terminals[-1]["id"])
        else:
            _refresh_switcher()

    async def _create_terminal(e=None):
        nonlocal _session_info, _active_id
        if not _session_info:
            _session_info = await _get_terminal_session(colab_service, session_name)
            if not _session_info:
                if _status.current:
                    _status.current.value = "Session not found"
                    _status.current.color = AppColors.ERROR
                if _spinner.current:
                    _spinner.current.visible = False
                if page:
                    page.update()
                if snack:
                    snack("Session not found — create one first")
                return

        new_id = max([t["id"] for t in _terminals], default=0) + 1
        _active_id = new_id
        for t in _terminals:
            t["mt"].visible = False

        mt = MobileTerminal(
            show_extra_keys=True,
            show_search=False,
            show_settings=True,
            scrollback=10000,
            font_family="JetBrains Mono",
            font_size=11.0,
            theme=BUILTIN_THEMES.get("JetBrains Dark", None),
            auto_focus=False,
            expand=True,
        )
        mt.visible = True

        entry = {
            "id": new_id,
            "mt": mt,
            "client": None,
            "pending_stdout": [],
            "ready": False,
        }
        _terminals.append(entry)
        _stack.controls.append(mt)
        _refresh_switcher()

        if _status.current:
            _status.current.value = f"Connecting Terminal {new_id}…"
            _status.current.color = ft.Colors.ON_SURFACE_VARIANT
        if _spinner.current:
            _spinner.current.visible = True
        if page:
            page.update()

        for _ in range(40):
            if mt.page is not None:
                break
            await asyncio.sleep(0.05)

        try:
            ws_url = await asyncio.to_thread(
                colab_service.create_terminal_ws_url,
                _session_info["url"],
                _session_info["token"],
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
                if entry["ready"] and mt.page is not None:
                    try:
                        _write_to_terminal(text)
                        return
                    except Exception as ex:
                        logger.debug("Buffering stdout: %s", ex)
                entry["pending_stdout"].append(text)

            def _on_status(msg: str, ok: bool):
                if _active_id == entry["id"]:
                    if _status.current:
                        _status.current.value = msg
                        _status.current.color = (
                            AppColors.SUCCESS if ok else ft.Colors.ON_SURFACE_VARIANT
                        )
                    if _spinner.current:
                        _spinner.current.visible = not ok
                    if page:
                        page.update()

            client = colab_service.get_terminal_client(ws_url, _on_stdout, _on_status)
            entry["client"] = client

            def _safe_run_task(task_fn, *args):
                try:
                    if getattr(page, "_session", getattr(page, "session", None)):
                        page.run_task(task_fn, *args)
                except RuntimeError:
                    pass

            def _on_bytes(payload: bytes | str):
                if not _is_fullscreen["value"] and payload:
                    _set_fullscreen(True)
                if entry.get("client"):
                    data = (
                        payload
                        if isinstance(payload, bytes)
                        else payload.encode("utf-8", errors="ignore")
                    )
                    _safe_run_task(entry["client"].send_input, data)

            mt.set_on_bytes(_on_bytes)
            mt.on_data = lambda e: _on_bytes(
                e.data if isinstance(e.data, str) else str(e.data)
            )

            def _on_resize(ev):
                if entry.get("client") and ev.data:
                    try:
                        info = json.loads(ev.data)
                        _safe_run_task(
                            entry["client"].set_size,
                            info.get("rows", 24),
                            info.get("cols", 80),
                        )
                    except Exception as ex:
                        logger.debug("Error handling terminal resize: %s", ex)

            mt.on_resize = _on_resize
            await client.connect()
            entry["ready"] = True

            if entry["pending_stdout"] and mt.page is not None:
                for chunk in entry["pending_stdout"]:
                    try:
                        _write_to_terminal(chunk)
                    except Exception:
                        pass
                entry["pending_stdout"].clear()

            if entry.get("client"):
                _safe_run_task(entry["client"].send_input, "\r")

        except Exception as ex:
            logger.error("Terminal %s init failed: %s", new_id, ex)
            if _active_id == new_id:
                if _status.current:
                    _status.current.value = f"Error: {ex}"
                    _status.current.color = AppColors.ERROR
                if _spinner.current:
                    _spinner.current.visible = False
                if page:
                    page.update()
            if snack:
                snack(f"Terminal {new_id} error: {ex}")

    async def _init_panel(e=None):
        _set_fullscreen(False)
        for t in _terminals:
            if t.get("client"):
                try:
                    t["client"].close()
                except Exception:
                    pass
        _terminals.clear()
        _stack.controls.clear()
        await _create_terminal()

    panel = ft.Container(
        content=ft.Column(
            controls=[status_bar, _switcher_box, _stack], spacing=0, expand=True
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
    actions = [refresh_btn]
    if theme_btn:
        actions.append(theme_btn)

    return ft.View(
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
            actions=actions,
        ),
    )


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

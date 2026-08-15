"""Native Colab Terminal panel using flet_multi_terminal."""

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


def build_terminal_panel(
    page: ft.Page,
    session_name: str,
    colab_service,
    snack: Callable[[str], None] | None = None,
    on_fullscreen_change: Callable[[bool], None] | None = None,
) -> tuple[ft.Container, Callable[..., asyncio.Future]]:
    """Build multi-terminal panel with tab management and dynamic switching."""
    _terminals: list[dict] = []
    _active_id: int = 1
    _next_id: int = 1
    _is_fullscreen = {"value": False}

    _status = ft.Ref[ft.Text]()
    _spinner = ft.Ref[ft.ProgressRing]()
    _switcher_row = ft.Ref[ft.Row]()
    _switcher_box = ft.Container(
        content=ft.Row(
            ref=_switcher_row, spacing=tokens.SPACE_XS, scroll=ft.ScrollMode.AUTO
        ),
        padding=ft.Padding(tokens.SPACE_SM, 0, tokens.SPACE_SM, 0),
        bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.ON_SURFACE),
    )
    _stack = ft.Stack(expand=True)

    def _set_fullscreen(fullscreen: bool):
        _is_fullscreen["value"] = fullscreen
        if _switcher_box:
            _switcher_box.visible = not fullscreen
        if on_fullscreen_change:
            on_fullscreen_change(fullscreen)
        if page:
            page.update()

    status_bar = ft.Container(
        content=ft.Row(
            controls=[
                ft.ProgressRing(
                    ref=_spinner, width=14, height=14, stroke_width=2, visible=False
                ),
                ft.Text(
                    ref=_status,
                    value="Ready",
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    expand=True,
                ),
                ft.IconButton(
                    icon=ft.Icons.FULLSCREEN_EXIT_ROUNDED
                    if _is_fullscreen["value"]
                    else ft.Icons.FULLSCREEN_ROUNDED,
                    icon_size=tokens.ICON_SM,
                    tooltip="Toggle Fullscreen",
                    on_click=lambda e: _set_fullscreen(not _is_fullscreen["value"]),
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

    def _refresh_switcher():
        nonlocal _active_id
        if not _switcher_row.current:
            return
        tabs: list[ft.Control] = []
        for t in _terminals:
            tid = t["id"]
            is_active = tid == _active_id
            btn = ft.Container(
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
                            f"Term {tid}",
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
                            on_tap=lambda e, x=tid: _close_terminal(x),
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
                on_click=lambda e, x=tid: _switch_to(x),
                ink=True,
            )
            tabs.append(btn)

        add_btn = ft.IconButton(
            icon=ft.Icons.ADD_ROUNDED,
            icon_size=tokens.ICON_SM,
            tooltip="New Terminal",
            on_click=lambda e: page.run_task(_create_terminal),
        )
        tabs.append(add_btn)
        _switcher_row.current.controls = tabs

    def _switch_to(tid: int):
        nonlocal _active_id
        _active_id = tid
        for t in _terminals:
            t["mt"].visible = t["id"] == tid
        _refresh_switcher()
        if page:
            page.update()

    def _close_terminal(tid: int):
        nonlocal _active_id
        idx = next((i for i, t in enumerate(_terminals) if t["id"] == tid), -1)
        if idx == -1:
            return
        entry = _terminals.pop(idx)
        if entry.get("client"):
            try:
                entry["client"].close()
            except Exception:
                pass
        try:
            _stack.controls.remove(entry["mt"])
        except ValueError:
            pass

        if not _terminals:
            page.run_task(_create_terminal)
            return

        if _active_id == tid:
            new_idx = max(0, idx - 1)
            _active_id = _terminals[new_idx]["id"]
            _terminals[new_idx]["mt"].visible = True

        _refresh_switcher()
        if page:
            page.update()

    async def _create_terminal():
        nonlocal _next_id, _active_id
        new_id = _next_id
        _next_id += 1
        _active_id = new_id

        for t in _terminals:
            t["mt"].visible = False

        _session_info = await _get_terminal_session(colab_service, session_name)
        if not _session_info:
            if _status.current:
                _status.current.value = "Session not found."
                _status.current.color = AppColors.ERROR
            if page:
                page.update()
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

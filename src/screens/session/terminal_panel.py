"""Native Colab Terminal panel — declarative component using flet_terminal.

Panel state (tabs, active tab, status) is an @ft.observable model
(`TerminalPanelState`); the `TerminalPanel` component re-renders
reactively on every change.

Architecture notes (v2.0.1):

* Each terminal tab's Colab WebSocket is owned by `TerminalEntry` and created
  by the PANEL — not by the widget host component. The socket therefore
  survives tab switches, widget remounts, and session-screen re-renders.
* Every stdout chunk is mirrored into a per-tab scrollback ring buffer. When
  the terminal widget remounts (Dart side fires a `mount` event whenever the
  xterm view is recreated) the buffer is replayed so no content is lost —
  this is what fixed "switching tabs loses terminal content".
* Clients reconnect automatically with exponential backoff after drops
  (app backgrounded, network blip), and can be force-reconnected from the
  app lifecycle hook via `app_state.terminal_reconnect`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from collections.abc import Callable

import flet as ft
from flet_terminal import BUILTIN_THEMES, MobileTerminal

from components.shortcuts_help import open_shortcuts_help
from core import tokens
from core.state import state as app_state
from core.theme import AppColors, is_light_theme

logger = logging.getLogger("colab")

# Scrollback ring buffer kept per tab in Python so content can be replayed
# when the Dart xterm widget is recreated (tab switch, remount). Roughly
# 2000 chunks ⇒ several screens of output on a busy shell.
_SCROLLBACK_CHUNKS = 2000


def _compact_btn_style() -> ft.ButtonStyle:
    """Snug toolbar buttons — no Material 48dp minimum tap box."""
    return ft.ButtonStyle(
        padding=2,
        visual_density=ft.VisualDensity.COMPACT,
    )


def _active_theme_name(page: ft.Page | None = None) -> str:
    """Terminal theme that follows the app's light/dark mode."""
    return "Colab Light" if is_light_theme(page) else "JetBrains Dark"


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
    except Exception:
        logger.exception("Failed to get session data")
        return None


@ft.observable
class TerminalEntry:
    """One terminal tab: its widget, WebSocket client, and readiness."""

    def __init__(self, tid: int):
        self.id = tid
        # Built during render by _TerminalHost — see that component's
        # docstring for why it must NOT be constructed in an async task.
        self.mt: MobileTerminal | None = None
        self.client = None
        self.ready = False
        self.wired = False
        # Ring buffer of every stdout chunk (bytes) — replayed when the
        # terminal widget remounts so content survives tab switches.
        self.scrollback: deque[bytes] = deque(maxlen=_SCROLLBACK_CHUNKS)


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


def _make_entry_handlers(
    entry: TerminalEntry,
    ps: TerminalPanelState,
    page,
    colab_service,
    session_name: str,
    snack,
):
    """Build the per-tab WS callbacks. Called once, at WebSocket-creation time."""
    logger_ = logger

    def _safe_run_task(task_fn, *args):
        try:
            if getattr(page, "_session", getattr(page, "session", None)):
                page.run_task(task_fn, *args)
        except RuntimeError:
            logger_.exception("run_task failed")

    async def _connect():
        session_info = await _get_terminal_session(colab_service, session_name)
        if not session_info:
            ps.status = "Session not found."
            ps.status_ok = False
            if snack:
                snack("Session not found in store.")
            return

        if ps.active_id == entry.id:
            ps.status = f"Connecting Terminal {entry.id}…"
            ps.status_ok = False
            ps.connecting = True
        try:
            client = colab_service.get_terminal_client(
                session_info["url"],
                session_info["token"],
                _on_stdout,
                _on_status,
                session_name=session_name,
            )
            entry.client = client

            await client.connect()
            entry.ready = True

            if entry.client:
                # Colab PTYs open in /root; move to the shared data dir.
                _safe_run_task(entry.client.send_input, "cd /content\r\n")

        except Exception as ex:
            # A 404 from POST /api/terminals usually means the cached
            # runtime-proxy token expired (they live for hours, not the
            # lifetime of the assignment). Re-mint it and retry once before
            # surfacing the failure.
            status = getattr(getattr(ex, "response", None), "status_code", None)
            healed = False
            if status == 404:
                try:
                    healed = await colab_service.refresh_session_token(
                        session_name, app_state.auth_method
                    )
                except Exception:
                    logger_.debug(
                        "token heal failed for %s", session_name, exc_info=True
                    )
            if healed:
                try:
                    session_info = await _get_terminal_session(
                        colab_service, session_name
                    )
                    if session_info:
                        client = colab_service.get_terminal_client(
                            session_info["url"],
                            session_info["token"],
                            _on_stdout,
                            _on_status,
                            session_name=session_name,
                        )
                        entry.client = client
                        await client.connect()
                        entry.ready = True
                        if entry.client:
                            _safe_run_task(entry.client.send_input, "cd /content\r\n")
                        logger_.info(
                            "Terminal %s connected after token refresh.",
                            entry.id,
                        )
                        return
                except Exception:
                    logger_.exception(
                        "Terminal %s retry after token refresh failed", entry.id
                    )
            logger_.exception("Terminal %s init failed", entry.id)
            if ps.active_id == entry.id:
                ps.status = f"Error: {ex}"
                ps.status_ok = False
                ps.connecting = False
            if snack:
                snack(f"Terminal {entry.id} error: {ex}")

    def _on_stdout(text: str):
        # Mirror into the ring buffer first — this is what survives widget
        # remounts and tab switches. send_bytes queues transparently when the
        # Dart channel is not ready yet (e.g. right after a remount).
        data = text.encode("utf-8", errors="ignore")
        entry.scrollback.append(data)
        if entry.mt is not None:
            entry.mt.send_bytes(data)

    def _on_status(msg: str, ok: bool):
        if ps.active_id == entry.id:
            ps.status = msg
            ps.status_ok = ok
            ps.connecting = not ok

    def replay_scrollback():
        """Re-send the buffered scrollback after a widget (re)mount.

        The Dart xterm buffer is empty after a fresh mount, so nothing the
        shell printed before the remount would be visible. Chunks that were
        sitting in the widget's own transport queue during the dead window
        were already mirrored into `entry.scrollback`, so clear them first
        and replay from the ring buffer — no duplicates, order preserved.
        """
        mt = entry.mt
        if mt is None:
            return
        with mt._terminal._lock:
            mt._terminal._pending_writes.clear()
        for chunk in list(entry.scrollback):
            mt.send_bytes(chunk)

    def _on_mount(e=None):
        # Fired by the Dart side whenever the xterm view is (re)created —
        # including after tab switches that dispose the hidden widget.
        replay_scrollback()

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
            except Exception:
                logger_.exception("Error handling terminal resize")

    return {
        "connect": _connect,
        "on_stdout": _on_stdout,
        "on_status": _on_status,
        "on_mount": _on_mount,
        "on_bytes": _on_bytes,
        "on_resize": _on_resize,
    }


@ft.component
def _TerminalHost(
    entry: TerminalEntry,
    ps: TerminalPanelState,
    handlers: dict,
    on_shortcut: Callable[[str], None] | None = None,
    focus_when_wired: bool = False,
) -> ft.Control:
    """Owns the MobileTerminal widget for one tab.

    The terminal widget is constructed DURING RENDER — the pattern proven
    responsive by the flet_terminal example app. Building the control inside
    a component render wires up its parent/page chain and did_mount()
    lifecycle correctly, so imperative changes (output writes, zoom, theme,
    blink) are pushed to the client immediately.

    The WebSocket is NOT created here (it lives on the entry, managed by the
    panel) — that is precisely why switching tabs no longer drops the shell.
    """
    page = ft.context.page

    # ── Build the widget once, during render ────────────────────────────────
    if entry.mt is None:
        mt = MobileTerminal(
            show_search=False,
            show_settings=False,
            scrollback=10000,
            font_family="JetBrains Mono",
            font_size=ps.zoom,
            theme=BUILTIN_THEMES.get(_active_theme_name(page)),
            auto_focus=False,
            expand=True,
        )
        # New terminals inherit the panel's current settings.
        if not ps.blink:
            mt.toggle_cursor_blink()
        entry.mt = mt
    mt = entry.mt

    # Wire handlers exactly once, before the first patch freezes the tree.
    if not entry.wired:
        mt.set_on_bytes(handlers["on_bytes"])
        mt.on_data = lambda e: handlers["on_bytes"](
            e.data if isinstance(e.data, str) else str(e.data)
        )
        mt.on_resize = handlers["on_resize"]
        # Firmware-level remount hook (Dart `initState` → "mount" event).
        mt._terminal.on_mount = handlers["on_mount"]
        # Dart-intercepted host shortcuts (flet-terminal ≥0.3.8). The combos
        # are consumed before the PTY, so they arrive only as events.
        if on_shortcut is not None:
            mt.on_shortcut = lambda e: on_shortcut(e.shortcut)
        entry.wired = True
        # New terminals grab the keyboard immediately on desktop so
        # Dart-intercepted shortcuts work without an extra click. Hidden
        # siblings are built too, hence the active-id gate.
        if focus_when_wired and ps.active_id == entry.id:
            try:
                if not page.platform.is_mobile():
                    mt.focus()
            except RuntimeError:
                logger.debug("Initial terminal focus deferred")

    return mt


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

    # ── Terminal lifecycle (panel-owned WebSockets) ─────────────────────────
    async def _connect_entry(entry: TerminalEntry):
        await entry._handlers["connect"]()

    def _create_terminal():
        """Register a new terminal tab and start its WebSocket.

        Handlers are built synchronously here so the first render of
        _TerminalHost can wire them immediately; the socket connects from a
        task right after. The MobileTerminal widget itself is built during
        render by _TerminalHost.
        """
        new_id = ps.next_id
        ps.next_id = new_id + 1
        ps.active_id = new_id
        entry = TerminalEntry(new_id)
        entry._handlers = _make_entry_handlers(
            entry, ps, page, colab_service, session_name, snack
        )
        ps.terminals.append(entry)
        ps.status = f"Opening Terminal {new_id}…"
        ps.status_ok = False
        ps.connecting = True
        page.run_task(entry._handlers["connect"])

    def _close_terminal(tid: int):
        idx = next((i for i, t in enumerate(ps.terminals) if t.id == tid), -1)
        if idx == -1:
            return
        entry = ps.terminals.pop(idx)
        if entry.client:
            try:
                entry.client.close()
            except Exception:
                logger.exception("Terminal client close failed")
        if not ps.terminals:
            _create_terminal()
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
                    logger.exception("Terminal client close failed")

    def _init_panel():
        _close_all_clients()
        for t in ps.terminals:
            t.mt = None  # widgets are owned per-panel-instance
        ps.terminals.clear()
        _create_terminal()

    async def _reconnect_dead():
        """Reconnect terminals whose sockets are no longer alive.

        Called from the app lifecycle resume hook — Colab's WS proxy closes
        idle sockets while the app is backgrounded but the PTY itself stays
        up, so ColabTerminalClient.reconnect() re-attaches to the same shell.
        """
        for entry in ps.terminals:
            client = entry.client
            if client is not None and not client.alive:
                logger.info("Reconnecting terminal %s on app resume", entry.id)
                await client.reconnect()

    async def _reconnect_active():
        """Manual reconnect for the active tab (top-bar / shortcut)."""
        entry = _active_entry()
        if entry is None:
            return
        if entry.client is None:
            ps.status = f"Connecting Terminal {entry.id}…"
            ps.connecting = True
            await entry._handlers["connect"]()
            return
        if entry.client.alive:
            if snack:
                snack(f"Terminal {entry.id} is already connected.")
            return
        ps.status = f"Reconnecting Terminal {entry.id}…"
        ps.connecting = True
        try:
            await entry.client.reconnect()
        except Exception as ex:
            logger.exception("Manual reconnect failed for terminal %s", entry.id)
            if snack:
                snack(f"Reconnect failed: {ex}", is_error=True)

    def _cycle_theme():
        names = list(BUILTIN_THEMES.keys())
        try:
            idx = names.index(ps.theme)
        except ValueError:
            idx = 0
        _set_theme(names[(idx + 1) % len(names)])

    def _refocus_terminal():
        """Return keyboard focus to the active terminal after a toolbar click.

        IconButtons steal focus when tapped, which silences every
        Dart-intercepted shortcut until the canvas is clicked again.
        Desktop only — on mobile requestFocus pops the soft keyboard.
        """
        try:
            if page.platform.is_mobile():
                return
        except Exception:
            pass
        entry = _active_entry()
        if entry and entry.mt:
            try:
                entry.mt.focus()
            except RuntimeError:
                logger.debug("Terminal focus deferred (page not ready)")

    def _switch_terminal_delta(delta: int):
        if not ps.terminals:
            return
        ids = [t.id for t in ps.terminals]
        try:
            pos = ids.index(ps.active_id)
        except ValueError:
            pos = 0
        ps.active_id = ids[(pos + delta) % len(ids)]

    def _handle_shortcut(name: str):
        """Dispatch Dart-intercepted terminal combos (flet-terminal ≥0.3.8)."""
        if name == "help":
            open_shortcuts_help(page, "terminal")
        elif name == "new_terminal":
            _create_terminal()
        elif name == "close_terminal":
            _close_terminal(ps.active_id)
        elif name.startswith("switch_terminal_"):
            try:
                target = int(name.rsplit("_", 1)[1])
            except ValueError:
                return
            if any(t.id == target for t in ps.terminals):
                ps.active_id = target
        elif name == "prev_terminal":
            _switch_terminal_delta(-1)
        elif name == "next_terminal":
            _switch_terminal_delta(1)
        elif name == "toggle_search":
            _toggle_search()
        elif name == "clear":
            _clear_terminal()
        elif name == "copy":
            page.run_task(_copy_selection)
        elif name == "paste":
            entry = _active_entry()
            if entry and entry.mt:
                entry.mt.paste()
        elif name == "zoom_in":
            _zoom_in()
        elif name == "zoom_out":
            _zoom_out()
        elif name == "zoom_reset":
            _zoom_reset()

    # ── Actions exposed to the SessionScreen FAB overflow menu ───────────────
    def _changed_settings():
        app_state.terminal_settings_rev += 1

    def _for_each_mt(fn):
        for t in ps.terminals:
            if t.mt is not None:
                fn(t.mt)

    def _set_theme(name: str):
        ps.theme = name
        _for_each_mt(lambda mt: mt.set_theme(name))
        _changed_settings()

    def _zoom_in():
        _for_each_mt(lambda mt: mt.zoom_in())
        entry = _active_entry()
        if entry and entry.mt:
            ps.zoom = entry.mt.font_size
        _changed_settings()

    def _zoom_out():
        _for_each_mt(lambda mt: mt.zoom_out())
        entry = _active_entry()
        if entry and entry.mt:
            ps.zoom = entry.mt.font_size
        _changed_settings()

    def _zoom_reset():
        _for_each_mt(lambda mt: mt.reset_zoom())
        entry = _active_entry()
        if entry and entry.mt:
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
        if not entry or not entry.mt:
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
                "new_terminal": lambda: _create_terminal(),
                "close_terminal": lambda: _close_terminal(ps.active_id),
                "reconnect": lambda: page.run_task(_reconnect_active),
                "cycle_theme": _cycle_theme,
                "clear_terminal": _clear_terminal,
                "copy": lambda: page.run_task(_copy_selection),
                "paste": lambda: (
                    _active_entry().mt.paste()
                    if _active_entry() and _active_entry().mt
                    else None
                ),
                # Settings (consumed by the FAB menu, with live checkmarks)
                "theme": _set_theme,
                "zoom_in": _zoom_in,
                "zoom_out": _zoom_out,
                "zoom_reset": _zoom_reset,
                "toggle_blink": _toggle_blink,
                "toggle_search": _toggle_search,
                "font_size": lambda: (
                    _active_entry().mt.font_size
                    if _active_entry() and _active_entry().mt
                    else ps.zoom
                ),
            }
        )

    # Self-initialize on mount; register the resume-reconnect hook globally
    # so main.py's lifecycle handler can reach it, and clear on unmount.
    def _on_mount():
        app_state.terminal_reconnect = _reconnect_dead
        _init_panel()

    def _cleanup():
        _close_all_clients()
        if getattr(app_state, "terminal_reconnect", None) is _reconnect_dead:
            app_state.terminal_reconnect = None

    ft.on_mounted(_on_mount)
    ft.use_effect(lambda: None, [], cleanup=_cleanup)

    # Follow the app's light/dark mode: re-apply the terminal theme whenever
    # the requested mode changes or the OS flips brightness in SYSTEM mode.
    def _apply_app_theme():
        name = _active_theme_name(page)
        for t in ps.terminals:
            if t.mt is not None:
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
            style=_compact_btn_style(),
            on_click=lambda e: (_create_terminal(), _refocus_terminal()),
        )
    )

    # Compact action cluster: Material's default ~48dp tap box per IconButton
    # is what created the wide gaps; COMPACT density + tight padding keeps the
    # icons snug while staying comfortably tappable.
    reconnect_btn = ft.IconButton(
        icon=ft.Icons.SYNC_ROUNDED,
        icon_size=tokens.ICON_SM,
        tooltip="Reconnect Terminal",
        style=_compact_btn_style(),
        on_click=lambda e: (page.run_task(_reconnect_active), _refocus_terminal()),
    )
    theme_btn = ft.IconButton(
        icon=ft.Icons.PALETTE_ROUNDED,
        icon_size=tokens.ICON_SM,
        tooltip="Cycle Terminal Theme",
        style=_compact_btn_style(),
        on_click=lambda e: (_cycle_theme(), _refocus_terminal()),
    )
    zoom_out_btn = ft.IconButton(
        icon=ft.Icons.ZOOM_OUT,
        icon_size=tokens.ICON_SM,
        tooltip="Zoom Out",
        style=_compact_btn_style(),
        on_click=lambda e: (_zoom_out(), _refocus_terminal()),
    )
    zoom_in_btn = ft.IconButton(
        icon=ft.Icons.ZOOM_IN,
        icon_size=tokens.ICON_SM,
        tooltip="Zoom In",
        style=_compact_btn_style(),
        on_click=lambda e: (_zoom_in(), _refocus_terminal()),
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
                reconnect_btn,
                theme_btn,
                zoom_out_btn,
                zoom_in_btn,
            ],
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(tokens.SPACE_SM, 0, tokens.SPACE_SM, 0),
        bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.ON_SURFACE),
    )

    # Each terminal gets a keyed _TerminalHost so the MobileTerminal instance
    # is stable across panel re-renders and mounts exactly once.
    stack_children = [
        ft.Container(
            content=_TerminalHost(
                entry=t,
                ps=ps,
                handlers=t._handlers or {},
                on_shortcut=_handle_shortcut,
                focus_when_wired=True,
                key=ft.ValueKey(f"host_{t.id}"),
            ),
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

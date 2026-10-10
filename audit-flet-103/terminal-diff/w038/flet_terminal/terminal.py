import logging
import threading
from dataclasses import dataclass
from typing import Any

import flet as ft
from flet.controls.base_control import control
from flet.data_channel import DataChannel, DataChannelOpenEvent

logger = logging.getLogger(__name__)

__all__ = ["ShortcutEvent", "Terminal"]


@dataclass
class ShortcutEvent(ft.Event["Terminal"]):
    """Fired when a built-in terminal keyboard shortcut is consumed on the
    Dart side. The key combination never reaches the PTY — returning
    ``handled`` from xterm's ``onKeyEvent`` swallows it before input
    processing. Enabled only when ``on_shortcut`` is set."""

    shortcut: str = ""
    """Machine name of the shortcut, e.g. ``"new_terminal"``."""


@control("FletTerminal")
class Terminal(ft.LayoutControl):
    """
    Native GPU-accelerated Terminal control for Flet using xterm.dart.
    Provides full xterm.js feature parity across Windows, Linux, macOS, Android, and Web.
    """

    scrollback: int | None = 10000
    font_family: str | None = "JetBrains Mono"
    font_size: float | None = 11.0
    cursor_blink: bool | None = True
    cursor_style: str | None = "block"  # "block", "underline", "bar"
    theme: dict[str, Any] | None = None
    read_only: bool | None = False
    auto_focus: bool | None = True

    # Sticky modifier key states (synced bidirectionally with Dart)
    ctrl_active: bool | None = False
    alt_active: bool | None = False

    # Standard Flet event handlers
    on_data: ft.ControlEventHandler | None = None
    on_resize: ft.ControlEventHandler | None = None
    on_modifier_reset: ft.ControlEventHandler | None = None
    on_title_change: ft.ControlEventHandler | None = None
    on_bell: ft.ControlEventHandler | None = None
    on_selection_change: ft.ControlEventHandler | None = None
    on_copy: ft.ControlEventHandler | None = None
    on_mount: ft.ControlEventHandler | None = None
    on_shortcut: ft.EventHandler[ShortcutEvent] | None = None

    # Internal channel setup handler
    on_data_channel_open: ft.EventHandler[DataChannelOpenEvent] | None = None

    def init(self):
        self._lock = threading.Lock()
        self._channel: DataChannel | None = None
        self._on_bytes_handler = None
        if self.on_data_channel_open is None:
            self.on_data_channel_open = self._handle_data_channel_open
        self._on_unmount_callback = None
        self._pending_writes: list[Any] = []
        self._dart_ready: bool = False
        self._channel_ready: bool = False

    def before_event(self, e: ft.ControlEvent):
        self._mark_dart_ready()
        return super().before_event(e)

    def _mark_dart_ready(self):
        if not self._dart_ready:
            self._dart_ready = True
        with self._lock:
            pending = list(self._pending_writes)
            self._pending_writes.clear()
        remaining = []
        for task_fn, args in pending:
            if not self.page or not self._dart_ready:
                remaining.append((task_fn, args))
                continue
            if task_fn == self.send_bytes and not self._channel_ready:
                remaining.append((task_fn, args))
                continue
            try:
                if args is not None:
                    self.page.run_task(task_fn, *args)
                else:
                    self.page.run_task(task_fn)
            except Exception:
                logger.debug("Pending write deferred (run_task failed)", exc_info=True)
                remaining.append((task_fn, args))
        if remaining:
            with self._lock:
                self._pending_writes.extend(remaining)

    def did_mount(self):
        super().did_mount()
        self._mark_dart_ready()

    def _handle_data_channel_open(self, e: DataChannelOpenEvent):
        if e.channel_name == "pty" or not self._channel:
            self._channel = self.get_data_channel(e.channel_id)
            if self._on_bytes_handler:
                self._channel.on_bytes(self._on_bytes_handler)
            self._channel_ready = True
        self._mark_dart_ready()

    def set_on_bytes(self, handler):
        """Registers a callback for raw bytes pushed from Dart to Python."""
        self._on_bytes_handler = handler
        if self._channel:
            self._channel.on_bytes(handler)

    def send_bytes(self, payload: bytes):
        """Sends raw bytes from Python to Dart (writing to terminal canvas)."""
        try:
            if self._channel is not None and self._channel_ready and self._dart_ready:
                self._channel.send(payload)
            else:
                with self._lock:
                    self._pending_writes.append((self.send_bytes, (payload,)))
        except Exception:
            logger.debug("send_bytes deferred (channel unavailable)", exc_info=True)
            with self._lock:
                self._pending_writes.append((self.send_bytes, (payload,)))

    def send_input(self, payload: bytes):
        """Forwards virtual key payload directly to the registered PTY input handler (`_on_bytes_handler`)."""
        if self._on_bytes_handler:
            self._on_bytes_handler(payload)

    def will_unmount(self):
        """Disposes resources and sockets when the terminal control is removed from tree."""
        super().will_unmount()
        self._dart_ready = False
        with self._lock:
            self._pending_writes.clear()
        if self._on_unmount_callback:
            try:
                self._on_unmount_callback()
            except Exception:
                logger.exception("Terminal unmount callback raised")

    async def write_async(self, data: str | bytes):
        """Writes text or escape sequences to the terminal via DataChannel (fast path) or Flet method invocation."""
        try:
            if self._channel is not None and self._channel_ready and self._dart_ready:
                payload = (
                    data.encode("utf-8", errors="ignore")
                    if isinstance(data, str)
                    else data
                )
                self._channel.send(payload)
                return
            if not self.page or not self._dart_ready:
                with self._lock:
                    self._pending_writes.append((self.write_async, (data,)))
                return
        except RuntimeError:
            with self._lock:
                self._pending_writes.append((self.write_async, (data,)))
            return
        payload = (
            data if isinstance(data, str) else data.decode("utf-8", errors="ignore")
        )
        try:
            await self._invoke_method("write", {"data": payload})
        except RuntimeError:
            with self._lock:
                self._pending_writes.append((self.write_async, (data,)))

    def write(self, data: str | bytes):
        """Synchronous wrapper for write_async, routing to DataChannel when available."""
        try:
            if self._channel is not None and self._channel_ready and self._dart_ready:
                payload = (
                    data.encode("utf-8", errors="ignore")
                    if isinstance(data, str)
                    else data
                )
                self._channel.send(payload)
                return
            if not self.page or not self._dart_ready:
                with self._lock:
                    self._pending_writes.append((self.write_async, (data,)))
                return
            self.page.run_task(self.write_async, data)
        except RuntimeError:
            with self._lock:
                self._pending_writes.append((self.write_async, (data,)))

    async def clear_async(self):
        """Clears the terminal scrollback and buffer."""
        try:
            if not self.page or not self._dart_ready:
                with self._lock:
                    self._pending_writes.append((self.clear_async, None))
                return
        except RuntimeError:
            with self._lock:
                self._pending_writes.append((self.clear_async, None))
            return
        try:
            await self._invoke_method("clear")
        except RuntimeError:
            with self._lock:
                self._pending_writes.append((self.clear_async, None))

    def clear(self):
        """Synchronous wrapper for clear_async."""
        try:
            if not self.page or not self._dart_ready:
                with self._lock:
                    self._pending_writes.append((self.clear_async, None))
                return
            self.page.run_task(self.clear_async)
        except RuntimeError:
            with self._lock:
                self._pending_writes.append((self.clear_async, None))

    async def focus_async(self):
        """Requests keyboard focus on the terminal."""
        try:
            if not self.page or not self._dart_ready:
                with self._lock:
                    self._pending_writes.append((self.focus_async, None))
                return
        except RuntimeError:
            with self._lock:
                self._pending_writes.append((self.focus_async, None))
            return
        try:
            await self._invoke_method("focus")
        except RuntimeError:
            with self._lock:
                self._pending_writes.append((self.focus_async, None))

    def focus(self):
        """Synchronous wrapper for focus_async."""
        try:
            if not self.page or not self._dart_ready:
                with self._lock:
                    self._pending_writes.append((self.focus_async, None))
                return
            self.page.run_task(self.focus_async)
        except RuntimeError:
            with self._lock:
                self._pending_writes.append((self.focus_async, None))

    async def search_async(self, query: str, start: int = 0, direction: str = "next"):
        """Searches for text within the terminal scrollback ring buffer.

        `start` is the character offset to resume scanning from (used to step
        through successive matches). `direction` is "next" or "prev". The Dart
        side selects the match and reports the total count via the
        `on_selection_change` event.
        """
        try:
            if not self.page or not self._dart_ready:
                with self._lock:
                    self._pending_writes.append(
                        (self.search_async, (query, start, direction))
                    )
                return
        except RuntimeError:
            with self._lock:
                self._pending_writes.append(
                    (self.search_async, (query, start, direction))
                )
            return
        try:
            await self._invoke_method(
                "search", {"query": query, "start": start, "direction": direction}
            )
        except RuntimeError:
            with self._lock:
                self._pending_writes.append(
                    (self.search_async, (query, start, direction))
                )

    def search(self, query: str, start: int = 0, direction: str = "next"):
        """Synchronous wrapper for search_async."""
        try:
            if not self.page or not self._dart_ready:
                with self._lock:
                    self._pending_writes.append(
                        (self.search_async, (query, start, direction))
                    )
                return
            self.page.run_task(self.search_async, query, start, direction)
        except RuntimeError:
            with self._lock:
                self._pending_writes.append(
                    (self.search_async, (query, start, direction))
                )

    async def clear_selection_async(self):
        """Clears any active text selection in the terminal."""
        try:
            if not self.page or not self._dart_ready:
                with self._lock:
                    self._pending_writes.append((self.clear_selection_async, None))
                return
        except RuntimeError:
            with self._lock:
                self._pending_writes.append((self.clear_selection_async, None))
            return
        try:
            await self._invoke_method("clear_selection")
        except RuntimeError:
            with self._lock:
                self._pending_writes.append((self.clear_selection_async, None))

    def clear_selection(self):
        """Synchronous wrapper for clear_selection_async."""
        try:
            if not self.page or not self._dart_ready:
                with self._lock:
                    self._pending_writes.append((self.clear_selection_async, None))
                return
            self.page.run_task(self.clear_selection_async)
        except RuntimeError:
            with self._lock:
                self._pending_writes.append((self.clear_selection_async, None))

    async def select_all_async(self):
        """Selects all text currently in the terminal buffer and scrollback."""
        try:
            if not self.page or not self._dart_ready:
                with self._lock:
                    self._pending_writes.append((self.select_all_async, None))
                return
        except RuntimeError:
            with self._lock:
                self._pending_writes.append((self.select_all_async, None))
            return
        try:
            await self._invoke_method("select_all")
        except RuntimeError:
            with self._lock:
                self._pending_writes.append((self.select_all_async, None))

    def select_all(self):
        """Synchronous wrapper for select_all_async."""
        try:
            if not self.page or not self._dart_ready:
                with self._lock:
                    self._pending_writes.append((self.select_all_async, None))
                return
            self.page.run_task(self.select_all_async)
        except RuntimeError:
            with self._lock:
                self._pending_writes.append((self.select_all_async, None))

    async def get_selection_async(self) -> str | None:
        """Returns the currently selected text, or None when there is no
        selection or the control is not ready. Unlike the fire-and-forget
        methods above this is a request/response call, so it cannot be queued
        — callers should retry after mount if they get None."""
        try:
            if not self.page or not self._dart_ready:
                return None
            result = await self._invoke_method("get_selection")
            return result if result else None
        except RuntimeError:
            return None

    async def paste_async(self):
        """Reads the system clipboard on the Dart side and feeds it to the PTY."""
        try:
            if not self.page or not self._dart_ready:
                with self._lock:
                    self._pending_writes.append((self.paste_async, None))
                return
        except RuntimeError:
            with self._lock:
                self._pending_writes.append((self.paste_async, None))
            return
        try:
            await self._invoke_method("paste")
        except RuntimeError:
            with self._lock:
                self._pending_writes.append((self.paste_async, None))

    def paste(self):
        """Synchronous wrapper for paste_async."""
        try:
            if not self.page or not self._dart_ready:
                with self._lock:
                    self._pending_writes.append((self.paste_async, None))
                return
            self.page.run_task(self.paste_async)
        except RuntimeError:
            with self._lock:
                self._pending_writes.append((self.paste_async, None))

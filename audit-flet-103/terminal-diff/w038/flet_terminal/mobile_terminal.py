"""MobileTerminal — composite responsive control combining Terminal, virtual keyboard bar, and search."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import flet as ft

from .extra_keys import DEFAULT_EXTRA_KEYS, ExtraKeysBar
from .frozen_support import control_update, thaw
from .search_bar import TerminalSearchBar
from .terminal import Terminal
from .themes import BUILTIN_THEMES, get_theme

logger = logging.getLogger(__name__)

__all__ = ["MobileTerminal"]


class MobileTerminal(ft.Column):
    """High-level terminal wrapper with responsive virtual extra keys, sticky modifiers, and search."""

    def __init__(
        self,
        show_extra_keys: bool = True,
        show_search: bool = False,
        show_settings: bool = True,
        scrollback: int = 10000,
        font_family: str = "JetBrains Mono",
        font_size: float = 11.0,
        cursor_blink: bool = True,
        cursor_style: str = "block",
        theme: dict[str, Any] | None = None,
        read_only: bool = False,
        auto_focus: bool = True,
        extra_keys: list[tuple[str, bytes | None]] | None = None,
        expand: bool | int = True,
    ):
        super().__init__(expand=expand, spacing=0)

        self._terminal = Terminal(
            scrollback=scrollback,
            font_family=font_family,
            font_size=font_size,
            cursor_blink=cursor_blink,
            cursor_style=cursor_style,
            theme=theme or BUILTIN_THEMES["JetBrains Dark"],
            read_only=read_only,
            auto_focus=auto_focus,
            expand=True,
        )
        self._default_font_size = font_size

        # The search bar is created upfront (hidden by default) rather than
        # lazily on first toggle: injecting a brand-new child into the tree
        # after Flet's first declarative render never reaches the client,
        # while flipping `visible` on a stable child always diffs cleanly.
        self._search_bar = TerminalSearchBar(
            on_search=self._terminal.search,
            on_close=lambda: self.toggle_search(),
        )
        self._search_bar.visible = bool(show_search)
        self._user_on_selection_change = None
        # Route search results into the bar's match counter while still
        # forwarding the event to any user-supplied handler.
        self._terminal.on_selection_change = self._internal_on_selection_change

        self._keys_bar: ExtraKeysBar | None = None
        if show_extra_keys:
            self._keys_bar = ExtraKeysBar(
                on_send_payload=self._terminal.send_input,
                on_modifier_change=self._on_modifier_change,
                show_settings=show_settings,
                on_set_theme=self.set_theme,
                on_set_cursor=self.set_cursor_style,
                on_toggle_blink=self.toggle_cursor_blink,
                on_toggle_search=self.toggle_search,
                on_copy=self.copy_selection,
                on_paste=self.paste,
                on_select_all=self.select_all,
                on_clear=self.clear,
                keys=extra_keys or DEFAULT_EXTRA_KEYS,
            )
            self._terminal.on_modifier_reset = lambda e: (
                self._keys_bar.reset_modifiers() if self._keys_bar else None
            )
            self._keys_bar._on_zoom_in = self.zoom_in
            self._keys_bar._on_zoom_out = self.zoom_out
            self._keys_bar._on_zoom_reset = self.reset_zoom
            self._keys_bar.current_font_size = font_size
            self._keys_bar.default_font_size = font_size
            self._keys_bar.active_cursor = cursor_style
            self._keys_bar.active_blink = cursor_blink
            self._keys_bar.active_search = show_search
            if isinstance(theme, dict) and "name" in theme:
                self._keys_bar.active_theme = theme["name"]
            elif theme is None:
                self._keys_bar.active_theme = "JetBrains Dark"
            self._keys_bar.update_settings_menu()

        controls: list[ft.Control] = [self._terminal, self._search_bar]
        if self._keys_bar:
            controls.append(self._keys_bar)

        self.controls = controls

    def _internal_on_selection_change(self, e):
        """Routes selection_change events: feeds the search bar counter and
        forwards to any user-supplied on_selection_change handler."""
        import json

        if self._search_bar:
            try:
                data = json.loads(e.data) if isinstance(e.data, str) else (e.data or {})
                if "found" in data:  # search-originated event
                    self._search_bar.report_result(
                        bool(data.get("found")),
                        int(data.get("count", 0)),
                        int(data.get("index", -1)),
                    )
            except Exception:
                logger.debug("selection_change parse failed", exc_info=True)
        if self._user_on_selection_change:
            self._user_on_selection_change(e)

    def _on_modifier_change(self, ctrl: bool, alt: bool):
        with thaw(self._terminal):
            self._terminal.ctrl_active = ctrl
            self._terminal.alt_active = alt
            control_update(self._terminal)

    @property
    def show_search(self) -> bool:
        return bool(self._search_bar.visible)

    @show_search.setter
    def show_search(self, val: bool):
        bar = self._search_bar
        with thaw(bar):
            bar.visible = bool(val)
            control_update(bar)
        if self._keys_bar:
            self._keys_bar.active_search = bool(val)
            self._keys_bar.update_settings_menu()

    def toggle_search(self):
        """Toggle visibility of the search bar."""
        self.show_search = not self.show_search
        if self._keys_bar:
            self._keys_bar.active_search = self.show_search
            self._keys_bar.update_settings_menu()

    def set_theme(self, theme_name: str):
        """Switch the active terminal color theme by name."""
        preset = get_theme(theme_name)
        if preset:
            with thaw(self._terminal):
                self._terminal.theme = preset
                control_update(self._terminal)
            if self._keys_bar:
                self._keys_bar.active_theme = theme_name
                self._keys_bar.update_settings_menu()

    def set_cursor_style(self, style: str):
        """Set cursor shape ('block', 'underline', 'bar')."""
        with thaw(self._terminal):
            self._terminal.cursor_style = style
            control_update(self._terminal)
        if self._keys_bar:
            self._keys_bar.active_cursor = style
            self._keys_bar.update_settings_menu()

    def toggle_cursor_blink(self):
        """Toggle blinking animation for the cursor."""
        with thaw(self._terminal):
            self._terminal.cursor_blink = not self._terminal.cursor_blink
            control_update(self._terminal)
        if self._keys_bar:
            self._keys_bar.active_blink = self._terminal.cursor_blink
            self._keys_bar.update_settings_menu()

    def zoom_in(self, step: float = 1.0):
        """Increase terminal font size."""
        current = self._terminal.font_size or 11.0
        new_size = current + step
        with thaw(self._terminal):
            self._terminal.font_size = new_size
            control_update(self._terminal)
        if self._keys_bar:
            self._keys_bar.current_font_size = new_size
            self._keys_bar.update_settings_menu()

    def zoom_out(self, step: float = 1.0):
        """Decrease terminal font size (minimum 6.0px)."""
        current = self._terminal.font_size or 11.0
        if current > 6.0:
            new_size = max(6.0, current - step)
            with thaw(self._terminal):
                self._terminal.font_size = new_size
                control_update(self._terminal)
            if self._keys_bar:
                self._keys_bar.current_font_size = new_size
                self._keys_bar.update_settings_menu()

    def reset_zoom(self):
        """Reset terminal font size to original default."""
        with thaw(self._terminal):
            self._terminal.font_size = self._default_font_size
            control_update(self._terminal)
        if self._keys_bar:
            self._keys_bar.current_font_size = self._default_font_size
            self._keys_bar.update_settings_menu()

    # ─── Forwarded Terminal Methods & Properties ───────────────────────────

    @property
    def ctrl_active(self) -> bool:
        return self._terminal.ctrl_active or False

    @ctrl_active.setter
    def ctrl_active(self, val: bool):
        with thaw(self._terminal):
            self._terminal.ctrl_active = val
            control_update(self._terminal)
        if self._keys_bar:
            self._keys_bar.ctrl_active = val
            self._keys_bar.refresh_buttons()

    @property
    def alt_active(self) -> bool:
        return self._terminal.alt_active or False

    @alt_active.setter
    def alt_active(self, val: bool):
        with thaw(self._terminal):
            self._terminal.alt_active = val
            control_update(self._terminal)
        if self._keys_bar:
            self._keys_bar.alt_active = val
            self._keys_bar.refresh_buttons()

    def send_bytes(self, payload: bytes):
        self._terminal.send_bytes(payload)

    @property
    def font_size(self) -> float:
        """The terminal's current font size (default 11.0)."""
        return self._terminal.font_size or self._default_font_size

    @property
    def cursor_blink(self) -> bool:
        """Whether cursor blinking is enabled."""
        return bool(self._terminal.cursor_blink)

    @property
    def cursor_style(self) -> str:
        """The active cursor shape ('block', 'underline', 'bar')."""
        return self._terminal.cursor_style or "block"

    @property
    def theme_name(self) -> str | None:
        """Name of the active built-in theme, if any matches."""
        cur = self._terminal.theme or {}
        for name, preset in BUILTIN_THEMES.items():
            if all(cur.get(k) == v for k, v in preset.items()):
                return name
        return None

    def send_input(self, payload: bytes):
        self._terminal.send_input(payload)

    def write(self, data: str | bytes):
        self._terminal.write(data)

    def clear(self):
        self._terminal.clear()

    def focus(self):
        self._terminal.focus()

    def search(self, query: str, start: int = 0, direction: str = "next"):
        self._terminal.search(query, start, direction)

    def clear_selection(self):
        self._terminal.clear_selection()

    def select_all(self):
        self._terminal.select_all()

    async def get_selection_async(self) -> str | None:
        return await self._terminal.get_selection_async()

    async def copy_selection_async(self) -> bool:
        """Copies the current selection to the system clipboard.

        Returns True when text was copied. Fires the terminal's `on_copy`
        handler (via the Dart right-click path this already happens; this is
        the programmatic/mobile equivalent).
        """
        text = await self._terminal.get_selection_async()
        if not text:
            return False
        try:
            await ft.Clipboard().set(text)
        except Exception:
            logger.exception("Clipboard set failed")
            return False
        self._terminal.clear_selection()
        try:
            await self._terminal._trigger_event("copy", text)
        except Exception:
            logger.debug("copy event dispatch failed", exc_info=True)
        return True

    def copy_selection(self):
        """Synchronous wrapper for copy_selection_async."""
        try:
            if not self.page:
                return
            self.page.run_task(self.copy_selection_async)
        except RuntimeError:
            logger.debug("copy_selection deferred (page unavailable)", exc_info=True)

    async def paste_async(self):
        await self._terminal.paste_async()

    def paste(self):
        self._terminal.paste()

    def set_on_bytes(self, handler: Callable[[bytes], None]):
        self._terminal.set_on_bytes(handler)

    # Forwarded event handler accessors — handler assignment is a Prop write,
    # so each setter thaws the (possibly declarative-frozen) terminal first.
    @property
    def on_data(self):
        return self._terminal.on_data

    @on_data.setter
    def on_data(self, val):
        with thaw(self._terminal):
            self._terminal.on_data = val

    @property
    def on_resize(self):
        return self._terminal.on_resize

    @on_resize.setter
    def on_resize(self, val):
        with thaw(self._terminal):
            self._terminal.on_resize = val

    @property
    def on_title_change(self):
        return self._terminal.on_title_change

    @on_title_change.setter
    def on_title_change(self, val):
        with thaw(self._terminal):
            self._terminal.on_title_change = val

    @property
    def on_bell(self):
        return self._terminal.on_bell

    @on_bell.setter
    def on_bell(self, val):
        with thaw(self._terminal):
            self._terminal.on_bell = val

    @property
    def on_selection_change(self):
        return self._user_on_selection_change

    @on_selection_change.setter
    def on_selection_change(self, val):
        # Keep the internal router (search counter) installed; the user
        # handler is invoked from it.
        self._user_on_selection_change = val
        with thaw(self._terminal):
            if self._search_bar is not None:
                self._terminal.on_selection_change = self._internal_on_selection_change
            else:
                self._terminal.on_selection_change = val

    @property
    def on_copy(self):
        return self._terminal.on_copy

    @on_copy.setter
    def on_copy(self, val):
        with thaw(self._terminal):
            self._terminal.on_copy = val

    @property
    def on_shortcut(self):
        return self._terminal.on_shortcut

    @on_shortcut.setter
    def on_shortcut(self, val):
        with thaw(self._terminal):
            self._terminal.on_shortcut = val

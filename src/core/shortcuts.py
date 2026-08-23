"""Keyboard shortcut engine — bindings, router, and the help-sheet data.

`page.on_keyboard_event` is a window-level handler (the Flet client registers
it via ``HardwareKeyboard.instance.addHandler``), so it fires with accurate
shift/ctrl/alt/meta flags no matter which control holds focus — including
TextFields and the xterm terminal. The handler cannot consume events, so
while the Terminal subview is active the session provider returns
``SUPPRESS`` and the flet_terminal Dart-side interceptor owns those keys
(combos it consumes never reach the PTY).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import flet as ft

__all__ = ["SUPPRESS", "Binding", "ShortcutRouter", "shortcuts_router"]

# Provider-returned sentinel: "this context owns the keyboard — stop
# matching, no lower-priority provider (e.g. global bindings) may fire".
SUPPRESS = object()

_KEY_ALIASES = {"return": "enter", "esc": "escape"}


def normalize_key(key: str) -> str:
    """Normalize a key label for matching.

    Flutter's ``keyLabel`` varies by platform ("Enter" vs "Return",
    "Arrow Up" vs "ArrowUp"); lowercase + de-space + alias both sides.
    """
    k = key.replace(" ", "").lower()
    return _KEY_ALIASES.get(k, k)


@dataclass(frozen=True)
class Binding:
    """One key combination. ``ctrl`` matches Control OR Meta (Cmd on macOS)."""

    key: str
    ctrl: bool = False
    shift: bool = False
    alt: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", normalize_key(self.key))

    def matches(self, e: ft.KeyboardEvent) -> bool:
        if bool(self.ctrl) != bool(e.ctrl or e.meta):
            return False
        if self.shift != e.shift:
            return False
        if self.alt != e.alt:
            return False
        return normalize_key(e.key) == self.key


BindingsList = list[tuple[Binding, Callable]]
Provider = Callable[[], BindingsList | object]


class _ShortcutRouter:
    """Priority registry of context providers.

    Providers registered later shadow earlier ones (inner screen contexts
    register after the app shell). A provider returns a bindings list or
    ``SUPPRESS`` to stop matching entirely.
    """

    def __init__(self) -> None:
        self._providers: list[Provider] = []

    def register(self, provider: Provider) -> Callable[[], None]:
        self._providers.append(provider)

        def _unregister() -> None:
            try:
                self._providers.remove(provider)
            except ValueError:
                pass

        return _unregister

    def resolve(self, e: ft.KeyboardEvent) -> Callable | None:
        """Return the first matching action, or None when nothing matches."""
        for provider in reversed(self._providers):
            result = provider()
            if result is SUPPRESS:
                return None
            for binding, action in result or []:
                if binding.matches(e):
                    return action
        return None


shortcuts_router = _ShortcutRouter()

#: Public alias so the hook can type-hint against the router class.
ShortcutRouter = _ShortcutRouter

# ── Help sheet data (F1 dialog) ──────────────────────────────────────────────
# (combo label, description) rows per context. All user-visible text English.

SHORTCUT_DOCS: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "global": (
        "General",
        [
            ("F1", "Show this shortcuts help"),
            ("Ctrl+1 .. 5", "Switch section: Home, Notebooks, Terminal, Files, Settings"),
        ],
    ),
    "notebook": (
        "Notebook",
        [
            ("Shift+Enter", "Run cell and go to the next (adds one if last)"),
            ("Ctrl+Enter", "Run cell in place"),
            ("Alt+Enter", "Run cell and insert a new one below"),
            ("Ctrl+Shift+Enter", "Run all cells"),
            ("Ctrl+S", "Export notebook as .ipynb (download)"),
            ("Ctrl+Shift+A", "Insert code cell above"),
            ("Ctrl+Shift+B", "Insert code cell below"),
            ("Alt+Up / Alt+Down", "Move cell up / down"),
            ("Ctrl+Shift+D", "Delete cell"),
            ("Ctrl+Shift+M", "Toggle cell type (code / markdown)"),
            ("Escape", "Leave the editor (render markdown)"),
        ],
    ),
    "terminal": (
        "Terminal",
        [
            ("Ctrl+Shift+T", "New terminal"),
            ("Ctrl+Shift+W", "Close terminal"),
            ("Ctrl+Shift+1 .. 9", "Switch to terminal 1 .. 9"),
            ("Ctrl+PageUp / PageDown", "Previous / next terminal"),
            ("Ctrl+Shift+F", "Toggle search"),
            ("Ctrl+Shift+L", "Clear terminal"),
            ("Ctrl+Shift+C / V", "Copy selection / paste"),
            ("Ctrl+Shift+= / - / 0", "Zoom in / out / reset"),
            ("F1", "Show this shortcuts help"),
        ],
    ),
    "files": (
        "Files",
        [
            ("F5 / Ctrl+R", "Refresh listing"),
            ("Alt+Up / Backspace", "Go to parent folder"),
            ("Ctrl+A", "Select all items"),
            ("Ctrl+Shift+N", "New folder"),
            ("Delete", "Delete selection"),
            ("Escape", "Clear selection"),
        ],
    ),
}

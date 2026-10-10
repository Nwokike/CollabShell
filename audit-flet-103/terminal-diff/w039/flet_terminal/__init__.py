"""FletTerminal — GPU-accelerated Terminal control for Flet across Web, Desktop, and Mobile."""

from flet_terminal.extra_keys import DEFAULT_EXTRA_KEYS, ExtraKeysBar
from flet_terminal.mobile_terminal import MobileTerminal
from flet_terminal.search_bar import TerminalSearchBar
from flet_terminal.terminal import ShortcutEvent, Terminal
from flet_terminal.themes import BUILTIN_THEMES, get_theme

__all__ = [
    "BUILTIN_THEMES",
    "DEFAULT_EXTRA_KEYS",
    "ExtraKeysBar",
    "MobileTerminal",
    "ShortcutEvent",
    "Terminal",
    "TerminalSearchBar",
    "get_theme",
]

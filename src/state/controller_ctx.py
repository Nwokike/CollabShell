"""Controller context — exposes AppController callbacks to the component tree.

Components read controller methods via ``ft.use_context(ControllerMethodsCtx)``
to trigger navigation, session opening, theme toggles, etc.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import flet as ft


def _noop(*_args, **_kwargs) -> None:
    """No-op sync default."""


async def _noop_async_check_for_updates(*_args, **_kwargs) -> None:
    """No-op async default (update check)."""


@dataclass
class ControllerMethods:
    """Callbacks from AppController exposed to the component tree."""

    # Navigate to a specific bottom tab (0=Home, 1=Notebooks, 2=Terminal, 3=Files, 4=Settings)
    navigate_tab: Callable[[int], None] = field(default=_noop)
    # Open a session in the app shell (name, mode: "notebook"|"terminal"|"files")
    open_session: Callable[[str, str], None] = field(default=_noop)
    # Close the current session screen and return to home
    close_session: Callable[[], None] = field(default=_noop)
    # Open the history log viewer screen (optionally preselected for a session)
    open_history: Callable[[str], None] = field(default=_noop)
    # Close the history screen and return to home
    close_history: Callable[[], None] = field(default=_noop)
    # Show a snackbar message
    show_snack: Callable[[str], None] = field(default=_noop)
    # Show the new session bottom sheet (mode: "notebook"|"terminal"|"files")
    show_new_session_sheet: Callable[[str], None] = field(default=_noop)
    # Toggle dark/light/system theme
    toggle_theme: Callable[[], None] = field(default=_noop)
    # Check version.json for updates/announcements (notify_if_latest toasts)
    check_for_updates: Callable[..., Awaitable[None]] = field(
        default=_noop_async_check_for_updates
    )
    # Open the version dialog (changelog when up to date, update UI otherwise)
    open_version_dialog: Callable[[], None] = field(default=_noop)


ControllerMethodsCtx = ft.create_context(ControllerMethods())

__all__ = ["ControllerMethods", "ControllerMethodsCtx"]

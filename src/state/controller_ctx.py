"""Controller context — exposes AppController callbacks to the component tree.

Components read controller methods via ``ft.use_context(ControllerMethodsCtx)``
to trigger navigation, session opening, theme toggles, etc.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import flet as ft


def _noop(*_args, **_kwargs) -> None:
    """No-op sync default."""


@dataclass
class ControllerMethods:
    """Callbacks from AppController exposed to the component tree."""

    navigate_tab: Callable[[int], None] = field(default=_noop)
    open_history: Callable[[], None] = field(default=_noop)
    close_fullscreen: Callable[[], None] = field(default=_noop)
    open_session: Callable[[str, str], None] = field(default=_noop)
    close_session: Callable[[], None] = field(default=_noop)
    show_snack: Callable[[str], None] = field(default=_noop)
    show_new_session_sheet: Callable[[str], None] = field(default=_noop)
    toggle_theme: Callable[[], None] = field(default=_noop)


ControllerMethodsCtx = ft.create_context(ControllerMethods())

__all__ = ["ControllerMethods", "ControllerMethodsCtx"]

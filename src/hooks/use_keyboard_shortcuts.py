"""use_keyboard_shortcuts — install a page-level shortcut dispatcher on mount.

Ported from the proven KTV Player pattern: page.on_keyboard_event is the
only Flet API that carries modifier flags (shift/ctrl/alt/meta) and it is a
single-slot event, so this hook:

* saves the previously-installed handler and chains to it for unmatched keys,
* returns a cleanup that restores the previous handler on unmount, preventing
  handler nesting across remounts,
* resolves actions through the shared ``shortcuts_router`` so screen contexts
  can register/unregister bindings as they mount and unmount.

Registered once from AppShell.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from core.shortcuts import ShortcutRouter

__all__ = ["use_keyboard_shortcuts"]


def use_keyboard_shortcuts(router: ShortcutRouter) -> None:
    def _install() -> Callable[[], None]:
        from flet import context as _ctx

        try:
            page = _ctx.page
        except Exception:
            return lambda: None

        previous = page.on_keyboard_event

        async def _handler(e: ft.KeyboardEvent) -> None:
            action = router.resolve(e)
            if action is not None:
                result = action()
                if hasattr(result, "__await__"):
                    await result
                return
            if previous is not None:
                result = previous(e)
                if hasattr(result, "__await__"):
                    await result

        page.on_keyboard_event = _handler

        def _cleanup() -> None:
            page.on_keyboard_event = previous

        return _cleanup

    ft.on_mounted(_install)

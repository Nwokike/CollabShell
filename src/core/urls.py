"""URL launching — one registered service, not one per click.

A transient `ft.UrlLauncher()` auto-registers a new service on the
current page every time it is constructed; on mobile the last one can
take the channel and earlier calls land on a dead handler, so external
links silently fail. One shared, registered instance fixes all of it.
"""

from __future__ import annotations

import flet as ft

_launcher: ft.UrlLauncher | None = None


def get_url_launcher() -> ft.UrlLauncher:
    """Return the shared URL launcher, creating it inside a page context."""
    global _launcher
    if _launcher is None:
        _launcher = ft.UrlLauncher()
    return _launcher


__all__ = ["get_url_launcher"]

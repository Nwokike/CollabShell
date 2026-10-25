"""Compute-usage chip for the app header.

The owner's compute-unit balance, as one small read-only pill beside the
assistant credit chip. Both numbers used to sit under the signed-in chip on the
Home page, where a stack of chips read as the page's own content rather than
status — DDGS puts its credit pill in the header instead
(`screens/home_screen.py:612`).

The loader is the shared 24h cache (`services.usage_cache.get_usage_cached`)
the Settings card already uses, so both surfaces report the same number without
a second fetch. Loads in an effect; the value is written to observable state and
the chip rebuilds from it, the way every async value in this app is handled.
"""

from __future__ import annotations

import logging

import flet as ft

from core import tokens
from state import ServiceCtx

logger = logging.getLogger("UsageChip")


@ft.component
def UsageChip() -> ft.Container:
    """One small pill: the compute-unit balance, or nothing when unsigned."""
    services = ft.use_context(ServiceCtx)
    from core.state import state

    text, set_text = ft.use_state("")
    visible, set_visible = ft.use_state(False)

    async def _load():
        if not state.is_authenticated or not state.is_online:
            return
        try:
            from services.usage_cache import get_usage_cached

            usage = await get_usage_cached(services, state.auth_method)
        except Exception as ex:
            logger.warning("Usage chip load failed: %s", ex)
            return
        if usage is None:
            return
        set_text(f"{float(usage.get('balance', 0.0)):.2f} CU")
        set_visible(True)

    ft.use_effect(
        lambda: page_run_task(_load),
        [state.is_authenticated, state.is_online],
    )

    def page_run_task(coro_fn):
        try:
            page = ft.context.page
        except RuntimeError:
            return
        page.run_task(coro_fn)

    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Icon(
                    ft.Icons.DATA_USAGE_ROUNDED,
                    size=tokens.ICON_SM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Text(
                    text,
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            spacing=tokens.SPACE_XS,
        ),
        padding=ft.Padding(tokens.SPACE_SM, 2, tokens.SPACE_SM, 2),
        border_radius=tokens.RADIUS_SM,
        bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE_VARIANT),
        tooltip="Compute-unit balance — tap for details",
        visible=visible,
        on_click=lambda e: _open_usage_settings(),
    )


def _open_usage_settings():
    """Navigate to the Settings tab, where the full usage card lives."""
    from core.state import state

    state.current_tab = 4

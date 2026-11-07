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

# The services bundle captured at the chip's last render, so the tap handler
# (outside the component context) can still reach colab/storage.
_SERVICES = None


@ft.component
def UsageChip() -> ft.Container:
    """One small pill: compute-unit balance + burn rate, or nothing when unsigned."""
    global _SERVICES
    services = ft.use_context(ServiceCtx)
    _SERVICES = services
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
        # Balance AND burn rate — the owner reads the rate in the header, not
        # just the remaining balance.
        balance = float(usage.get("balance", 0.0))
        rate = float(usage.get("rate", 0.0))
        set_text(f"{balance:.2f} CU · {rate:.2f}/hr")
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
        tooltip="Compute units: balance · burn rate — tap for details",
        visible=visible,
        on_click=lambda e: show_usage_dialog(),
    )


def show_usage_dialog() -> None:
    """The header chip's tap target: a modal with the full usage readout.

    Mirrors the credit-balance wallet modal's shape (AlertDialog + rows +
    refresh), showing the same numbers the Settings → Account usage card
    shows — the Settings card itself stays put; this is a second view of it.
    """
    import flet as ft

    from core import tokens
    from core.state import state

    try:
        page = ft.context.page
    except RuntimeError:
        return
    # Captured at the chip's render (a click handler is outside the component
    # context, so use_context is not available there).
    services = _SERVICES

    rows_box = ft.Column(spacing=tokens.SPACE_XS, tight=True)
    updated_text = ft.Text("", size=tokens.FONT_XS, color=ft.Colors.ON_SURFACE_VARIANT)
    refresh_btn = ft.OutlinedButton(
        "Refresh", icon=ft.Icons.REFRESH_ROUNDED, disabled=True
    )

    async def _load(force: bool = False):
        refresh_btn.disabled = True
        try:
            refresh_btn.update()
        except Exception:
            pass
        try:
            if force:
                from services.colab.usage_ops import get_usage_impl

                usage = await get_usage_impl(
                    services.colab, state.auth_method
                ) if services is not None else None
            else:
                from services.usage_cache import get_usage_cached

                usage = (
                    await get_usage_cached(services, state.auth_method)
                    if services is not None
                    else None
                )
        except Exception as ex:
            logger.warning("Usage dialog load failed: %s", ex)
            usage = None
        if usage is None:
            rows_box.controls = [
                ft.Text("Usage unavailable right now.", size=tokens.FONT_SM)
            ]
        else:
            from screens.settings.account_section import format_usage_values

            rows, needs_free_copy = format_usage_values(usage)
            controls = [
                ft.Row(
                    controls=[
                        ft.Text(label, size=tokens.FONT_SM),
                        ft.Text(
                            value,
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.W_600,
                            expand=True,
                            text_align=ft.TextAlign.RIGHT,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                )
                for label, value in rows
            ]
            if needs_free_copy:
                from screens.settings.account_section import free_tier_copy

                controls.append(
                    ft.Text(
                        free_tier_copy(),
                        size=tokens.FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    )
                )
            rows_box.controls = controls
        if usage:
            # Reuse the Settings card's age-in-words formatter on the fetch time.
            from screens.settings.account_section import _format_updated

            updated_text.value = _format_updated(
                {"updated_at": str(usage.get("fetched_at") or "")}
            )
        else:
            updated_text.value = ""
        refresh_btn.disabled = False
        try:
            rows_box.update()
            updated_text.update()
            refresh_btn.update()
        except Exception:
            pass

    refresh_btn.on_click = lambda e: page.run_task(_load, True)

    page.show_dialog(
        ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [
                    ft.Icon(ft.Icons.DATA_USAGE_ROUNDED, size=tokens.ICON_SM),
                    ft.Text("Compute units", size=tokens.FONT_MD, weight=ft.FontWeight.W_700),
                ],
                spacing=tokens.SPACE_SM,
            ),
            content=ft.Container(
                content=ft.Column(
                    controls=[rows_box, updated_text],
                    spacing=tokens.SPACE_SM,
                    tight=True,
                ),
                width=340,
            ),
            actions=[
                refresh_btn,
                ft.TextButton("Close", on_click=lambda e: page.pop_dialog()),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
    )
    page.run_task(_load)

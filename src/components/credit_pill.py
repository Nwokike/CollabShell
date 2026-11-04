"""Credit pill — the assistant balance, always visible and one tap from help.

A `@ft.component` so it tracks `state.is_premium` and `state.credits_revision`
without the Home screen rebuilding. Colours and copy mirror DDGS's
`build_credit_pill` (components/wallet.py:33-59), which is the pattern the
owner already ships.

The balance lives on the async CreditService, so it is loaded in an effect and
re-loaded whenever a metered turn bumps the revision.
"""

from __future__ import annotations

import flet as ft

from components.wallet_dialog import show_wallet_dialog
from core import tokens
from core.theme import AppColors
from state import AppStateCtx, ServiceCtx


def credit_color(balance: int):
    """Green when comfortable, amber near the wall, red at it."""
    if balance > 20:
        return AppColors.SUCCESS
    if balance >= 5:
        return AppColors.WARNING
    return AppColors.ERROR


def build_credit_pill(
    page: ft.Page, balance: int, state=None, services=None
) -> ft.Container:
    """The plain (non-reactive) pill, for callers that already hold a number.

    ``state``/``services`` are only needed for the tap target (the wallet
    dialog); pass them when the pill should be tappable.
    """
    color = credit_color(balance)
    on_click = None
    if state is not None and services is not None:
        on_click = lambda e: show_wallet_dialog(page, state, services)
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(
                    tokens.ASSISTANT_ICON,
                    size=tokens.ICON_SM,
                    color=color,
                ),
                ft.Text(
                    str(balance),
                    size=tokens.FONT_SM,
                    weight=ft.FontWeight.W_600,
                    color=color,
                ),
            ],
            spacing=4,
            tight=True,
        ),
        padding=ft.Padding(8, 4, 10, 4),
        border_radius=tokens.RADIUS_PILL,
        bgcolor=ft.Colors.with_opacity(0.12, color),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.25, color)),
        ink=True,
        tooltip="Assistant credits, tap for details",
        on_click=on_click,
    )


@ft.component
def CreditPill() -> ft.Control:
    """Reactive credit pill for the home header."""
    state = ft.use_context(AppStateCtx)
    services = ft.use_context(ServiceCtx)
    page = ft.context.page

    balance, set_balance = ft.use_state(0)
    revision = getattr(state, "credits_revision", 0)
    is_premium = getattr(state, "is_premium", False)

    async def _load():
        credits = getattr(services, "credits", None)
        if credits is None:
            return
        try:
            set_balance(await credits.get_balance(is_premium=bool(is_premium)))
        except Exception:
            # A failed read must not blank the header; keep the last number.
            pass

    ft.use_effect(lambda: page.run_task(_load), [revision, is_premium])

    return build_credit_pill(page, balance, state, services)

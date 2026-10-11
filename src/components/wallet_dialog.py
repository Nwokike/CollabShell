"""Wallet dialog — credits balance, ad top-up, and the premium upsell.

One dialog, three states, mirroring DDGS's proven shape: balance, what a
credit buys, and the way to get more. The ad top-up is mobile-only because
flet-ads raises on desktop/web — the same gate the rest of the app uses.
"""

from __future__ import annotations

import logging

import flet as ft

from core import tokens
from core.styles import tip_text

logger = logging.getLogger("WalletDialog")

AD_TOPUP_CREDITS = 2
AD_TOPUP_COOLDOWN_SEC = 30.0


def show_wallet_dialog(page: ft.Page, state, services) -> None:
    credits = getattr(services, "credits", None)
    ad_service = getattr(services, "ad_service", None)

    is_premium = bool(getattr(state, "is_premium", False))
    cap = 500 if is_premium else 50

    async def _balance_async() -> int:
        if credits is None:
            return 0
        try:
            return await credits.get_balance(is_premium=is_premium)
        except Exception:
            return 0

    balance_text = ft.Text(
        "Loading credits…",
        size=tokens.FONT_MD,
        weight=ft.FontWeight.W_600,
        selectable=True,
    )

    async def _refresh_async():
        balance_text.value = f"{await _balance_async()} of {cap} credits left today"
        try:
            page.update()
        except Exception as ex:
            logger.warning("Wallet refresh failed: %s", ex)

    def _refresh():
        page.run_task(_refresh_async)

    def _open_premium(ev=None):
        page.pop_dialog()
        # Deep-link the user to the settings screen's premium row rather than
        # nesting a second dialog.
        controller = getattr(state, "controller", None)
        if controller is not None and hasattr(controller, "navigate_tab"):
            try:
                controller.navigate_tab(4)
            except Exception:
                logger.warning("Could not navigate to settings")
        page.update()

    async def _watch_ad(ev=None):
        if ad_service is None or credits is None:
            return
        granted = {"ok": False}

        def _on_reward(_ok=True):
            # AdService calls this with no argument on the desktop/no-ads
            # path (ad_service.py:190-196), so the parameter must be optional.
            granted["ok"] = bool(_ok)

        try:
            await ad_service.show_rewarded_interstitial(_on_reward)
        except Exception as ex:
            logger.warning("Rewarded ad failed: %s", ex)
        if granted["ok"]:

            await credits.add_credits(AD_TOPUP_CREDITS, is_premium=is_premium)
            _refresh()
        page.update()

    def _ads_available() -> bool:
        if ad_service is None or is_premium:
            return False
        probe = getattr(ad_service, "_is_mobile", None)
        # It is a method, not a property: a truthy bound method here made
        # desktop offer an ad top-up it cannot show.
        return bool(probe() if callable(probe) else probe)

    can_ads = _ads_available()

    page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Assistant credits"),
            content=ft.Column(
                controls=[
                    balance_text,
                    tip_text("Resets at 00:00 UTC. Yesterday's unused credits do "
                             "not roll over."),
                    ft.Divider(height=tokens.SPACE_SM),
                    ft.Text(
                        "One assistant step costs 1 credit — each reply, and "
                        "each tool call the assistant makes.",
                        size=tokens.FONT_SM,
                    ),
                    ft.Divider(height=tokens.SPACE_SM),
                    tip_text("Searching, uploading files, and everything else in "
                             "the app stays free."),
                ],
                spacing=tokens.SPACE_XS,
                tight=True,
            ),
            actions=[
                ft.TextButton("Close", on_click=lambda ev: page.pop_dialog()),
                *(
                    [
                        ft.FilledButton(
                            f"Watch Ad (+{AD_TOPUP_CREDITS})",
                            on_click=lambda ev: page.run_task(_watch_ad),
                        )
                    ]
                    if can_ads
                    else [
                        ft.FilledButton(
                            "Get 500 credits a day",
                            on_click=lambda ev: _open_premium(),
                        )
                    ]
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
    )
    # Populate the balance now that the dialog exists.
    _refresh()

"""Wallet dialog — credits balance, ad top-up, and the premium upsell.

One dialog, three states, mirroring DDGS's proven shape: balance, what a
credit buys, and the way to get more. The ad top-up is mobile-only because
flet-ads raises on desktop/web — the same gate the rest of the app uses.
"""

from __future__ import annotations

import asyncio
import logging
import time

import flet as ft

from core import tokens
from core.channel import CHANNEL
from core.constants import AD_TOPUP_COOLDOWN_SEC, AD_TOPUP_CREDITS
from core.styles import tip_text

logger = logging.getLogger("WalletDialog")


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

    cooldown_label = ft.Text(
        "",
        size=tokens.FONT_SM,
        color=ft.Colors.ON_SURFACE_VARIANT,
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
        """Deep-link to the Settings tab, where the PREMIUM card lives."""
        from core.state import state as app_state

        page.pop_dialog()
        app_state.current_tab = 4
        try:
            page.route = "/settings"
        except Exception:
            logger.debug("route write skipped", exc_info=True)
        page.update()

    def _watch_content(label: str) -> ft.Row:
        return ft.Row(
            controls=[
                ft.Icon(ft.Icons.PLAY_CIRCLE_ROUNDED, size=tokens.ICON_SM),
                ft.Text(label, size=tokens.FONT_SM, weight=ft.FontWeight.W_500),
            ],
            spacing=tokens.SPACE_XS,
            alignment=ft.MainAxisAlignment.CENTER,
        )

    topup_label = f"Watch Ad (+{AD_TOPUP_CREDITS})"

    watch_btn = ft.FilledButton(
        content=_watch_content(topup_label),
        disabled=is_premium,
    )

    dialog_open = True

    def _close(e=None):
        nonlocal dialog_open
        dialog_open = False
        try:
            page.pop_dialog()
        except Exception:
            pass

    async def _countdown():
        while dialog_open:
            remaining = int(state.ad_cooldown_end - time.time())
            # Read live: the local above was captured when the dialog was
            # built, so a purchase made while it was open kept counting down
            # against a verdict that had already changed.
            if state.is_premium:
                break
            if remaining > 0:
                watch_btn.disabled = True
                watch_btn.content = _watch_content(f"Cooldown ({remaining}s)")
            else:
                watch_btn.disabled = False
                watch_btn.content = _watch_content(topup_label)
            try:
                watch_btn.update()
            except Exception:
                return
            if remaining <= 0:
                break
            await asyncio.sleep(0.5)

    async def _on_watch_success():
        new_balance = await credits.add_credits(AD_TOPUP_CREDITS, is_premium=is_premium)
        state.credits_remaining = new_balance
        balance_text.value = f"{new_balance} of {cap} credits left today"
        cooldown_label.value = f"+{AD_TOPUP_CREDITS} credits added!"
        try:
            balance_text.update()
            cooldown_label.update()
        except Exception:
            pass

    async def _on_watch(e):
        if state.is_premium:
            return
        now = time.time()
        if state.ad_cooldown_end > now:
            cooldown_label.value = f"Wait {int(state.ad_cooldown_end - now)}s."
            try:
                cooldown_label.update()
            except Exception:
                pass
            return
        state.ad_cooldown_end = now + AD_TOPUP_COOLDOWN_SEC
        watch_btn.disabled = True
        try:
            watch_btn.update()
        except Exception:
            pass
        page.run_task(_countdown)

        granted = {"ok": False}

        def _on_reward(_ok=True):
            granted["ok"] = bool(_ok)

        try:
            await ad_service.show_rewarded_interstitial(_on_reward)
        except Exception as ex:
            logger.warning("Rewarded ad failed: %s", ex)
        if granted["ok"]:
            await _on_watch_success()
        else:
            # Nothing was shown, so nothing was earned and nothing should
            # be locked out: hand the button straight back.
            state.ad_cooldown_end = 0.0
            watch_btn.disabled = False
            cooldown_label.value = "Ads are not available right now."
            try:
                watch_btn.update()
                cooldown_label.update()
            except Exception:
                pass

    def _ads_available() -> bool:
        if ad_service is None or is_premium:
            return False
        probe = getattr(ad_service, "_is_mobile", None)
        # It is a method, not a property: a truthy bound method here made
        # desktop offer an ad top-up it cannot show.
        return bool(probe() if callable(probe) else probe)

    can_ads = _ads_available()

    watch_btn.on_click = lambda e: page.run_task(_on_watch, e)

    page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Assistant credits"),
            content=ft.Column(
                controls=[
                    balance_text,
                    tip_text(
                        "Resets at 00:00 UTC. Yesterday's unused credits do "
                        "not roll over."
                    ),
                    ft.Divider(height=tokens.SPACE_SM),
                    ft.Text(
                        "One assistant step costs 1 credit — each reply, and "
                        "each tool call the assistant makes.",
                        size=tokens.FONT_SM,
                    ),
                    ft.Divider(height=tokens.SPACE_SM),
                    tip_text(
                        "Searching, uploading files, and everything else in "
                        "the app stays free."
                    ),
                    cooldown_label,
                ],
                spacing=tokens.SPACE_XS,
                tight=True,
            ),
            actions=[
                ft.TextButton("Close", on_click=lambda ev: page.pop_dialog()),
                *(
                    [
                        watch_btn,
                    ]
                    if can_ads
                    else [
                        ft.FilledButton(
                            "Get 500 credits a day",
                            on_click=lambda ev: _open_premium(),
                        )
                    ]
                    if CHANNEL != "play"
                    # The Play build has no premium of any kind — no ad exists
                    # there either (Play Billing is a separate channel this
                    # build does not use), so the dialog's only action is
                    # Close. Never a purchase surface in a Play-distributed
                    # build: ktv-player's rule, DDGS's rule.
                    else []
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
    )
    # Populate the balance now that the dialog exists.
    _refresh()
    # The cooldown loop only has anything to update when the ad button is
    # actually on screen.
    if not is_premium and can_ads:
        page.run_task(_countdown)

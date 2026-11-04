"""Wallet dialog — balance, cost table, ad top-up (cooldown) and upsell.

A verbatim copy of DDGS's proven wallet (src/components/wallet.py), adapted
only for CollabShell's names. The ad top-up exists ONLY where an ad can
actually play (native mobile, non-premium), credits enter ONLY on the close
of an ad that actually opened, and the cooldown runs a live 0.5s countdown
that reads state fresh every tick.
"""

from __future__ import annotations

import asyncio
import logging
import time

import flet as ft

from core import tokens
from core.channel import CHANNEL
from core.constants import (
    AD_TOPUP_COOLDOWN_SEC,
    AD_TOPUP_CREDITS,
    COST_STEP,
    DAILY_FREE_CREDITS,
    DAILY_PREMIUM_CREDITS,
)
from core.styles import tip_text
from core.theme import AppColors
from services.ai_credits import credit_word

logger = logging.getLogger("WalletDialog")


def _credit_color(credits: int) -> str:
    if credits > 20:
        return AppColors.SUCCESS
    if credits >= 5:
        return AppColors.WARNING
    return AppColors.ERROR


def _row(
    icon: ft.IconData, title: str, subtitle: str, trailing: ft.Control
) -> ft.Container:
    """The wallet row shape — DDGS's setting_row."""
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(icon, size=tokens.ICON_SM, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Column(
                    [
                        ft.Text(title, size=tokens.FONT_SM, weight=ft.FontWeight.W_600),
                        ft.Text(
                            subtitle,
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    spacing=1,
                    tight=True,
                    expand=True,
                ),
                trailing,
            ],
            spacing=tokens.SM_SPACE_SM if hasattr(tokens, "SM_SPACE_SM") else 10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(0, 4, 0, 4),
    )


def show_wallet_dialog(page: ft.Page, state, services) -> None:
    """Balance, cost table, ad top-up (30s cooldown) and the premium upsell.

    DDGS's flow verbatim: the top-up row exists only where an ad can play,
    the cooldown is stamped the moment the button is pressed and handed
    straight back when no ad was shown, and credits enter only through the
    close of an ad that actually opened.
    """
    credits = getattr(services, "credits", None)
    ad_service = getattr(state, "ad_service", None) or getattr(
        services, "ad_service", None
    )

    if not hasattr(state, "ad_cooldown_end"):
        state.ad_cooldown_end = 0.0

    ads_available = False
    if ad_service is not None:
        probe = getattr(ad_service, "_is_mobile", None)
        # A method on the real service, a bool on stubs: handle both.
        ads_available = bool(probe() if callable(probe) else probe)
    is_premium = bool(getattr(state, "is_premium", False))
    cap = DAILY_PREMIUM_CREDITS if is_premium else DAILY_FREE_CREDITS

    def _credits():
        return credits

    async def _balance_async() -> int:
        if credits is None:
            return 0
        try:
            return await credits.get_balance(is_premium=is_premium)
        except Exception:
            return 0

    balance_value = 0

    balance_text = ft.Text(
        "…",
        size=tokens.FONT_MD,
        weight=ft.FontWeight.W_700,
        color=_credit_color(balance_value),
        selectable=True,
    )

    cooldown_label = ft.Text(
        "",
        size=tokens.FONT_SM,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )

    def _refresh_color():
        balance_text.color = _credit_color(balance_value)

    async def _refresh_async():
        nonlocal balance_value
        balance_value = await _balance_async()
        balance_text.value = (
            f"{balance_value} of {cap} credits left today · resets 00:00 UTC"
        )
        _refresh_color()
        try:
            page.update()
        except Exception as ex:
            logger.debug("wallet refresh skipped: %s", ex)

    def _refresh():
        page.run_task(_refresh_async)

    def _open_premium(ev=None):
        """Desktop has no ads to watch: send the user to the Premium card."""
        from core.state import state as app_state

        page.pop_dialog()
        app_state.current_tab = 4
        try:
            page.route = "/settings"
        except Exception:
            logger.debug("route write skipped", exc_info=True)
        page.update()

    def _close(e=None):
        nonlocal dialog_open
        dialog_open = False
        try:
            page.pop_dialog()
        except Exception:
            pass

    def _watch_content(text: str) -> ft.Row:
        """The button's one shape; only its label changes state."""
        return ft.Row(
            [
                ft.Icon(
                    ft.Icons.PLAY_CIRCLE_ROUNDED,
                    size=tokens.ICON_SM,
                    color=ft.Colors.WHITE,
                ),
                ft.Text(text, size=tokens.FONT_SM, color=ft.Colors.WHITE),
            ],
            spacing=6,
            tight=True,
        )

    topup_label = f"Watch Ad (+{AD_TOPUP_CREDITS} Credits)"

    watch_btn = ft.FilledButton(
        content=_watch_content(topup_label),
        bgcolor=AppColors.DARK_PRIMARY,
        disabled=is_premium,
    )

    dialog_open = True

    async def _countdown():
        while dialog_open:
            remaining = int(state.ad_cooldown_end - time.time())
            # Read live: a purchase made while the dialog is open must not
            # keep counting down against a verdict that already changed.
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
        new_balance = await _credits().add_credits(
            AD_TOPUP_CREDITS, is_premium=is_premium
        )
        state.credits_remaining = new_balance
        # The chat header pill is imperative: poke it or the balance behind
        # this dialog stays stale until the next chat render.
        chat = getattr(page, "_assistant_session", None)
        refresh = getattr(chat, "_refresh_credits", None)
        if callable(refresh):
            try:
                refresh()
            except Exception:
                pass
        balance_text.value = f"{new_balance} of {cap} credits left today"
        balance_text.color = _credit_color(new_balance)
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
        # Stamp the cooldown BEFORE the ad: a double-press can never queue
        # two ads (or two rewards).
        state.ad_cooldown_end = now + AD_TOPUP_COOLDOWN_SEC
        watch_btn.disabled = True
        try:
            watch_btn.update()
        except Exception:
            pass
        page.run_task(_countdown)

        from services.ad_service import AdService

        svc = ad_service or AdService(page)
        ok = await svc.show_rewarded_interstitial(_on_watch_success)
        if not ok:
            # Nothing was shown, so nothing was earned and nothing should be
            # locked out: hand the button straight back.
            state.ad_cooldown_end = 0.0
            watch_btn.disabled = False
            cooldown_label.value = "Ads are not available right now."
            try:
                watch_btn.update()
                cooldown_label.update()
            except Exception:
                pass

    watch_btn.on_click = lambda e: page.run_task(_on_watch, e)

    rows: list[ft.Control] = [
        _row(
            ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED,
            "Assistant credits",
            f"of {DAILY_PREMIUM_CREDITS if is_premium else DAILY_FREE_CREDITS} "
            "daily · resets 00:00 UTC",
            balance_text,
        ),
        ft.Divider(height=1, thickness=1, color=ft.Colors.with_opacity(0.18, ft.Colors.OUTLINE)),
        _row(
            ft.Icons.BOLT_ROUNDED,
            "Assistant model step",
            "Each reply and tool call",
            ft.Text(
                credit_word(COST_STEP),
                size=tokens.FONT_SM,
                weight=ft.FontWeight.W_600,
                color=ft.Colors.PRIMARY,
            ),
        ),
        ft.Divider(height=1, thickness=1, color=ft.Colors.with_opacity(0.18, ft.Colors.OUTLINE)),
        _row(
            ft.Icons.MONEY_OFF_ROUNDED,
            "Searching, uploads, everything else",
            "No credits used",
            ft.Text(
                "Free",
                size=tokens.FONT_SM,
                weight=ft.FontWeight.W_600,
                color=AppColors.SUCCESS,
            ),
        ),
    ]

    # The watch-ad row exists only where an ad can play (native mobile) and
    # only while it earns something (not for premium).
    if ads_available and not is_premium:
        rows.extend(
            [
                ft.Divider(
                    height=1,
                    thickness=1,
                    color=ft.Colors.with_opacity(0.18, ft.Colors.OUTLINE),
                ),
                _row(
                    ft.Icons.PLAY_CIRCLE_ROUNDED,
                    topup_label,
                    "",
                    ft.Icon(
                        ft.Icons.PLAY_CIRCLE_ROUNDED,
                        size=tokens.ICON_SM,
                        color=ft.Colors.PRIMARY,
                    ),
                ),
            ]
        )

    if ads_available and not is_premium:
        actions: list[ft.Control] = [cooldown_label, watch_btn]
    elif not is_premium and CHANNEL != "play":
        # No ad exists here (desktop, web): offer the credits, never the words
        # "remove ads" — there are no ads to remove.
        actions = [
            ft.TextButton(
                f"Get {DAILY_PREMIUM_CREDITS} credits a day",
                icon=ft.Icons.WORKSPACE_PREMIUM_ROUNDED,
                on_click=lambda e: _open_premium(),
            )
        ]
    else:
        actions = []

    page.show_dialog(
        ft.AlertDialog(
            title=ft.Text("Assistant credits"),
            content=ft.Container(
                content=ft.Column(
                    [*rows, *actions, tip_text("Yesterday's unused credits do not roll over.")],
                    spacing=tokens.SPACE_XS,
                    tight=True,
                ),
                width=340,
                padding=ft.Padding(4, 8, 4, 4),
            ),
            actions=[ft.TextButton("Close", on_click=_close)],
            actions_alignment=ft.MainAxisAlignment.END,
        )
    )
    # Populate the balance now that the dialog exists.
    _refresh()
    # The cooldown loop only has anything to update when the ad button is
    # actually on screen.
    if not is_premium and ads_available:
        page.run_task(_countdown)

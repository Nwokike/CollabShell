"""AI credit pill + wallet dialog — copied verbatim from DDGS's wallet.py.

The only adaptations are CollabShell's plumbing: the dialog takes
(page, state, services), credits come from services.credits, the pill refresh
goes through page._assistant_session._refresh_credits, and the premium
deep-link sets the shell route instead of DDGS's controller attribute.
Everything else — rows, copy, cooldown, countdown, grant path — is DDGS's.
"""

from __future__ import annotations

import asyncio
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
from core.theme import AppColors
from services.ai_credits import credit_word


def _credit_color(credits: int) -> str:
    if credits > 20:
        return AppColors.SUCCESS
    if credits >= 5:
        return AppColors.WARNING
    return AppColors.ERROR


def _row(
    icon: ft.IconData,
    title: str,
    subtitle: str,
    trailing: ft.Control,
) -> ft.Container:
    """Wallet row; the shape lives in DDGS's core.ui.setting_row."""
    icon_box = ft.Container(
        content=ft.Icon(
            icon,
            size=tokens.ICON_MD,
            color=ft.Colors.ON_SURFACE_VARIANT,
        ),
        width=tokens.ICON_BOX if hasattr(tokens, "ICON_BOX") else 36,
        height=tokens.ICON_BOX if hasattr(tokens, "ICON_BOX") else 36,
        border_radius=tokens.ICON_BOX_RADIUS if hasattr(tokens, "ICON_BOX_RADIUS") else 8,
        bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE),
        alignment=ft.Alignment.CENTER,
    )
    return ft.Container(
        content=ft.Row(
            [
                icon_box,
                ft.Column(
                    [
                        ft.Text(
                            title, size=tokens.FONT_SM, weight=ft.FontWeight.W_600
                        ),
                        ft.Text(
                            subtitle,
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            max_lines=3,
                        ),
                    ],
                    spacing=1,
                    tight=True,
                    expand=True,
                ),
                trailing,
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(0, 4, 0, 4),
    )


def _cost_row(label: str, cost: str) -> ft.Container:
    if cost == "free":
        return _row(
            ft.Icons.MONEY_OFF_ROUNDED,
            label,
            "No credits used",
            ft.Text(
                "Free",
                size=tokens.FONT_SM,
                weight=ft.FontWeight.W_600,
                color=AppColors.SUCCESS,
            ),
        )
    return _row(
        ft.Icons.BOLT_ROUNDED,
        label,
        "Each reply and tool call",
        ft.Text(
            str(cost),
            size=tokens.FONT_SM,
            weight=ft.FontWeight.W_600,
            color=ft.Colors.PRIMARY,
        ),
    )


def show_wallet_dialog(page: ft.Page, state, services) -> None:
    """Balance, cost table, ad top-up (30s cooldown) and the premium upsell.

    DDGS verbatim: the top-up row and button render exactly where an ad can
    actually play, never as a dead affordance.
    """
    if not hasattr(state, "ad_cooldown_end"):
        state.ad_cooldown_end = 0.0

    # Ads exist only in native mobile builds: flet-ads raises on web and on
    # desktop, so the top-up row and button render exactly where an ad can
    # actually play (single source: ad_service).
    ad_service = getattr(state, "ad_service", None) or getattr(
        services, "ad_service", None
    )
    probe = getattr(ad_service, "_is_mobile", None) if ad_service is not None else None
    ads_available = bool(ad_service) and bool(probe() if callable(probe) else probe)
    is_premium = bool(getattr(state, "is_premium", False))
    credits = getattr(services, "credits", None)

    def _credits():
        return credits

    balance_text = ft.Text(
        str(getattr(state, "credits_remaining", 0)),
        size=tokens.FONT_XL,
        weight=ft.FontWeight.BOLD,
        color=_credit_color(getattr(state, "credits_remaining", 0)),
    )
    cooldown_label = ft.Text("", size=tokens.FONT_XS, text_align=ft.TextAlign.CENTER)

    topup_label = f"Watch Ad (+{AD_TOPUP_CREDITS} Credits)"

    def _watch_content(text: str) -> ft.Control:
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

    watch_btn = ft.FilledButton(
        content=_watch_content(topup_label),
        bgcolor=ft.Colors.PRIMARY,
        disabled=is_premium,
    )

    dialog_open = True

    def _open_premium(e=None):
        """Desktop has no ads to watch: send the user to the Premium card."""
        _close()
        state.current_tab = 4
        try:
            page.route = "/settings"
        except Exception:
            pass
        page.update()

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
        new_balance = await _credits().add_credits(
            AD_TOPUP_CREDITS, is_premium=is_premium
        )
        state.credits_remaining = new_balance
        # The chat header is an imperative view, not a state subscriber:
        # poke its pill or the balance behind this dialog stays stale until
        # the next chat render.
        refresh = getattr(
            getattr(page, "_assistant_session", None), "_refresh_credits", None
        )
        if callable(refresh):
            try:
                refresh()
            except Exception:
                pass
        balance_text.value = str(new_balance)
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
        state.ad_cooldown_end = now + AD_TOPUP_COOLDOWN_SEC
        watch_btn.disabled = True
        try:
            watch_btn.update()
        except Exception:
            pass
        page.run_task(_countdown)
        from services.ad_service import AdService

        ad_service = getattr(state, "ad_service", None) or getattr(
            services, "ad_service", None
        ) or AdService(page)
        ok = await ad_service.show_rewarded_interstitial(_on_watch_success)
        if not ok:
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

    watch_btn.on_click = lambda e: page.run_task(_on_watch, e)

    rows: list[ft.Control] = [
        _row(
            ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED,
            "Assistant credits",
            f"of {DAILY_PREMIUM_CREDITS if is_premium else DAILY_FREE_CREDITS} "
            "daily · resets 00:00 UTC",
            balance_text,
        ),
        ft.Divider(
            height=1,
            thickness=1,
            color=ft.Colors.with_opacity(0.18, ft.Colors.OUTLINE),
        ),
        _cost_row("Assistant model step", credit_word(COST_STEP)),
        ft.Divider(
            height=1,
            thickness=1,
            color=ft.Colors.with_opacity(0.18, ft.Colors.OUTLINE),
        ),
        _cost_row("Everything else in the app", "free"),
    ]

    # The watch-ad row exists only where an ad can play (native mobile)
    # and only while it earns something (not for premium).
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
                        color=AppColors.DARK_PRIMARY,
                    ),
                ),
            ]
        )

    if ads_available and not is_premium:
        actions: list[ft.Control] = [cooldown_label, watch_btn]
    elif not is_premium and CHANNEL != "play":
        # No ad exists here (desktop, web): offer the credits, never the
        # words "remove ads" - there are no ads to remove.
        actions = [
            ft.TextButton(
                f"Get {DAILY_PREMIUM_CREDITS} credits a day",
                icon=ft.Icons.WORKSPACE_PREMIUM_ROUNDED,
                icon_color=ft.Colors.PRIMARY,
                on_click=lambda e: _open_premium(),
            )
        ]
    else:
        actions = []

    content = ft.Column(
        [
            *rows,
            *actions,
        ],
        spacing=tokens.SPACE_XS,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )

    dlg = ft.AlertDialog(
        title=ft.Text("Assistant credits", font_family="Outfit"),
        content=ft.Container(
            content=content, width=340, padding=ft.Padding(4, 8, 4, 4)
        ),
        actions=[ft.TextButton("Close", on_click=_close)],
    )
    page.show_dialog(dlg)
    # The cooldown loop only has anything to update when the ad button is
    # on screen.
    if not is_premium and ads_available:
        page.run_task(_countdown)

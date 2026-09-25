"""Premium settings — one backend: the Kiri License Worker.

KTV Player's model, adopted wholesale. Google Play Billing is not part of
this build: the Play Console in use has no Google Payments merchant
profile, so there is nothing to sell through it. The Play AAB is stamped
CHANNEL = "play" at build time and this whole screen reduces to the free
tier — no purchase rows of any kind. Direct APKs, desktop and web sell
through license.kiri.ng with no Google permission involved.
"""

from __future__ import annotations

import logging
import time

import flet as ft

from ai.credits import AD_CREDIT_REWARD, DAILY_CREDITS, PREMIUM_DAILY_CREDITS
from core import constants, tokens
from core.state import state
from core.styles import glass_card, section_header, tip_text
from core.theme import AppColors
from core.urls import get_url_launcher
from services import license_service as license

logger = logging.getLogger("PremiumSection")


def _row(icon, title, subtitle, trailing):
    return ft.Row(
        controls=[
            ft.Icon(icon, size=tokens.ICON_LG, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Column(
                controls=[
                    ft.Text(title, size=tokens.FONT_MD, weight=ft.FontWeight.W_500),
                    tip_text(subtitle),
                ],
                spacing=tokens.SPACE_XXS,
                expand=True,
            ),
            trailing,
        ],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=tokens.SPACE_LG,
    )


def _status_chip(text: str, color: str) -> ft.Control:
    return ft.Container(
        content=ft.Text(
            text,
            size=tokens.FONT_XS,
            color=color,
            weight=ft.FontWeight.W_600,
        ),
        padding=ft.Padding(
            tokens.SPACE_SM, tokens.SPACE_XXS, tokens.SPACE_SM, tokens.SPACE_XXS
        ),
        border_radius=tokens.RADIUS_SM,
        bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.ON_SURFACE),
    )


def build_premium_section(page: ft.Page, app_state, services) -> ft.Column:
    premium = services.premium
    ai = services.ai
    if premium is None:
        return ft.Column()

    async def _snack(message: str, is_error: bool = False):
        from core.notifications import show_notification

        show_notification(page, message, is_error=is_error)

    # ── Buy through the Kiri Worker (the only channel) ───────────────────

    async def _open_checkout(e=None):
        """Fetch the Worker's catalog first, then show a plain dialog.

        No hooks here: this runs from an event handler, where Flet has no
        renderer — the mistake that made the old version crash the moment
        it was tapped. Plain controls are safe anywhere.
        """
        if not license.is_available(page):
            return
        try:
            products = await license.get_catalog()
        except license.LicenseError as ex:
            await _snack(str(ex), is_error=True)
            return
        page.show_dialog(_checkout_dialog(page, services, products))

    async def _show_recovery(e=None):
        stored = await services.storage.get(constants.STORAGE_LICENSE_RECOVERY)
        if not stored:
            await _snack("No recovery ID yet — it appears after a purchase.")
            return
        await _snack(f"Your recovery ID is {stored}")

    async def _restore_license(e=None):
        """Redeem the saved recovery ID through the service (which stores
        and applies the entitlement, then re-renders the section)."""
        stored = await services.storage.get(constants.STORAGE_LICENSE_RECOVERY)
        if not stored:
            await _snack("No recovery ID saved on this device.", is_error=True)
            return
        try:
            entitlement = await premium.kiri_restore(str(stored))
        except license.LicenseError as ex:
            await _snack(str(ex), is_error=True)
            return
        if entitlement.grants_access:
            await _snack("Premium restored.")
        else:
            await _snack(f"That license is {entitlement.status}.", is_error=True)
        page.update()

    async def _check_status(e=None):
        """Manual re-check, like KTV's Settings action."""
        try:
            entitlement = await premium.kiri_check_status()
        except license.LicenseError as ex:
            await _snack(str(ex), is_error=True)
            return
        if entitlement is None:
            await _snack("No saved purchase to check.")
            return
        await _snack(
            "Premium is active." if entitlement.grants_access
            else f"That license is {entitlement.status}.",
            is_error=not entitlement.grants_access,
        )
        page.update()

    # ── Earn credits by watching an ad ──────────────────────────────────
    # SpanInsight's rule, adopted exactly: 2 credits per completed ad,
    # one ad at a time, 30 seconds between ads. The cooldown is stamped
    # BEFORE the ad opens, so no burst of taps can open a burst of ads —
    # the failure the owner hit on the phone.
    AD_COOLDOWN_SECONDS = 30.0

    async def _watch_ad(e=None, button: ft.TextButton | None = None):
        now = time.monotonic()
        if now < state.ad_cooldown_end:
            remaining = int(state.ad_cooldown_end - now) + 1
            await _snack(f"Next ad in {remaining}s.")
            return
        ad = services.ad_service
        if ad is None or ai is None or ai.ledger is None:
            return
        state.ad_cooldown_end = now + AD_COOLDOWN_SECONDS
        if button is not None:
            button.disabled = True
            page.update()

        async def _grant():
            await ai.ledger.add_bonus(AD_CREDIT_REWARD)
            ai.credits_left = await ai.ledger.remaining()
            await _snack(f"+{AD_CREDIT_REWARD} credits. Thanks for watching.")

        try:
            started = await ad.show_rewarded_interstitial(
                _grant, grant_on_fail=False
            )
            if not started:
                await _snack("No ad available right now — try again later.")
        finally:
            if button is not None:
                button.disabled = False
            page.update()

    # ── Build the rows ──────────────────────────────────────────────────
    # The Play AAB is a free-only build (CHANNEL = "play"): it sells
    # nothing and shows nothing to buy — its monetization is ads. Every
    # other build offers premium.
    from core.build_channel import CHANNEL

    play_build = CHANNEL == "play"
    controls: list[ft.Control] = []

    if not play_build and state.premium_status in ("expired", "revoked"):
        headline, detail = (
            (
                "Premium expired",
                "Your paid period ended. Renew to switch Premium back on.",
            )
            if state.premium_status == "expired"
            else (
                "Premium refunded",
                "A refund turned Premium off. Buy again any time.",
            )
        )
        controls.append(
            _row(
                ft.Icons.WORKSPACE_PREMIUM_ROUNDED,
                headline,
                detail,
                _status_chip(state.premium_status, AppColors.ERROR),
            )
        )
        controls.append(ft.Divider(height=tokens.SPACE_SM))

    if not play_build:
        if state.is_premium:
            source = "Kiri license"
            note = (
                f"Premium is on, through {source}."
                if not state.premium_offline
                else f"Premium is on, through {source}. Not confirmed by the "
                "server this session — you stay signed in either way."
            )
            if state.premium_status == "grace":
                # A recurring payment failed; the Worker grants a grace
                # window before expiry. Say so instead of showing "Active".
                note = (
                    "Payment overdue — finish your payment to keep Premium. "
                    "You still have full access for now."
                )
                controls.append(
                    _row(
                        ft.Icons.WORKSPACE_PREMIUM_ROUNDED,
                        "Payment overdue",
                        note,
                        _status_chip("Grace", AppColors.WARNING),
                    )
                )
            else:
                controls.append(
                    _row(
                        ft.Icons.WORKSPACE_PREMIUM_ROUNDED,
                        "Premium is on",
                        note,
                        _status_chip("Active", AppColors.SUCCESS),
                    )
                )
        else:
            controls.append(
                _row(
                    ft.Icons.WORKSPACE_PREMIUM_OUTLINED,
                    "Go Premium",
                    f"No ads, and {PREMIUM_DAILY_CREDITS} AI credits a day "
                    f"instead of {DAILY_CREDITS}.",
                    ft.TextButton(
                        "See options",
                        on_click=lambda e: page.run_task(_open_checkout, e),
                    ),
                )
            )

        # ── The Kiri License Worker — the only purchase channel ─────────
        # Reached on direct APKs, desktop and web alike. The Play AAB
        # never enters this branch at all.
        if license.is_available(page):
            controls.append(ft.Divider(height=tokens.SPACE_SM))
            controls.append(
                _row(
                    ft.Icons.CREDIT_CARD_ROUNDED,
                    "Pay directly",
                    "Card or mobile money, paid to Kiri — your recovery ID "
                    "is how you get back in if you clear app data.",
                    ft.TextButton(
                        "Buy", on_click=lambda e: page.run_task(_open_checkout, e)
                    ),
                )
            )
            controls.append(
                _row(
                    ft.Icons.VPN_KEY_ROUNDED,
                    "Recovery ID",
                    "Keep this somewhere safe. It is the only way back in "
                    "after a reinstall.",
                    ft.TextButton(
                        "Show", on_click=lambda e: page.run_task(_show_recovery, e)
                    ),
                )
            )
            controls.append(
                _row(
                    ft.Icons.RESTORE_ROUNDED,
                    "Restore a purchase",
                    "Enter the recovery ID from your receipt, or re-check "
                    "the one saved on this device.",
                    ft.Row(
                        controls=[
                            ft.TextButton(
                                "Restore",
                                on_click=lambda e: page.run_task(
                                    _restore_license, e
                                ),
                            ),
                            ft.TextButton(
                                "Check status",
                                on_click=lambda e: page.run_task(_check_status, e),
                            ),
                        ],
                        spacing=tokens.SPACE_SM,
                    ),
                )
            )
    # Credits: the visible benefit, with a way to earn more.
    if ai is not None:
        controls.append(ft.Divider(height=tokens.SPACE_SM))

        def _ad_button():
            # The reward only exists where ads exist: a desktop button
            # would grant credits with nothing watched (and no ad SDK).
            try:
                mobile = page.platform.is_mobile()
            except Exception:
                mobile = False
            if not mobile or services.ad_service is None or state.is_premium:
                return (
                    _status_chip("Premium", AppColors.WARNING)
                    if state.is_premium
                    else None
                )
            return ft.TextButton(
                f"+{AD_CREDIT_REWARD}",
                icon=ft.Icons.PLAY_CIRCLE_OUTLINE_ROUNDED,
                on_click=lambda e: page.run_task(_watch_ad, e, e.control),
            )

        controls.append(
            _row(
                ft.Icons.CONFIRMATION_NUMBER_ROUNDED,
                f"{ai.credits_left} AI credits",
                f"{DAILY_CREDITS} a day free, {PREMIUM_DAILY_CREDITS} with "
                f"Premium. Each model call uses 2; failed calls are refunded. "
                f"Credits from ads never expire.",
                _ad_button(),
            )
        )

    return ft.Column(
        controls=[
            section_header("PREMIUM"),
            glass_card(
                ft.Column(controls=controls, spacing=tokens.SPACE_SM),
                margin=ft.Margin(
                    tokens.SPACE_LG,
                    tokens.SPACE_XXS,
                    tokens.SPACE_LG,
                    tokens.SPACE_XXS,
                ),
            ),
        ],
        spacing=0,
    )


def _checkout_dialog(page, services, products) -> ft.Control:
    """Email + tier chooser for the direct (Worker) channel.

    `products` was fetched before this dialog was built — building UI in
    an event handler is fine as long as no Flet hooks are used.
    """
    email_field = ft.TextField(
        label="Email for your receipt",
        hint_text="you@example.com",
        keyboard_type=ft.KeyboardType.EMAIL,
        text_size=tokens.FONT_SM,
        dense=True,
    )
    error_text = ft.Text("", size=tokens.FONT_XS, color=AppColors.ERROR)
    tier = {"id": ""}  # pre-selected below from the catalog

    def _select(product_id: str, e=None):
        tier["id"] = product_id
        for pid, button in tier_buttons.items():
            selected = pid == product_id
            button.style = (
                ft.ButtonStyle(bgcolor=ft.Colors.with_opacity(0.16, ft.Colors.PRIMARY))
                if selected
                else None
            )
        page.update()

    async def _continue(e=None):
        if not license.valid_email(email_field.value or ""):
            error_text.value = "Enter a valid email address."
            page.update()
            return
        error_text.value = "Opening checkout…"
        page.update()
        try:
            checkout = await license.start_checkout(email_field.value or "", tier["id"])
        except license.LicenseError as ex:
            error_text.value = str(ex)
            page.update()
            return
        recovery = checkout.get("recovery_id") or ""
        # Save it before leaving the app: if the user never finishes, they
        # can still come back to this purchase.
        await services.storage.set(constants.STORAGE_LICENSE_RECOVERY, recovery)
        page.pop_dialog()
        await get_url_launcher().launch_url(checkout.get("checkout_url") or "")
        from core.notifications import show_notification

        show_notification(
            page,
            f"Recovery ID saved: {recovery}. Keep it safe — it is how you "
            "restore this purchase.",
        )

    tier_buttons: dict[str, ft.Button] = {}
    tier_rows: list[ft.Control] = []
    for product in products:
        interval = f"/{product.interval}" if product.interval else ""
        button = ft.TextButton(
            f"{product.label}{interval}",
            on_click=lambda e, pid=product.id: _select(pid, e),
        )
        tier_buttons[product.id] = button
        tier_rows.append(button)
    if not tier_rows:
        tier_rows.append(
            ft.Text(
                "Prices could not be loaded — try again shortly.",
                size=tokens.FONT_XS,
                color=AppColors.ERROR,
            )
        )
    # Pre-select the first tier so Continue always has a valid choice.
    if tier_buttons:
        first = next(iter(tier_buttons))
        tier["id"] = first
        tier_buttons[first].style = ft.ButtonStyle(
            bgcolor=ft.Colors.with_opacity(0.16, ft.Colors.PRIMARY)
        )

    return ft.AlertDialog(
        title=ft.Text("Pay directly"),
        content=ft.Column(
            controls=[
                ft.Text(
                    "Use this if Google Play payment does not work where you "
                    "are. Prices come from Kiri, not from the app.",
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                email_field,
                ft.Column(tier_rows, spacing=tokens.SPACE_XXS, tight=True),
                error_text,
            ],
            spacing=tokens.SPACE_SM,
            tight=True,
        ),
        actions=[
            ft.TextButton("Cancel", on_click=lambda e: page.pop_dialog()),
            ft.FilledButton("Continue", on_click=lambda e: page.run_task(_continue)),
        ],
    )


__all__ = ["build_premium_section"]

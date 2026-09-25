"""Premium settings — both payment channels, one honest screen.

CollabShell is on Google Play, so **Play Billing is the primary way to buy**
and gets the top of the screen. The Kiri License Worker is the **fallback
for users Google billing cannot serve** — regions where Play payment is not
offered, and desktop builds that have no Play Store at all.

Neither channel hides the other, and a user who bought through one is never
asked to buy again through the other. The copy says which channel is for
whom, because "two paywalls" is only confusing when nobody explains why
there are two.
"""

from __future__ import annotations

import logging

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

    # ── Buy through Play (the default channel) ──────────────────────────

    async def _buy_play(e=None):
        started = await premium.buy()
        if not started:
            await _snack(
                "Google Play could not start the purchase. If you are in a "
                "region where Play payment does not work, use the direct "
                "purchase below.",
                is_error=True,
            )
            return
        # The result arrives through the purchase stream; the UI updates
        # when state.is_premium flips.

    async def _restore_play(e=None):
        await premium.restore_purchases()
        await _snack("Checking Google Play for a previous purchase…")

    # ── Buy through the Kiri Worker (the fallback) ──────────────────────

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

    async def _enable_direct(e=None):
        """The user says Google Play payment does not work for them. Only
        now does the direct channel exist on this build — it is their
        choice, not an offer."""
        await license.save_opt_in(services.storage, True)
        license.set_available(page, True)
        await _snack("Direct purchase options unlocked below.")
        page.update()

    async def _restore_license(e=None):
        stored = await services.storage.get(constants.STORAGE_LICENSE_RECOVERY)
        if not stored:
            await _snack("No recovery ID saved on this device.", is_error=True)
            return
        try:
            entitlement = await license.restore(stored)
        except license.LicenseError as ex:
            await _snack(str(ex), is_error=True)
            return
        if await license.apply_entitlement(entitlement):
            await _snack("Premium restored.")
        else:
            await _snack(f"That license is {entitlement.status}.", is_error=True)
        page.update()

    # ── Earn credits by watching an ad ──────────────────────────────────

    async def _watch_ad(e=None):
        if ai is None:
            return
        ad = services.ad_service
        if ad is None:
            return
        done = {"value": False}

        async def _grant():
            if done["value"]:
                return
            done["value"] = True
            await ai.ledger.add_bonus(AD_CREDIT_REWARD)
            ai.credits_left = await ai.ledger.remaining()
            await _snack(f"+{AD_CREDIT_REWARD} credits. Thanks for watching.")
            page.update()

        await ad.show_rewarded_interstitial(_grant)

    # ── Build the rows ──────────────────────────────────────────────────

    controls: list[ft.Control] = []

    if state.is_premium:
        source = "Google Play" if state.premium_source == "play" else "Kiri license"
        note = (
            f"Premium is on, through {source}."
            if not state.premium_offline
            else f"Premium is on, through {source}. Not confirmed by the "
            "server this session — you stay signed in either way."
        )
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
                f"No ads, {PREMIUM_DAILY_CREDITS} AI credits a day instead of "
                f"{DAILY_CREDITS}, and unlimited chat history.",
                ft.TextButton("See options", on_click=lambda e: _open_checkout(e)),
            )
        )

    # Google Play is where most people should buy.
    if premium.available:
        controls.append(
            _row(
                ft.Icons.SHOPPING_CART_ROUNDED,
                "Buy with Google Play",
                "The normal way to buy. Your purchase is tied to your Play "
                "account and restores on any device you sign into.",
                ft.TextButton("Buy", on_click=lambda e: page.run_task(_buy_play, e)),
            )
        )
        controls.append(ft.Divider(height=tokens.SPACE_SM))
        controls.append(
            _row(
                ft.Icons.RESTORE_ROUNDED,
                "Restore from Google Play",
                "Already paid? This re-checks your Play account.",
                ft.TextButton(
                    "Restore", on_click=lambda e: page.run_task(_restore_play, e)
                ),
            )
        )

    # ── The direct channel, where it is allowed to exist ────────────────
    # Desktop and web have no Play Store, so this is their only way in. On
    # Android it stays out of the way until the user says Google Play
    # payment does not work for them: nobody is steered into it, and the
    # Play build carries no alternative payment to report.
    if license.is_available(page):
        controls.append(ft.Divider(height=tokens.SPACE_SM))
        controls.append(
            _row(
                ft.Icons.CREDIT_CARD_ROUNDED,
                "Pay directly",
                "Card or mobile money, paid to Kiri — your recovery ID is how "
                "you get back in if you clear app data.",
                ft.TextButton(
                    "Buy", on_click=lambda e: page.run_task(_open_checkout, e)
                ),
            )
        )
        controls.append(
            _row(
                ft.Icons.VPN_KEY_ROUNDED,
                "Recovery ID",
                "Keep this somewhere safe. It is the only way back in after "
                "a reinstall.",
                ft.TextButton(
                    "Show", on_click=lambda e: page.run_task(_show_recovery, e)
                ),
            )
        )
        controls.append(
            _row(
                ft.Icons.RESTORE_ROUNDED,
                "Restore a purchase",
                "Enter the recovery ID from your receipt.",
                ft.TextButton(
                    "Restore", on_click=lambda e: page.run_task(_restore_license, e)
                ),
            )
        )
    elif premium.available:
        # Android with Play Billing: the escape hatch exists for the user
        # who cannot pay through Google, and is reached by asking, never by
        # being offered.
        controls.append(ft.Divider(height=tokens.SPACE_SM))
        controls.append(
            _row(
                ft.Icons.HELP_OUTLINE_ROUNDED,
                "Google Play payment not working?",
                "In some regions and on some accounts, Google Play will not "
                "take the payment. You can choose to pay Kiri directly "
                "instead, with a card or mobile money.",
                ft.TextButton(
                    "Show options", on_click=lambda e: page.run_task(_enable_direct, e)
                ),
            )
        )

    # Credits: the visible benefit, with a way to earn more.
    if ai is not None:
        controls.append(ft.Divider(height=tokens.SPACE_SM))
        controls.append(
            _row(
                ft.Icons.CONFIRMATION_NUMBER_ROUNDED,
                f"{ai.credits_left} AI credits",
                f"{DAILY_CREDITS} a day free, {PREMIUM_DAILY_CREDITS} with "
                f"Premium. Each model call uses 2; failed calls are refunded. "
                f"Credits from ads never expire.",
                ft.TextButton(
                    f"+{AD_CREDIT_REWARD}",
                    icon=ft.Icons.PLAY_CIRCLE_OUTLINE_ROUNDED,
                    on_click=lambda e: page.run_task(_watch_ad, e),
                )
                if not state.is_premium
                else _status_chip("Premium", AppColors.WARNING),
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

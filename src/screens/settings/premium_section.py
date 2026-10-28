"""Settings → CollabShell Premium.

Rebuilt on DDGS's card (`components/settings/sections_premium.py`), which is
itself KTV Player's shape. One entitlement, four rows:

    status          what Premium is, or why it lapsed
    plans           monthly / yearly / lifetime, priced from the Worker
    recovery ID     the ID itself, with Copy
    Restore         re-check ownership (new device / reinstall)

and the typing happens in dialogs that only exist once you ask for one — a
settings card that lists every field it will ever need is a form, not a menu.

The card is BUILT from observable state (`state.license_prices`,
`state.license_recovery_id`, `state.is_premium`) on every render, so an
async load or an unlock repaints it through the observable notify. Nothing
mutates a control in place: `controls.clear()`/`append()` never set the dirty
flag (`flet/controls/value_types.py:57-77`) and the client can be left
showing an empty card.

On the Play channel the screen does not build this card at all (see
`screens/settings/__init__.py`) — not even an empty container, because "not
even a disabled card — nothing to declare, nothing to reach, ads stay on" is
the rule both reference apps state.
"""

from __future__ import annotations

import logging
import re

import flet as ft

from core import tokens
from core.channel import CHANNEL
from core.constants import DAILY_FREE_CREDITS, DAILY_PREMIUM_CREDITS
from core.notifications import show_notification
from core.styles import glass_card, section_header, tip_text

logger = logging.getLogger("PremiumSection")

EMAIL_RE = re.compile(r"^\S+@\S+\.\S+$")

# What a lapsed payment means, in the buyer's words. `status` comes off the
# signed token, so the copy can never disagree with the entitlement.
_STATUS_COPY = {
    "grace": ("Payment overdue", "Finish your payment to keep Premium"),
    "expired": ("Premium expired", "Renew to switch Premium back on"),
    "revoked": ("Premium refunded", "A refund turned Premium off"),
}

# The plans, in the order a buyer compares them. The price next to each is
# read from the Worker's catalog, never written here.
_PLANS = (
    ("monthly", "Renews monthly, cancel any time"),
    ("yearly", "Two months free versus monthly"),
    ("lifetime", "Pay once, keep it"),
)

_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


def page_has_ads(page, state, services) -> bool:
    """Whether an ad can actually appear on this build.

    The pitch says "Removes ads" only when it is true: desktop and web show
    no ad, so there the subtitle sells the credits alone.
    """
    ad_service = getattr(services, "ad_service", None)
    if ad_service is None:
        return False
    try:
        platform = getattr(page, "platform", None)
        if platform is None or not platform.is_mobile():
            return False
    except Exception:
        return False
    return True


def _paid_subtitle(claims, has_ads: bool) -> str:
    """Paid-row subtitle: the benefits plus the token's own dates."""
    base = (
        f"Ads removed · {DAILY_PREMIUM_CREDITS} credits a day"
        if has_ads
        else f"{DAILY_PREMIUM_CREDITS} credits a day"
    )
    expires_at = getattr(claims, "expires_at", None)
    if expires_at is None:
        return f"{base} · thank you!"
    product = str(getattr(claims, "product", "") or "")
    renewal = {"monthly": "renews monthly", "yearly": "renews yearly"}.get(
        product, "renews automatically"
    )
    try:
        import datetime

        when = datetime.datetime.fromtimestamp(
            int(expires_at), tz=datetime.UTC
        ).strftime("%d %b %Y")
    except TypeError, ValueError, OSError, OverflowError:
        return f"{base} · thank you!"
    return f"{base} · active until {when} · {renewal}"


def _pitch_subtitle(has_ads: bool) -> str:
    """Free-row pitch: what Premium buys here."""
    if has_ads:
        return (
            f"Removes ads and raises assistant credits from "
            f"{DAILY_FREE_CREDITS} to {DAILY_PREMIUM_CREDITS} a day"
        )
    return (
        f"Raises assistant credits from {DAILY_FREE_CREDITS} "
        f"to {DAILY_PREMIUM_CREDITS} a day"
    )


def _row(icon, title: str, subtitle: str, trailing=None) -> ft.Row:
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
            *([trailing] if trailing is not None else []),
        ],
        spacing=tokens.SPACE_LG,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def _divider() -> ft.Control:
    return ft.Divider(height=tokens.SPACE_SM)


# One catalog fetch per launch, not one per repaint of this card.
_PRICES_ATTEMPTED = False


def build_premium_section(page: ft.Page, state, services) -> ft.Column:
    """The PREMIUM card. DDGS's shape, built from observable state."""
    if CHANNEL == "play":
        # Unreachable in practice — the screen does not build this card on the
        # Play channel — but a direct caller must not get a purchase surface.
        return ft.Container(width=0, height=0)

    premium = getattr(services, "premium", None)
    license_ok = premium is not None and getattr(premium, "available", False)
    claims = (
        getattr(getattr(premium, "license", None), "claims", None)
        if license_ok
        else None
    )
    lapse = str(getattr(claims, "status", "") or "")
    has_ads = page_has_ads(page, state, services)
    is_premium = bool(getattr(state, "is_premium", False))
    prices = getattr(state, "license_prices", {}) or {}
    recovery = str(getattr(state, "license_recovery_id", "") or "")

    rows: list[ft.Control] = []

    # ── Status ──────────────────────────────────────────────────────────────
    # One row, always present: a lapse explains, a paid row shows the token's
    # own dates, a free row is the pitch.
    if is_premium and lapse in _STATUS_COPY:
        title, subtitle = _STATUS_COPY[lapse]
        rows.append(
            _row(
                ft.Icons.WORKSPACE_PREMIUM_ROUNDED,
                title,
                subtitle,
                ft.Icon(
                    ft.Icons.ERROR_OUTLINE_ROUNDED,
                    size=tokens.ICON_SM,
                    color=ft.Colors.ERROR,
                ),
            )
        )
    elif is_premium:
        rows.append(
            _row(
                ft.Icons.WORKSPACE_PREMIUM_ROUNDED,
                "CollabShell Premium",
                _paid_subtitle(claims, has_ads),
                ft.Icon(
                    ft.Icons.CHECK_CIRCLE_ROUNDED,
                    size=tokens.ICON_MD,
                    color=ft.Colors.SUCCESS,
                ),
            )
        )
    elif lapse in _STATUS_COPY:
        # A lapsed payment is explained before the buy rows: say what happened
        # first, the way back is the very next section.
        title, subtitle = _STATUS_COPY[lapse]
        rows.append(
            _row(
                ft.Icons.REPORT_ROUNDED,
                title,
                subtitle,
                ft.Icon(
                    ft.Icons.ERROR_OUTLINE_ROUNDED,
                    size=tokens.ICON_SM,
                    color=ft.Colors.ERROR,
                ),
            )
        )
    else:
        rows.append(
            _row(
                ft.Icons.WORKSPACE_PREMIUM_ROUNDED,
                "CollabShell Premium",
                _pitch_subtitle(has_ads),
                ft.Icon(
                    ft.Icons.CIRCLE_OUTLINED,
                    size=tokens.ICON_SM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            )
        )

    # ── Plans (only while free) ────────────────────────────────────────────
    if license_ok and not is_premium:
        if prices:
            for product_id, blurb in _PLANS:
                price = prices.get(product_id, "")
                if not price:
                    continue
                rows.append(_divider())
                rows.append(
                    _row(
                        ft.Icons.LOCK_OPEN_ROUNDED
                        if product_id == "lifetime"
                        else ft.Icons.AUTORENEW_ROUNDED,
                        product_id.capitalize(),
                        blurb,
                        ft.FilledButton(
                            price,
                            on_click=lambda e, pid=product_id: _ask_email(pid),
                        ),
                    )
                )
        elif _PRICES_ATTEMPTED:
            # A real failure, not the first paint: say so, and offer the retry.
            rows.append(_divider())
            rows.append(
                _row(
                    ft.Icons.CLOUD_OFF_ROUNDED,
                    "Unlock options unavailable",
                    "Could not reach the license service. Check your connection",
                    ft.OutlinedButton("Retry", on_click=lambda e: _load_prices()),
                )
            )
        else:
            rows.append(_divider())
            rows.append(
                _row(
                    ft.Icons.CLOUD_OFF_ROUNDED,
                    "Loading unlock options",
                    "Fetching this week's prices from the licence service",
                    ft.ProgressRing(
                        width=tokens.ICON_SM, height=tokens.ICON_SM, stroke_width=2
                    ),
                )
            )

        if recovery:
            rows.append(_divider())
            rows.append(
                _row(
                    ft.Icons.KEY_ROUNDED,
                    "Your recovery ID",
                    recovery,
                    ft.OutlinedButton(
                        "Copy",
                        icon=ft.Icons.CONTENT_COPY_ROUNDED,
                        on_click=lambda e: page.run_task(_copy_recovery, recovery),
                    ),
                )
            )

    # ── Restore ────────────────────────────────────────────────────────────
    if license_ok:
        rows.append(_divider())
        rows.append(
            _row(
                ft.Icons.RESTORE_ROUNDED,
                "Restore purchases",
                "Re-check ownership (new device / reinstall)",
                ft.OutlinedButton("Restore", on_click=lambda e: _ask_recovery()),
            )
        )

    # ── the loaders ─────────────────────────────────────────────────────────

    async def _load_prices(ev=None):
        """Fetch prices and the recovery ID once, into observable state.

        A write to `state.license_prices` repaints this card through the
        observable notify — no control is mutated, and nothing is pushed to
        the client from inside a render body.
        """
        global _PRICES_ATTEMPTED
        if not license_ok:
            return
        if _PRICES_ATTEMPTED and prices:
            return
        _PRICES_ATTEMPTED = True
        try:
            fetched = await premium.kiri_catalog()
            state.license_prices = {
                str(p.id): str(p.price_label) for p in fetched
            } or {}
        except Exception as ex:
            logger.warning("Premium catalog failed: %s", ex)
            state.license_prices = {}
        try:
            state.license_recovery_id = (await premium.license.recovery_id()) or ""
        except Exception as ex:
            logger.warning("Premium recovery read failed: %s", ex)

    def _reload_prices():
        global _PRICES_ATTEMPTED
        _PRICES_ATTEMPTED = False
        page.run_task(_load_prices)

    if not _PRICES_ATTEMPTED:
        page.run_task(_load_prices)

    async def _copy_recovery(value: str):
        try:
            await ft.Clipboard().set(value)
        except Exception as ex:
            logger.warning("Recovery ID copy failed: %s", ex)
        show_notification(page, "Recovery ID copied. Keep it somewhere safe.")

    # ── the dialogs ─────────────────────────────────────────────────────────

    def _ask_email(product_id: str):
        """One required field, and it appears when you ask to buy."""
        label = f"{product_id.capitalize()} {prices.get(product_id, '')}".rstrip()
        email_ref = ft.Ref[ft.TextField]()

        def _start(ev=None):
            email = (email_ref.current.value or "").strip() if email_ref.current else ""
            if not EMAIL_RE.match(email):
                show_notification(page, "Enter a valid email address.", is_warning=True)
                return
            page.pop_dialog()
            page.run_task(_checkout, product_id, email)

        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text(f"Unlock CollabShell Premium — {label}"),
                content=ft.Column(
                    controls=[
                        ft.Text(
                            "Card, bank transfer and USDC are handled by our "
                            "payment partner. This app never sees your card "
                            "number."
                        ),
                        ft.TextField(
                            ref=email_ref,
                            label="Email for your receipt",
                            hint_text="you@example.com",
                            keyboard_type=ft.KeyboardType.EMAIL,
                            autofocus=True,
                            on_submit=lambda ev: _start(),
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                    tight=True,
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda ev: page.pop_dialog()),
                    ft.FilledButton("Continue", on_click=lambda ev: _start()),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )

    def _ask_recovery():
        field_ref = ft.Ref[ft.TextField]()

        def _restore(ev=None):
            code = (field_ref.current.value or "").strip() if field_ref.current else ""
            page.pop_dialog()
            page.run_task(_restore_license, code or recovery)

        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Restore your license"),
                content=ft.Column(
                    controls=[
                        ft.TextField(
                            ref=field_ref,
                            label="Recovery ID",
                            hint_text=recovery or "KIRI-L-…",
                        ),
                        ft.Text(
                            "Your recovery ID is in your receipt email. "
                            "It is also stored on this device.",
                            size=tokens.FONT_XS,
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                    tight=True,
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda ev: page.pop_dialog()),
                    ft.FilledButton("Restore", on_click=lambda ev: _restore()),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )

    async def _restore_license(code: str):
        if not code:
            show_notification(page, "Enter your recovery ID first.", is_warning=True)
            return
        try:
            status = await premium.kiri_restore(code)
        except Exception as ex:
            show_notification(
                page, f"Could not reach the licence service: {ex}", is_error=True
            )
            return
        state.license_recovery_id = status.recovery_id or code
        if bool(getattr(state, "is_premium", False)):
            show_notification(page, "Premium restored.", is_success=True)
        else:
            show_notification(
                page, f"That licence is {status.status}.", is_warning=True
            )

    async def _checkout(product_id: str, email: str):
        try:
            checkout = await premium.kiri_checkout(product_id, email)
        except Exception as ex:
            show_notification(
                page, f"Could not open the payment page: {ex}", is_error=True
            )
            return
        # The recovery ID is available the moment the order exists — surface
        # it before the browser takes over, because the hosted page is the
        # last place a user will copy it from.
        if getattr(checkout, "recovery_id", ""):
            state.license_recovery_id = checkout.recovery_id
        url = str(getattr(checkout, "checkout_url", "") or "")
        if not url.startswith("https://"):
            logger.warning("Refused non-https checkout URL: %r", url[:60])
            show_notification(
                page, "Could not start the payment — try again.", is_error=True
            )
            return
        try:
            await ft.UrlLauncher().launch_url(url)
        except Exception as ex:
            show_notification(
                page,
                f"Could not open the payment page ({ex}). Your recovery ID is "
                f"{state.license_recovery_id}.",
                is_error=True,
            )
            return
        # The watcher polls in the background; the card unlocks by itself.
        show_notification(
            page, "Complete the payment. This screen unlocks itself when it lands."
        )

    return ft.Column(
        controls=[
            section_header("PREMIUM"),
            glass_card(
                ft.Column(controls=rows, spacing=tokens.SPACE_XS, tight=True),
                margin=ft.Margin(
                    tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
                ),
            ),
        ],
        spacing=0,
    )

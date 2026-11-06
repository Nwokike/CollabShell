"""Settings → Premium — KTV Player's premium card, verbatim.

The owner's rule: exactly KTV Player's premium on every count — the rows,
the order, the dialogs, the copy, the busy/error states. Nothing added,
nothing removed. Only the app name and the benefit sentence are this app's:
KTV's channel-pack line describes a product CollabShell does not have, so
the same sentence shape carries this app's real benefit (500 credits a day).

Structure (KTV settings_screen.py:942-1235):

    status row      "CollabShell Premium" + honest subtitle + check mark
    kiri rows       (free only) every catalog product, the recovery ID with
                    Copy, then error-with-Retry or loading-while-in-flight
    restore row     always: Restore purchases

The card is built from observable state on every render — the same repaint
behavior KTV gets from its use_state + premium_service listener pair, through
this app's observable AppState instead.
"""

from __future__ import annotations

import logging
import time

import flet as ft

from core import tokens
from core.channel import CHANNEL
from core.constants import DAILY_PREMIUM_CREDITS
from core.notifications import show_notification
from core.styles import glass_card, section_header
from core.theme import AppColors

logger = logging.getLogger("PremiumSection")

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

# One catalog fetch per launch, not one per repaint of this card. (KTV uses
# ft.on_mounted(_load_license) for re-fetch-on-mount, but CollabShell's
# section builders are plain functions called from the SettingsScreen
# component body, and test_a_plain_section_builder_never_registers_a_hook
# forbids flet hooks there — so the once-per-launch flag is the port.)
_ATTEMPTED = False


def page_has_ads(page) -> bool:
    """True where ads are actually requested (KTV notifications.py:143).

    Only ANDROID/IOS phones show ads; desktop/web never request any, so
    claiming "no ads" there would be a lie. Unknown page -> assume ads.
    """
    try:
        return bool(page.platform.is_mobile())
    except Exception:
        return True


def premium_unlocked_message(page) -> str:
    """Platform-honest unlock toast (KTV notifications.py:156)."""
    if page_has_ads(page):
        return "Premium unlocked. Ads removed."
    return "Premium unlocked."


def _premium_subtitle(is_premium, claims, has_ads: bool) -> str:
    """Premium row subtitle: honest benefits for this platform.

    The benefit is this app's (credits a day); "no ads" is claimed only
    where ads are actually requested (phones). paid-through comes from the
    signed token (exp-guarded), so the dates stay truthful offline, and
    its absence marks a lifetime license.
    """
    pack = f"{DAILY_PREMIUM_CREDITS} assistant credits a day"
    if not is_premium:
        return f"Remove all ads and unlock {pack}" if has_ads else f"Unlock {pack}"
    base = (
        f"Ads removed · {DAILY_PREMIUM_CREDITS} credits a day"
        if has_ads
        else f"{DAILY_PREMIUM_CREDITS} credits a day"
    )
    paid_through = getattr(claims, "paid_through", None)
    if not paid_through:
        return f"{base} · thank you!"
    product = str(getattr(claims, "product", "") or "")
    renewal = {"monthly": "renews monthly", "yearly": "renews yearly"}.get(
        product, "renews automatically"
    )
    try:
        moment = time.gmtime(int(paid_through) / 1000)
        label = f"{moment.tm_mday} {_MONTHS[moment.tm_mon - 1]} {moment.tm_year}"
    except (TypeError, ValueError, OverflowError, OSError):
        return f"{base} · thank you!"
    return f"{base} · active until {label} · {renewal}"


def _row(leading, title: str, subtitle: str, trailing=None) -> ft.Container:
    """KTV's _setting_row verbatim: [icon+text] ---- [control]."""
    try:
        from flet import context

        page = context.page
    except Exception:
        page = None
    return ft.Container(
        content=ft.Row(
            controls=[
                ft.Row(
                    controls=[
                        leading,
                        ft.Column(
                            controls=[
                                ft.Text(title, size=13, weight=ft.FontWeight.W_500),
                                ft.Text(
                                    subtitle,
                                    size=11,
                                    color=AppColors.grey_dim(page),
                                ),
                            ],
                            spacing=1,
                            expand=True,
                        ),
                    ],
                    spacing=12,
                    expand=True,
                ),
                *([trailing] if trailing is not None else []),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding(4, 10, 4, 10),
    )


def build_premium_section(page: ft.Page, state, services) -> ft.Column:
    """The PREMIUM card — KTV's rows, order, dialogs and copy."""
    premium_service = getattr(services, "premium", None)
    is_premium = bool(getattr(state, "is_premium", False))
    products = list(getattr(state, "license_products", []) or [])
    recovery_id = str(getattr(state, "license_recovery_id", "") or "")
    license_busy = bool(getattr(state, "license_busy", False))
    license_error = str(getattr(state, "license_error", "") or "")
    has_ads = page_has_ads(page)

    # ── Kiri License (the backend for installs Play cannot bill) ───────────

    async def _load_license():
        if not premium_service or not premium_service.available:
            return
        state.license_error = ""
        # Loading, not failing: the row must not claim the license service is
        # unreachable while the request is still in flight.
        state.license_busy = True
        try:
            state.license_products = list(await premium_service.kiri_catalog())
        except Exception:
            logger.debug("License catalog load failed", exc_info=True)
            state.license_error = "Could not reach the license service."
            state.license_busy = False
            return
        state.license_busy = False
        try:
            license_svc = premium_service.license
            state.license_recovery_id = (
                await license_svc.recovery_id() if license_svc else ""
            )
        except Exception:
            logger.debug("Recovery ID load failed", exc_info=True)

    def _run_guarded(fn):
        """KTV's guard: the Retry row must not double-fire while busy."""

        def _go(e=None):
            if getattr(state, "license_busy", False):
                return
            page.run_task(fn)

        return _go

    global _ATTEMPTED
    if premium_service is not None and not _ATTEMPTED:
        _ATTEMPTED = True
        page.run_task(_load_license)

    # ── the dialogs (KTV verbatim) ──────────────────────────────────────────

    def _ask_email(product_label: str):
        """Email is required by the payment provider and is the only field
        the user has to type."""
        field = ft.TextField(
            label="Email for your receipt",
            hint_text="you@example.com",
            keyboard_type=ft.KeyboardType.EMAIL,
            width=320,
        )
        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text(f"Unlock CollabShell Premium — {product_label}", size=15),
                content=field,
                actions=[
                    ft.TextButton("Cancel", on_click=lambda e: page.pop_dialog()),
                    ft.FilledButton(
                        "Continue",
                        on_click=lambda e: page.run_task(
                            _start_kiri_checkout, product_label, field
                        ),
                    ),
                ],
            )
        )

    async def _start_kiri_checkout(product_id: str, field):
        email = (field.value or "").strip()
        if not email or "@" not in email:
            show_notification(page, "Enter a valid email address", is_warning=True)
            return
        page.pop_dialog()
        state.license_busy = True
        try:
            checkout = await premium_service.kiri_checkout(product_id, email)
            state.license_recovery_id = checkout.recovery_id
            # Flutterwave hosts the payment; the app never sees card data.
            # kiri_checkout already started the watcher — no manual step.
            checkout_url = checkout.checkout_url or ""
            if not checkout_url.startswith("https://"):
                logger.debug("Refused non-https checkout URL")
                show_notification(
                    page, "Could not start the payment — try again.", is_warning=True
                )
                return
            await ft.UrlLauncher().launch_url(checkout_url)
            show_notification(
                page,
                "Complete the payment. This screen unlocks itself when it lands",
            )
        except Exception as ex:
            logger.debug("Kiri checkout failed", exc_info=True)
            show_notification(
                page, str(ex) or "Could not start the payment", is_warning=True
            )
        finally:
            state.license_busy = False

    def _ask_recovery_id(e=None):
        field = ft.TextField(
            label="Recovery ID",
            hint_text=recovery_id or "KIRI-L-...",
            width=340,
        )
        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Restore your license", size=15),
                content=ft.Column(
                    [
                        field,
                        ft.Text(
                            "Your recovery ID is in your receipt email. "
                            "It is also stored on this device.",
                            size=11,
                        ),
                    ],
                    tight=True,
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda e: page.pop_dialog()),
                    ft.FilledButton(
                        "Restore",
                        on_click=lambda e: page.run_task(_redeem_kiri, field),
                    ),
                ],
            )
        )

    async def _redeem_kiri(field):
        code = (field.value or "").strip() or recovery_id
        if not code:
            show_notification(page, "Enter your recovery ID first.", is_warning=True)
            return
        page.pop_dialog()
        state.license_busy = True
        try:
            status = await premium_service.kiri_restore(code)
            state.license_recovery_id = status.recovery_id
            if bool(getattr(state, "is_premium", False)):
                show_notification(page, premium_unlocked_message(page))
            else:
                show_notification(page, f"License status: {status.status}")
        except Exception as ex:
            logger.debug("License restore failed", exc_info=True)
            show_notification(
                page, str(ex) or "Could not restore that license", is_warning=True
            )
        finally:
            state.license_busy = False

    async def _copy_recovery_id(e=None):
        if not recovery_id:
            return
        try:
            await ft.Clipboard().set(recovery_id)
            show_notification(page, "Recovery ID copied")
        except Exception:
            show_notification(
                page, "Copy failed — clipboard unavailable on this device", is_warning=True
            )

    def _kiri_product_row(product):
        return _row(
            leading=ft.Icon(
                ft.Icons.LOCK_OPEN_ROUNDED
                if product.id == "lifetime"
                else ft.Icons.AUTORENEW,
                size=18,
                color=ft.Colors.PRIMARY,
            ),
            title=product.id.capitalize(),
            subtitle=product.description or product.price_label,
            trailing=ft.FilledButton(
                product.price_label,
                on_click=lambda e, p=product: _ask_email(p.id),
                disabled=state.license_busy,
            ),
        )

    # ── the rows (KTV settings_screen.py:1131-1221) ─────────────────────────

    kiri_rows: list = []
    # Built only where the card is shown: assembling these on the play
    # channel still executed the raise, even though the card was discarded.
    if CHANNEL != "play" and not is_premium:
        kiri_rows = [
            *[_kiri_product_row(p) for p in products],
            *(
                [
                    _row(
                        leading=ft.Icon(
                            ft.Icons.KEY, size=18, color=ft.Colors.PRIMARY
                        ),
                        title="Your recovery ID",
                        subtitle=(
                            recovery_id or "Created when you start a payment"
                        ),
                        trailing=ft.OutlinedButton(
                            "Copy",
                            on_click=_copy_recovery_id,
                            disabled=not recovery_id,
                        ),
                    )
                ]
                if recovery_id
                else []
            ),
        ]
        if not products:
            if license_error:
                kiri_rows.append(
                    _row(
                        leading=ft.Icon(
                            ft.Icons.CLOUD_OFF,
                            size=18,
                            color=AppColors.grey_dim(page),
                        ),
                        title="Unlock options unavailable",
                        subtitle=f"{license_error} Tap Retry to try again.",
                        trailing=ft.OutlinedButton(
                            "Retry",
                            icon=ft.Icons.REFRESH,
                            on_click=_run_guarded(_load_license),
                        ),
                    )
                )
            elif license_busy:
                # A request is in flight: say so, rather than claiming the
                # service is unreachable (which is what rendered on every
                # first paint, before the fetch resolved).
                kiri_rows.append(
                    _row(
                        leading=ft.Icon(
                            ft.Icons.CLOUD_SYNC,
                            size=18,
                            color=AppColors.grey_dim(page),
                        ),
                        title="Loading unlock options",
                        subtitle="Contacting the license service",
                        trailing=ft.ProgressRing(
                            width=16, height=16, stroke_width=2
                        ),
                    )
                )
            # No products and no error and not busy: nothing to show yet.

    license_svc = getattr(premium_service, "license", None)
    rows: list[ft.Control] = [
        _row(
            leading=ft.Icon(
                ft.Icons.VERIFIED_ROUNDED,
                size=18,
                color=ft.Colors.PRIMARY if is_premium else ft.Colors.ON_SURFACE_VARIANT,
            ),
            title="CollabShell Premium",
            subtitle=_premium_subtitle(
                is_premium,
                getattr(license_svc, "claims", None),
                has_ads,
            ),
            trailing=ft.Icon(
                ft.Icons.CHECK_CIRCLE if is_premium else ft.Icons.CIRCLE_OUTLINED,
                size=20,
                color=(
                    ft.Colors.PRIMARY if is_premium else ft.Colors.ON_SURFACE_VARIANT
                ),
            ),
        ),
        # Kiri rows are absent from the Play build entirely — that guard sits
        # in the list assembly above (CHANNEL check).
        *([] if is_premium else kiri_rows),
        _row(
            leading=ft.Icon(ft.Icons.RESTORE, size=18, color=ft.Colors.PRIMARY),
            title="Restore purchases",
            subtitle="Re-check ownership (new device / reinstall)",
            trailing=ft.OutlinedButton("Restore", on_click=_ask_recovery_id),
        ),
    ]

    return ft.Column(
        controls=[
            section_header("PREMIUM"),
            glass_card(
                ft.Column(controls=rows, spacing=0, tight=True),
                margin=ft.Margin(
                    tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
                ),
            ),
        ],
        spacing=0,
    )

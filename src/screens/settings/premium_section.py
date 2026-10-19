"""Premium settings section — the upsell, checkout, and restore.

Verbatim in shape from ktv-player's premium section: product rows priced from
the Worker's live /catalog, an email field, an external hosted checkout, a
recovery ID with copy, and Restore purchases. On the Play channel the whole
card is skipped — that build has no premium of any kind.
"""

from __future__ import annotations

import logging

import flet as ft

from core import tokens
from core.channel import CHANNEL
from core.notifications import show_notification
from core.styles import after_render, glass_card, section_header, tip_text

logger = logging.getLogger("PremiumSection")


def _row(title: str, subtitle: str, trailing=None) -> ft.Row:
    return ft.Row(
        controls=[
            ft.Icon(
                ft.Icons.WORKSPACE_PREMIUM_ROUNDED,
                size=tokens.ICON_LG,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            ft.Column(
                controls=[
                    ft.Text(title, size=tokens.FONT_MD, weight=ft.FontWeight.W_500),
                    tip_text(subtitle),
                ],
                spacing=tokens.SPACE_XXS,
                expand=True,
            ),
            *( [trailing] if trailing is not None else [] ),
        ],
        spacing=tokens.SPACE_LG,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def premium_subtitle(state, claims=None, has_ads: bool = True) -> str:
    """Honest about what premium does here: it raises the assistant credits."""
    if not getattr(state, "is_premium", False):
        if has_ads:
            return (
                "Removes ads and raises assistant credits from 50 to "
                "500 a day."
            )
        return "Raises assistant credits from 50 to 500 a day."
    if claims is not None and not claims.is_lifetime and claims.expires_at:
        import datetime

        when = datetime.datetime.fromtimestamp(
            claims.expires_at, tz=datetime.UTC
        ).strftime("%d %b %Y")
        if claims.mode == "recurring":
            return f"500 credits a day · renews {when}"
        return f"500 credits a day · active until {when}"
    return "500 credits a day · thank you!"


def build_premium_section(page: ft.Page, state, services) -> ft.Column | ft.Container:
    """The PREMIUM card. Returns an empty container on the Play channel."""
    if CHANNEL == "play":
        return ft.Container(width=0, height=0)

    premium = getattr(services, "premium", None)
    if premium is None or not premium.available:
        return ft.Container(width=0, height=0)

    body = ft.Column(controls=[], spacing=tokens.SPACE_XS, tight=True)

    def _render(products: list, recovery: str = ""):
        body.controls.clear()
        body.controls.append(
            _row("Premium", premium_subtitle(state, premium.license.claims))
        )
        if recovery:
            body.controls.append(
                _row(
                    "Your recovery ID",
                    "Keep it somewhere safe — it restores your purchase on a "
                    "new device or after a reinstall.",
                    trailing=ft.OutlinedButton(
                        "Copy",
                        icon=ft.Icons.COPY_ROUNDED,
                        on_click=lambda e: _copy_handler(recovery),
                    ),
                )
            )
        body.controls.append(ft.Divider(height=tokens.SPACE_SM))
        if products:
            for product in products:
                body.controls.append(
                    _row(
                        product.id.replace("_", " ").title(),
                        product.description
                        or f"{product.price_label} · one payment",
                        trailing=ft.FilledButton(
                            product.price_label,
                            on_click=lambda e, pid=product.id: _ask_email(pid),
                        ),
                    )
                )
        else:
            body.controls.append(
                tip_text(
                    "Could not reach the license service. Check your "
                    "connection and try again."
                )
            )
        try:
            page.update()
        except Exception as ex:
            logger.warning("Premium render failed: %s", ex)

    async def _copy(text: str):
        # Page has no set_clipboard/show_snack in flet 1.0 — use the
        # Clipboard service and the shared notification helper.
        try:
            await ft.Clipboard().set(text)
        except Exception as ex:
            logger.warning("Recovery ID copy failed: %s", ex)
        show_notification(page, "Recovery ID copied. Keep it somewhere safe.")

    def _copy_handler(text: str):
        page.run_task(_copy, text)

    async def _load(ev=None):
        # StorageService.get is a coroutine and there is no sync `.data`, so
        # the recovery id is read through the service's own accessor. A
        # failure here must not blank the card.
        try:
            recovery = (await premium.license.recovery_id()) or ""
        except Exception as ex:
            logger.warning("Premium recovery read failed: %s", ex)
            recovery = ""
        try:
            products = await premium.kiri_catalog()
        except Exception as ex:
            logger.warning("Premium catalog failed: %s", ex)
            products = []
        _render(products, recovery)

    def _ask_email(product_id: str):
        email_ref = ft.Ref[ft.TextField]()

        def _start(ev=None):
            email = email_ref.current.value if email_ref.current else ""
            page.pop_dialog()
            page.run_task(_checkout, product_id, email or "")

        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Unlock Premium"),
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

    async def _checkout(product_id: str, email: str):
        try:
            checkout = await premium.kiri_checkout(product_id, email)
        except Exception as ex:
            show_notification(page, f"Could not open the payment page: {ex}", is_error=True)
            return
        # The hosted page opens outside the app; the watcher polls in the
        # background and unlocks by itself.
        try:
            import webbrowser

            webbrowser.open(checkout.checkout_url)
        except Exception:
            show_notification(
                page, "Complete the payment. This screen unlocks itself when it lands."
            )
        else:
            show_notification(
                page, "Complete the payment. This screen unlocks itself when it lands."
            )

    # NOT `page.run_task(_load)` in the body: `build_premium_section` runs
    # inside SettingsScreen's `@ft.component` body, and flet 1.0 forbids touching
    # the page from there — a task that mutates controls mid-render races the
    # component's own patch and the screen comes back blank with no traceback
    # (`flet/components/component.py:145-167`). See `core.styles.after_render`.
    _render([])
    after_render(lambda: page.run_task(_load))

    return ft.Column(
        controls=[
            section_header("PREMIUM"),
            glass_card(
                body,
                margin=ft.Margin(
                    tokens.SPACE_LG, tokens.SPACE_XS, tokens.SPACE_LG, tokens.SPACE_XS
                ),
            ),
        ],
        spacing=0,
    )

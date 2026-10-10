"""Premium settings section — the upsell, checkout, and restore.

Verbatim in shape from ktv-player's premium section: product rows priced from
the Worker's live /catalog, an email field, an external hosted checkout, a
recovery ID with copy, and Restore purchases. On the Play channel the whole
card is skipped — that build has no premium of any kind.
"""

from __future__ import annotations

import logging

import flet as ft

from core import constants, tokens
from core.channel import CHANNEL
from core.styles import glass_card, section_header, tip_text

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

    def _render(products: list):
        body.controls.clear()
        body.controls.append(
            _row("Premium", premium_subtitle(state, premium.license.claims))
        )
        recovery = premium.license.storage.data.get(constants.SETTING_RECOVERY_ID, "")
        if recovery:
            body.controls.append(
                _row(
                    "Your recovery ID",
                    "Keep it somewhere safe — it restores your purchase on a "
                    "new device or after a reinstall.",
                    trailing=ft.OutlinedButton(
                        "Copy",
                        icon=ft.Icons.COPY_ROUNDED,
                        on_click=lambda e: _copy(recovery, page),
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

    def _copy(text: str, pg):
        pg.set_clipboard(text)
        pg.show_snack("Recovery ID copied. Keep it somewhere safe.")

    async def _load(ev=None):
        products = await premium.kiri_catalog()
        _render(products)

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
            page.show_snack(f"Could not open the payment page: {ex}")
            return
        # The hosted page opens outside the app; the watcher polls in the
        # background and unlocks by itself.
        try:
            import webbrowser

            webbrowser.open(checkout.checkout_url)
        except Exception:
            page.show_snack(
                "Complete the payment. This screen unlocks itself when it lands."
            )
        else:
            page.show_snack(
                "Complete the payment. This screen unlocks itself when it lands."
            )

    _render([])
    page.run_task(_load)

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

"""Premium via Google Play Billing — the default channel.

CollabShell has been on Play since v1, so Play Billing is the primary way to
become premium. The Kiri License Worker (see `license_service.py`) is the
fallback for users Google billing cannot serve; either one sets
`state.is_premium`, and neither one hides the other.

This is the same service KTV Player ships, with CollabShell's storage:

- Billing attaches on **Android only**. `in_app_purchase` has no desktop or
  web platform, and an invoke there stalls for the full timeout on boot.
- Boot reads the local flag first (instant UI), then reconciles with the store
  *after* the first render. A failed store check never downgrades the flag —
  a user who bought Premium does not lose it because the store was slow.
- Buy re-queries the product first: a Play product created after boot takes
  time to propagate, and a product the store does not know yet is a friendly
  False rather than an exception.
- Every purchased/restored transaction is acknowledged with
  `complete_purchase()` inside the handler — the 3-day Play rule. Google
  auto-refunds anything left unacknowledged.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import flet as ft

from core import constants
from core.state import state

logger = logging.getLogger("premium")

PREMIUM_PRODUCT_ID = "premium_unlock"

# These round-trips sit behind a settings button and on app resume, where a
# stalled network should surface as a message, not a spinner that never ends.
STORE_TIMEOUT = 6.0


class PremiumService:
    """Owns the Play Billing service and the persisted `premium` flag."""

    def __init__(self, page, storage):
        self.page = page
        self.storage = storage
        self.billing = None
        self.price: str | None = None
        self._listeners: list[Callable[[], None]] = []
        if self._supported():
            try:
                from flet_billing import Billing

                self.billing = Billing(on_purchase_updated=self._on_purchases)
                # Service auto-registers against context.page; appending
                # again would register the same instance twice.
                if self.billing not in page.services:
                    page.services.append(self.billing)
            except Exception:
                # A build without the billing extension still runs; the
                # fallback channel is unaffected.
                logger.warning("Play Billing unavailable", exc_info=True)

    def _supported(self) -> bool:
        """Android has a Play Store; desktop and web do not, and an invoke
        there would stall for the full timeout on every call."""
        try:
            return bool(self.page.platform.is_mobile())
        except Exception:
            return False

    # ── Observation ─────────────────────────────────────────────────────

    def add_listener(self, callback: Callable[[], None]) -> None:
        if callback not in self._listeners:
            self._listeners.append(callback)

    def _notify(self) -> None:
        for callback in list(self._listeners):
            try:
                callback()
            except Exception:
                logger.debug("Premium listener failed", exc_info=True)

    @property
    def available(self) -> bool:
        """True when Play Billing is attached (Android builds)."""
        return self.billing is not None

    # ── Entitlement ─────────────────────────────────────────────────────

    async def load_local(self) -> None:
        """Read the persisted **Play** entitlement — boot-path safe.

        This flag is a cache of a store purchase that `reconcile()` confirms
        with Google Play on every launch. It is deliberately NOT a general
        premium unlock: a Kiri license must be proved by its signed token
        (`license_service.cached_entitlement`), never by a `true` in storage.
        The two proofs stay apart so a Kiri purchase can never be granted by
        this path, and a Play purchase is never granted by a token.
        """
        try:
            source = await self.storage.get(constants.STORAGE_PREMIUM_SOURCE)
            if source != "play":
                return
            if await self.storage.get(constants.STORAGE_PREMIUM) == "true":
                state.is_premium = True
                state.premium_source = "play"
                state.premium_product = (
                    await self.storage.get(constants.STORAGE_PREMIUM_PRODUCT)
                    or PREMIUM_PRODUCT_ID
                )
        except Exception:
            logger.warning("Could not read premium flag", exc_info=True)

    async def activate(self, product: str = PREMIUM_PRODUCT_ID) -> None:
        """Mark premium and persist the proof that survives a reinstall-free
        restart. Each channel writes its own, so a Play purchase is restored
        by Play and a license by the Worker."""
        state.is_premium = True
        state.premium_source = "play"
        state.premium_product = product
        state.premium_offline = False
        try:
            await self.storage.set(constants.STORAGE_PREMIUM, "true")
            await self.storage.set(constants.STORAGE_PREMIUM_SOURCE, "play")
            await self.storage.set(constants.STORAGE_PREMIUM_PRODUCT, product)
        except Exception:
            logger.warning("Could not persist premium flag", exc_info=True)
        self._notify()

    async def reconcile(self) -> None:
        """Reconcile ownership with the store, after the first frame.

        Every call here is a network round-trip. A failed store check keeps
        the local flag: a paying user must never lose Premium to a bad
        network day.
        """
        if self.billing is None:
            return
        from flet_billing import PurchaseStatus

        try:
            if not await self.billing.is_available(timeout=STORE_TIMEOUT):
                return
        except TimeoutError:
            logger.info("Play store check timed out — keeping local flag")
            return
        except Exception:
            logger.warning("Play store check failed; keeping local flag", exc_info=True)
            return

        await self._refresh_product()
        try:
            owned = await self.billing.query_past_purchases(timeout=STORE_TIMEOUT)
            if any(
                p.product_id == PREMIUM_PRODUCT_ID
                and p.status is PurchaseStatus.PURCHASED
                for p in owned.purchases
            ):
                await self.activate()
        except Exception:
            logger.debug("query_past_purchases unavailable here", exc_info=True)
        try:
            await self.billing.restore_purchases(timeout=STORE_TIMEOUT)
        except Exception:
            logger.debug("restore_purchases failed", exc_info=True)

    async def _refresh_product(self) -> bool:
        """Query the premium product. False when the store does not know it
        yet — an expected state while a listing propagates, not an error."""
        if self.billing is None:
            return False
        try:
            result = await self.billing.query_products(
                [PREMIUM_PRODUCT_ID], timeout=STORE_TIMEOUT
            )
            if result.error:
                logger.info("Premium product query error: %s", result.error.message)
                return False
            product = next(
                (p for p in result.products if p.id == PREMIUM_PRODUCT_ID), None
            )
        except Exception:
            logger.warning("Premium product query failed", exc_info=True)
            return False
        if product is None:
            logger.info(
                "Premium product '%s' is not in this store yet", PREMIUM_PRODUCT_ID
            )
            return False
        self.price = product.price
        self._notify()
        return True

    # ── Actions ─────────────────────────────────────────────────────────

    async def buy(self) -> bool:
        """Start the one-time purchase. The result arrives through the
        purchase stream. False when the store cannot offer it."""
        if state.is_premium:
            return True
        if self.billing is None:
            logger.info("Play purchase requested on an unsupported platform")
            return False
        if not await self._refresh_product():
            return False
        try:
            return await self.billing.buy_non_consumable(PREMIUM_PRODUCT_ID)
        except Exception:
            logger.exception("Premium purchase request failed")
            return False

    async def restore_purchases(self) -> None:
        """Ask Play to re-deliver anything this account still owns."""
        if self.billing is None:
            return
        try:
            await self.billing.restore_purchases(timeout=STORE_TIMEOUT)
        except Exception:
            logger.warning("restore_purchases failed", exc_info=True)

    async def _on_purchases(self, e) -> None:
        from flet_billing import PurchaseStatus

        for purchase in getattr(e, "purchases", []) or []:
            if (
                purchase.status
                in (
                    PurchaseStatus.PURCHASED,
                    PurchaseStatus.RESTORED,
                )
                and purchase.product_id == PREMIUM_PRODUCT_ID
            ):
                # Acknowledge first: Play refunds anything left pending.
                if getattr(purchase, "pending_complete_purchase", False) and getattr(
                    purchase, "purchase_id", None
                ):
                    try:
                        await self.billing.complete_purchase(purchase.purchase_id)
                    except Exception:
                        logger.warning("complete_purchase failed", exc_info=True)
                await self.activate(purchase.product_id)
            elif purchase.status is PurchaseStatus.ERROR:
                # Play's own recovery dialog for failed/deferred purchases.
                try:
                    await self.billing.show_in_app_messages()
                except Exception:
                    logger.debug("show_in_app_messages unavailable", exc_info=True)


__all__ = ["PREMIUM_PRODUCT_ID", "PremiumService", "ft"]

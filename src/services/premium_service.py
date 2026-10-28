"""Premium entitlement — is the user entitled to the higher daily credit cap?

Verbatim port of ktv-player/src/services/premium_service.py. The service layer
(`KiriLicenseService`) owns the token and the Worker calls; this owns when to
ask, when to re-ask, and when to tell the UI.

The cadences are deliberate:
  * checkout is watched every ~5s with jitter and backoff — a payment page
    takes seconds to a couple of minutes;
  * steady state re-checks hourly;
  * a resume re-check is debounced 60s so a burst of app switches is one call.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from core.channel import CHANNEL
from services.license_service import (
    WATCHER_ABORT_CODES,
    Checkout,
    KiriLicenseService,
    LicenseStatus,
    LicenseUnavailable,
)

logger = logging.getLogger("premium_service")

CHECKOUT_WATCH_INTERVAL = 5.0
CHECKOUT_WATCH_TIMEOUT = 15 * 60.0
RECONCILE_INTERVAL = 60 * 60.0
RESUME_DEBOUNCE = 60.0


class PremiumService:
    """Owns ``state.is_premium`` and reconciles it with the Worker."""

    def __init__(self, page, state, storage=None):
        self.page = page
        self.state = state
        self.storage = storage
        self.backend: str = "none"  # "kiri" | "none"
        self._listeners: list[Callable[[], None]] = []
        self.license = KiriLicenseService(storage, on_change=self._recompute_premium)
        self._checkout_watch_task: asyncio.Task | None = None
        self._reconcile_task: asyncio.Task | None = None
        # Negative so the first resume is never debounced.
        self._last_reconcile_at = time.monotonic() - RESUME_DEBOUNCE
        if CHANNEL == "play":
            logger.info("Play channel build — premium disabled, free tier with ads")
            return
        self.backend = "kiri"

    # ── verdict ────────────────────────────────────────────────────────────

    def _recompute_premium(self) -> None:
        unlocked = self.license.unlocked
        if self.state.is_premium != unlocked:
            logger.info("Premium state -> %s (kiri)", unlocked)
            self.state.is_premium = unlocked
            self._notify_listeners()

    def add_listener(self, callback: Callable[[], None]) -> None:
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[], None]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify_listeners(self) -> None:
        for callback in list(self._listeners):
            try:
                callback()
            except Exception:
                logger.debug("Premium listener failed", exc_info=True)

    @property
    def available(self) -> bool:
        return self.backend == "kiri"

    def _premium_disabled(self) -> bool:
        if CHANNEL == "play":
            logger.debug("Purchase ignored: the Play build has no premium")
            return True
        return False

    # ── boot + reconcile ──────────────────────────────────────────────────

    async def load_local(self) -> None:
        """Unlock from the cached token. Offline by design, safe on boot."""
        if CHANNEL == "play":
            self.state.is_premium = False
            self._notify_listeners()
            return
        try:
            await self.license.apply_cached_token()
        except Exception:
            logger.warning("Could not verify the cached license", exc_info=True)
        self._recompute_premium()

    async def reconcile(self) -> None:
        """Re-check with the Worker, using the token-issuing path.

        ``/status`` never re-issues a token, so a renewal would leave the user
        locked out at the old ``exp``. ``/restore`` re-arms it.
        """
        if CHANNEL == "play":
            return  # no timestamp update
        try:
            recovery_id = await self.license.recovery_id()
        except Exception:
            logger.warning("Kiri license refresh: recovery ID unreadable")
            self._last_reconcile_at = time.monotonic()
            return
        if not recovery_id:
            self._recompute_premium()
            self._last_reconcile_at = time.monotonic()
            return
        try:
            await self.license.restore(recovery_id)
        except LicenseUnavailable as ex:
            if ex.is_refusal:
                logger.info("Kiri license refused (%s)", ex.status_code)
            else:
                logger.info("Kiri license refresh: %s", ex)
        except Exception:
            logger.debug("Kiri license refresh failed", exc_info=True)
        finally:
            self._recompute_premium()
            self._last_reconcile_at = time.monotonic()

    async def reconcile_if_due(self) -> None:
        """Resume re-check: debounced so a burst of switches is one call."""
        if self._premium_disabled():
            return
        if time.monotonic() - self._last_reconcile_at < RESUME_DEBOUNCE:
            return
        await self.reconcile()

    def start_reconcile_loop(self) -> None:
        if self._premium_disabled():
            return
        self.stop_reconcile_loop()
        self._reconcile_task = self.page.run_task(self._reconcile_loop)
        logger.info(
            "Hourly license reconcile started (interval %.0fs)", RECONCILE_INTERVAL
        )

    def stop_reconcile_loop(self) -> None:
        task = self._reconcile_task
        self._reconcile_task = None
        if task is not None and not task.done():
            task.cancel()

    async def _reconcile_loop(self) -> None:
        while True:
            await asyncio.sleep(RECONCILE_INTERVAL)
            try:
                # Forced, not debounced: the hourly loop is the scheduled tick.
                await self.reconcile()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("Hourly reconcile failed, will retry", exc_info=True)

    # ── checkout watcher ──────────────────────────────────────────────────

    def start_checkout_watch(self, recovery_id: str) -> None:
        if self._premium_disabled() or not recovery_id:
            return
        self.stop_checkout_watch()
        self._checkout_watch_task = self.page.run_task(
            self._checkout_watch_loop, recovery_id
        )
        logger.info(
            "Checkout watcher started (interval %.0fs)", CHECKOUT_WATCH_INTERVAL
        )

    def stop_checkout_watch(self) -> None:
        task = self._checkout_watch_task
        self._checkout_watch_task = None
        if task is not None and not task.done():
            task.cancel()

    async def _checkout_watch_loop(self, recovery_id: str) -> None:
        import random as _random

        deadline = time.monotonic() + CHECKOUT_WATCH_TIMEOUT
        failures = 0
        try:
            while time.monotonic() < deadline:
                # A parallel manual Restore may have unlocked first.
                if self.state.is_premium and self.license.unlocked:
                    return
                # Jitter scales with the interval; backoff grows with failures
                # so a struggling Worker is not hammered.
                backoff = min(30.0, CHECKOUT_WATCH_INTERVAL * failures)
                await asyncio.sleep(
                    CHECKOUT_WATCH_INTERVAL
                    + _random.uniform(0, CHECKOUT_WATCH_INTERVAL)
                    + backoff
                )
                try:
                    status = await self.license.restore(recovery_id)
                    failures = 0
                except LicenseUnavailable as ex:
                    if ex.is_refusal and ex.status_code in WATCHER_ABORT_CODES:
                        # A payment problem will not fix itself; 404 is NOT
                        # here because a webhook lag looks like a 404.
                        logger.info(
                            "Checkout watcher refused, stopping: %s", ex.status_code
                        )
                        return
                    failures += 1
                    logger.info("Checkout watcher waiting: %s", ex)
                    continue
                except asyncio.CancelledError:
                    raise
                except Exception:
                    # A DB hiccup must not kill the loop.
                    failures += 1
                    logger.debug("Checkout watcher error, continuing", exc_info=True)
                    continue

                if self.license.unlocked:
                    logger.info(
                        "Checkout watcher unlocked product=%s status=%s",
                        status.product,
                        status.status,
                    )
                    self._notify_premium_unlocked()
                    return
        finally:
            self._checkout_watch_task = None
        logger.info("Checkout watcher timed out — Restore purchases remains available")

    def _notify_premium_unlocked(self) -> None:
        """Tell the user the purchase landed. Ads-off is the mobile story."""
        show = getattr(self.page, "controller", None)
        snack = getattr(show, "show_snack", None) if show is not None else None
        if snack is None:
            snack = getattr(self.page, "show_snack", None)
        if snack is None:
            return
        try:
            if self.page.platform.is_mobile():
                snack("Premium unlocked. Ads removed.")
            else:
                snack("Premium unlocked.")
        except Exception:
            logger.debug("Could not show the unlock notice", exc_info=True)

    # ── shutdown ──────────────────────────────────────────────────────────

    async def ashutdown(self) -> None:
        """Cancel AND await, so a shutdown waits for the loops to finish."""
        tasks = [self._checkout_watch_task, self._reconcile_task]
        self._checkout_watch_task = None
        self._reconcile_task = None
        pending = [t for t in tasks if t is not None and not t.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    def shutdown(self) -> None:
        """Cancel only."""
        self.stop_checkout_watch()
        self.stop_reconcile_loop()

    # ── the kiri surface the settings UI calls ────────────────────────────

    async def kiri_catalog(self) -> list:
        if self._premium_disabled():
            return []
        try:
            return await self.license.fetch_catalog()
        except LicenseUnavailable as ex:
            logger.info("Kiri catalog unavailable: %s", ex)
            return []
        except Exception:
            logger.debug("Kiri catalog failed", exc_info=True)
            return []

    async def kiri_checkout(self, product_id: str, email: str) -> Checkout:
        if self._premium_disabled():
            raise LicenseUnavailable("Premium is not available in this build")
        checkout = await self.license.checkout(product_id, email)
        self.start_checkout_watch(checkout.recovery_id)
        return checkout

    async def kiri_restore(self, recovery_id: str) -> LicenseStatus:
        if self._premium_disabled():
            raise LicenseUnavailable("Premium is not available in this build")
        status = await self.license.restore(recovery_id)
        self._recompute_premium()
        if self.license.unlocked:
            self.stop_checkout_watch()
        return status

"""Premium unlock through the Kiri License Worker — KTV Player's model.

Single backend: **Kiri License** (license.kiri.ng) — Flutterwave checkout
and a signed entitlement token. It works on direct APK installs, Windows
and Linux with no Google permission at all.

Google Play Billing is not part of this build: the Play Console in use
has no Google Payments merchant profile, so there is nothing to sell with
and nothing testable. The Play AAB ships free-only (see
core.build_channel.CHANNEL) and this service goes inert on that channel —
no Worker requests, no purchase UI, no cached entitlement can unlock it.

Core rules, taken from KTV's service:

- The entitlement is a **signed token**, verified offline on every start —
  never a bare local flag. An unverifiable token grants nothing.
- The recovery ID is stored immediately: it is the only way back in after
  the user clears app data.
- A network failure never downgrades: only an authoritative Worker ruling
  (expired / revoked) clears the flag.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from core import constants
from core.state import state
from services import license_service as license

logger = logging.getLogger("premium")


def _is_play_build() -> bool:
    """The build-time channel marker, read fresh every time.

    Imported lazily (not at module top) so the marker is the value that
    governs the decision — same pattern license_service uses.
    """
    from core.build_channel import CHANNEL

    return CHANNEL == "play"


class PremiumService:
    """Owns the Kiri license and derives the `premium` flag from it."""

    def __init__(self, page, storage):
        self.page = page
        self.storage = storage
        self.backend: str = "none"  # "kiri" | "none"
        self._listeners: list[Callable[[], None]] = []
        if _is_play_build():
            # Free-only build: no purchase surface of any kind is wired up.
            logger.info("Play channel build — premium disabled, free tier with ads")
            return
        self.backend = "kiri"

    # ── Observation ─────────────────────────────────────────────────────

    def add_listener(self, callback: Callable[[], None]) -> None:
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[], None]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify(self) -> None:
        for callback in list(self._listeners):
            try:
                callback()
            except Exception:
                logger.debug("Premium listener failed", exc_info=True)

    @property
    def available(self) -> bool:
        """True when this build can offer a purchase at all."""
        return self.backend == "kiri"

    def _premium_disabled(self) -> bool:
        if _is_play_build():
            logger.debug("Purchase ignored: the Play build has no premium")
            return True
        return False

    # ── Lifecycle ───────────────────────────────────────────────────────

    async def load_local(self) -> None:
        """Verify the cached signed token — safe on the boot path.

        Offline by design: a paid user keeps Premium with no network at
        all, and a token that no longer verifies (expired, tampered,
        revoked) grants nothing. A bare `premium=true` in storage is never
        enough — that is the difference from a flag-based system.
        """
        if _is_play_build():
            # Free-only build: a token left over from a direct install must
            # never unlock it.
            state.is_premium = False
            return
        try:
            entitlement = await license.cached_entitlement(self.storage)
        except Exception:
            logger.warning("Could not verify the cached license", exc_info=True)
            entitlement = None
        if entitlement is not None:
            await license.apply_entitlement(entitlement)
        else:
            # No token, or one that failed verification: not entitled.
            state.is_premium = False
            state.premium_source = ""
            state.premium_offline = True
        self._notify()

    async def reconcile(self) -> None:
        """Refresh the entitlement with the Worker.

        A network round-trip, so this runs *after* the first frame, never
        before it. It runs even while unlocked: the Worker is
        authoritative when reachable, so a refund or expiry must land.
        Only a network failure keeps the local verdict.
        """
        if _is_play_build():
            return
        recovery_id = await self.storage.get(constants.STORAGE_LICENSE_RECOVERY)
        if not recovery_id:
            return
        try:
            entitlement = await license.check_status(recovery_id)
        except license.LicenseError as ex:
            if ex.code in ("license_not_found", "app_not_entitled"):
                # The Worker ruled: no such purchase. That is authoritative.
                await license.apply_entitlement(
                    license.Entitlement(status="expired", recovery_id=str(recovery_id))
                )
                self._notify()
            else:
                # Unreachable or rate-limited: keep the current verdict.
                logger.info("Kiri license refresh inconclusive: %s", ex)
            return
        except Exception:
            logger.debug("Kiri license refresh failed", exc_info=True)
            return
        await license.store_entitlement(self.storage, entitlement)
        await license.apply_entitlement(entitlement)
        self._notify()

    # ── The Worker surface, one call each ───────────────────────────────

    async def kiri_catalog(self) -> list:
        """Products offered by the license Worker, or [] when unavailable."""
        if self._premium_disabled():
            return []
        try:
            return await license.get_catalog()
        except license.LicenseError as ex:
            logger.info("License catalog unavailable: %s", ex)
            return []

    async def kiri_checkout(self, product_id: str, email: str) -> dict:
        """Create a hosted payment; the recovery ID is saved for restore."""
        if self._premium_disabled():
            raise license.LicenseError("Premium is not available in this build")
        checkout = await license.start_checkout(email, product_id)
        recovery = checkout.get("recovery_id") or ""
        if recovery:
            await self.storage.set(constants.STORAGE_LICENSE_RECOVERY, recovery)
        self._notify()
        return checkout

    async def kiri_restore(self, recovery_id: str) -> license.Entitlement:
        """Redeem a recovery ID. Raises LicenseError with the reason."""
        if self._premium_disabled():
            raise license.LicenseError("Premium is not available in this build")
        entitlement = await license.restore(recovery_id)
        await license.store_entitlement(self.storage, entitlement)
        await license.apply_entitlement(entitlement)
        self._notify()
        return entitlement

    async def kiri_check_status(self) -> license.Entitlement | None:
        """Re-check the saved entitlement; None when there is nothing to ask."""
        if self._premium_disabled():
            return None
        recovery_id = await self.storage.get(constants.STORAGE_LICENSE_RECOVERY)
        if not recovery_id:
            return None
        entitlement = await license.check_status(str(recovery_id))
        await license.store_entitlement(self.storage, entitlement)
        await license.apply_entitlement(entitlement)
        self._notify()
        return entitlement


__all__ = ["PremiumService"]

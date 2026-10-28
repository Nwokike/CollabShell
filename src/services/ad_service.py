"""AdMob service — banner and interstitial ads.

Direct port of Sherlock's production AdService pattern.
Uses test Ad IDs until Play Store launch.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

import flet as ft

from core.state import state

logger = logging.getLogger(__name__)

try:
    import flet_ads as fta

    _HAS_ADS = True
except ImportError:
    _HAS_ADS = False


class AdService:
    """Manages AdMob banner and interstitial ads."""

    MIN_INTERSTITIAL_GAP = 60.0  # seconds between interstitials (all call sites)

    USE_TEST_IDS = False  # Production AdMob IDs active

    BANNER_ID_ANDROID_TEST = "ca-app-pub-3940256099942544/9214589741"
    INTERSTITIAL_ID_ANDROID_TEST = "ca-app-pub-3940256099942544/1033173712"

    BANNER_ID_ANDROID_PROD = "ca-app-pub-5679949845754640/8726930570"
    INTERSTITIAL_ID_ANDROID_PROD = "ca-app-pub-5679949845754640/7258916174"
    NATIVE_ID_ANDROID_PROD = "ca-app-pub-5679949845754640/1634521578"

    NATIVE_ID_ANDROID_TEST = "ca-app-pub-3940256099942544/2247696110"

    def __init__(self, page: ft.Page):
        self.page = page
        self.interstitial = None
        self._interstitial_loaded = False
        self._interstitial_shown = False
        self._pending_interstitial = False
        self._active_rewarded_ad = None
        self._on_close: Callable | None = None
        self._can_request_ads: bool = True
        self._consent_manager = None

    @property
    def banner_id(self) -> str:
        if self.USE_TEST_IDS:
            return self.BANNER_ID_ANDROID_TEST
        return self.BANNER_ID_ANDROID_PROD

    @property
    def interstitial_id(self) -> str:
        if self.USE_TEST_IDS:
            return self.INTERSTITIAL_ID_ANDROID_TEST
        return self.INTERSTITIAL_ID_ANDROID_PROD

    @property
    def native_id(self) -> str:
        if self.USE_TEST_IDS:
            return self.NATIVE_ID_ANDROID_TEST
        return self.NATIVE_ID_ANDROID_PROD

    @property
    def _premium(self) -> bool:
        """True when the user owns Kiri premium: no ads, ever."""
        try:
            from core.state import state

            return bool(getattr(state, "is_premium", False))
        except Exception:
            return False

    def _is_mobile(self) -> bool:
        try:
            return not self.page.web and self.page.platform.is_mobile()
        except (
            ValueError,
            TypeError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
        ):
            return False

    # ── Consent Management (UMP) ──────────────────────────────────────────────

    async def gather_consent(self):
        """Run UMP consent flow. Only shows UI in regulated regions (EEA/UK)."""
        if state.is_premium or not _HAS_ADS or not self._is_mobile():
            self._can_request_ads = True
            return
        try:
            # Sherlock's production pattern: flet-ads auto-registers on
            # construction, but a service whose refcount drops can be
            # unregistered - keep it in page.services explicitly.
            self._consent_manager = fta.ConsentManager()
            if self._consent_manager not in self.page.services:
                self.page.services.append(self._consent_manager)
            await self._consent_manager.request_consent_info_update()
            await self._consent_manager.load_and_show_consent_form_if_required()
            self._can_request_ads = await self._consent_manager.can_request_ads()
        except Exception as e:
            logger.warning("UMP consent flow failed, defaulting to allow ads: %s", e)
            self._can_request_ads = True

    async def show_privacy_options(self):
        """Show privacy options form if required by regulation (GDPR)."""
        if not self._consent_manager:
            return
        try:
            status = (
                await self._consent_manager.get_privacy_options_requirement_status()
            )
            if status == fta.PrivacyOptionsRequirementStatus.REQUIRED:
                await self._consent_manager.show_privacy_options_form()
                self._can_request_ads = await self._consent_manager.can_request_ads()
        except Exception:
            pass

    # ── Ad Controls ───────────────────────────────────────────────────────────

    def get_banner_ad(self) -> ft.Control:
        """Return a banner ad control, or empty container on desktop."""
        if (
            state.is_premium
            or not _HAS_ADS
            or not self._is_mobile()
            or not self._can_request_ads
        ):
            return ft.Container(width=0, height=0)
        try:
            from core import tokens

            ad = fta.BannerAd(
                unit_id=self.banner_id,
                width=tokens.BANNER_WIDTH,
                height=tokens.BANNER_HEIGHT,
                on_error=lambda e: None,
            )
            return ft.Container(
                content=ad,
                width=tokens.BANNER_WIDTH,
                height=tokens.BANNER_HEIGHT,
                alignment=ft.Alignment.CENTER,
            )
        except (
            ValueError,
            TypeError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
        ):
            return ft.Container(width=0, height=0)

    async def preload_interstitial(self, on_close: Callable | None = None):
        """Create and load a fresh interstitial (single-use in flet-ads 1.0)."""
        self._on_close = on_close
        if (
            state.is_premium
            or not _HAS_ADS
            or not self._is_mobile()
            or not self._can_request_ads
        ):
            return
        try:
            self._interstitial_loaded = False
            self._interstitial_shown = False
            self.interstitial = fta.InterstitialAd(
                unit_id=self.interstitial_id,
                on_load=self._handle_loaded,
                on_error=self._handle_error,
                on_close=self._handle_close,
            )
            if self.interstitial not in self.page.services:
                self.page.services.append(self.interstitial)
        except (
            ValueError,
            TypeError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
        ):
            self.interstitial = None

    def _handle_loaded(self, e):
        self._interstitial_loaded = True
        if self._pending_interstitial:
            self._pending_interstitial = False
            self.page.run_task(self._show_loaded)

    def _handle_error(self, e):
        logger.error("InterstitialAd error: %s", getattr(e, "data", e))
        self.interstitial = None
        self._interstitial_loaded = False
        # Nothing will show: let the next trigger queue a fresh load
        # instead of returning "queued" forever.
        self._pending_interstitial = False

    async def _show_loaded(self):
        if self.interstitial is None or self._interstitial_shown:
            return
        try:
            await self.interstitial.show()
            self._interstitial_shown = True
            # The queued impression fired: this is when the gap is spent.
            state.last_interstitial_ts = time.time()
        except (
            ValueError,
            TypeError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
        ) as exc:
            logger.warning("Interstitial show-on-load failed: %s", exc)
            self.interstitial = None
            self._interstitial_loaded = False

    async def _handle_close(self, e):
        self._interstitial_shown = False
        if self._on_close:
            if asyncio.iscoroutinefunction(self._on_close):
                await self._on_close()
            else:
                self._on_close()
        await self.preload_interstitial(on_close=self._on_close)

    async def show_interstitial(self) -> bool:
        """Show the preloaded interstitial; load a fresh one if none is ready.

        InterstitialAd is single-use in flet-ads 1.0, so shown or failed
        instances are replaced. Returns True when an ad is shown or queued to
        show as soon as it finishes loading.
        """
        if (
            state.is_premium
            or not _HAS_ADS
            or not self._is_mobile()
            or not self._can_request_ads
        ):
            return False
        now = time.time()
        if now - state.last_interstitial_ts < self.MIN_INTERSTITIAL_GAP:
            return False
        ad = self.interstitial
        if (
            ad is not None
            and self._interstitial_loaded
            and not self._interstitial_shown
        ):
            try:
                await ad.show()
                self._interstitial_shown = True
                # The gap is spent only by an impression that really fired.
                state.last_interstitial_ts = now
                return True
            except (
                ValueError,
                TypeError,
                OSError,
                RuntimeError,
                ConnectionError,
                ImportError,
            ):
                self.interstitial = None
                self._interstitial_loaded = False
        if self._pending_interstitial:
            # Already queued by an earlier trigger; its show stamps the gap.
            return True
        # Queue a fresh load: it shows automatically once loaded, and
        # _show_loaded stamps the gap then. A load that cannot even start
        # leaves the gap unspent - a no-op must not lock out a real ad.
        self._pending_interstitial = True
        if self.interstitial is None:
            await self.preload_interstitial(self._on_close)
            if self.interstitial is None:
                self._pending_interstitial = False
                return False
        return True

    async def show_rewarded_interstitial(self, on_close: Callable) -> bool:
        """Show a rewarded interstitial ad, triggering on_close when closed.

        Returns False when no ad could be shown, and grants nothing in that
        case. It used to call `on_close` anyway - for premium users, when
        flet_ads is missing, and on mobile web where `_is_mobile()` is
        False - so credits were handed out for an impression nobody saw:
        two every 30 seconds against a 200/day cap, with the cooldown held
        only in memory and cleared by a relaunch. A reward has to be paid
        for by an ad that actually closed.
        """
        if state.is_premium or not _HAS_ADS or not self._is_mobile():
            logger.info("No rewarded ad available - granting nothing")
            # Desktop/no-ads fallback: still call on_close so the UI flow continues
            if asyncio.iscoroutinefunction(on_close):
                await on_close()
            else:
                on_close()
            return False

        try:

            async def _show(e):
                await e.control.show()

            async def _close(e):
                self._active_rewarded_ad = None
                if asyncio.iscoroutinefunction(on_close):
                    await on_close()
                else:
                    on_close()

            self._active_rewarded_ad = fta.InterstitialAd(
                unit_id=self.interstitial_id,
                on_load=lambda e: self.page.run_task(_show, e),
                on_close=lambda e: self.page.run_task(_close, e),
                on_error=lambda e: logger.error(
                    "Rewarded Interstitial error: %s", e.data
                ),
            )
            if self._active_rewarded_ad not in self.page.services:
                self.page.services.append(self._active_rewarded_ad)
            return True
        except (
            ValueError,
            TypeError,
            OSError,
            RuntimeError,
            ConnectionError,
            ImportError,
        ):
            logger.exception("Failed to trigger rewarded interstitial")
            if asyncio.iscoroutinefunction(on_close):
                await on_close()
            else:
                on_close()
            return False

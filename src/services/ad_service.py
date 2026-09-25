"""AdMob service — banner and interstitial ads.

Direct port of Sherlock's production AdService pattern.
Uses test Ad IDs until Play Store launch.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable

import flet as ft

logger = logging.getLogger(__name__)

try:
    import flet as ft
    import flet_ads as fta

    _HAS_ADS = True
except ImportError:
    _HAS_ADS = False


class AdService:
    """Manages AdMob banner and interstitial ads."""

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
        self._on_close: Callable | None = None
        self._active_rewarded_ad = None
        # Single-flight for rewarded ads: while True, new requests are
        # refused instead of stacking another full-screen ad.
        self._rewarded_showing = False
        self._can_request_ads: bool = True
        self._consent_manager = None
        # The gap DDGS/Sherlock enforce between interstitials. Without it a
        # burst of actions (run cell, open files, export notebook) can stack
        # three full-screen ads in a row and the app feels hostile.
        self._last_interstitial_at: float = 0.0
        self.min_interstitial_gap: float = 90.0

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

    def _is_mobile(self) -> bool:
        try:
            return self.page.platform.is_mobile()
        except Exception:
            return False

    def _premium(self) -> bool:
        """Premium removes ads. One condition, checked at every choke point,
        so no new ad surface can forget it."""
        from core.state import state

        return bool(getattr(state, "is_premium", False))

    def _ads_allowed(self) -> bool:
        """The single gate every ad surface goes through."""
        if not _HAS_ADS or not self._is_mobile() or self._premium():
            return False
        return bool(self._can_request_ads)

    def _gap_elapsed(self) -> bool:
        import time as _time

        return (_time.monotonic() - self._last_interstitial_at) >= (
            self.min_interstitial_gap
        )

    # ── Consent Management (UMP) ──────────────────────────────────────────────

    async def gather_consent(self):
        """Run UMP consent flow. Only shows UI in regulated regions (EEA/UK).

        A premium user is never shown the form: premium is resolved before
        this runs, and asking someone who has already paid whether they
        consent to ads they will never see is a bug, not a nicety.
        """
        if not _HAS_ADS or not self._is_mobile() or self._premium():
            self._can_request_ads = not self._premium()
            return
        try:
            self._consent_manager = fta.ConsentManager()
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
            logger.exception("Suppressed exception")

    # ── Ad Controls ───────────────────────────────────────────────────────────

    def get_banner_ad(self) -> ft.Control:
        """Return a banner ad control, or empty container when there is no
        ad to show (desktop, no consent, or premium)."""
        if not self._ads_allowed():
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
        """Pre-load an interstitial ad for later display."""
        self._on_close = on_close
        if not self._ads_allowed():
            # Premium: drop any preloaded instance so a purchase mid-session
            # actually stops the ads instead of leaving one queued.
            self.interstitial = None
            return
        try:
            self.interstitial = fta.InterstitialAd(
                unit_id=self.interstitial_id,
                on_load=lambda e: None,
                on_error=lambda e: logger.error("Interstitial error: %s", e),
                on_close=self._handle_close,
            )
        except Exception as e:
            logger.error("Failed to preload interstitial: %s", e)
            self.interstitial = None

    async def _handle_close(self, e):
        if self._on_close:
            if inspect.iscoroutinefunction(self._on_close):
                await self._on_close()
            else:
                self._on_close()
        await self.preload_interstitial(on_close=self._on_close)

    async def show_interstitial(self) -> bool:
        """Show a preloaded interstitial. Returns True if shown.

        Restocks in ``finally``: the served instance is single-use, and the
        only reload used to happen on the rewarded ad's close — so after
        the first session-create, every later interstitial found an empty
        slot and silently no-opped.

        Held to a minimum gap: a burst of actions must not stack three
        full-screen ads in a row.
        """
        shown = False
        try:
            if self._premium() or not self._gap_elapsed():
                return False
            if self.interstitial:
                import time as _time

                self._last_interstitial_at = _time.monotonic()
                await self.interstitial.show()
                shown = True
            return shown
        except Exception:
            return False
        finally:
            await self.preload_interstitial(on_close=self._on_close)

    async def show_rewarded_interstitial(
        self, on_close: Callable, grant_on_fail: bool = True
    ) -> bool:
        """Show a rewarded ad, running `on_close` when it completes.

        `grant_on_fail` decides what a failed/no-fill ad is worth:

        - True (gated actions like downloads): the action runs anyway —
          no fill is a network outcome, not a user outcome, and the same
          action runs free on desktop.
        - False (credit rewards): nothing is granted. Paying credits for
          an ad that never played would hand out free credits on every
          network hiccup, and the ad never even opened for the user.

        A single-flight guard sits over the whole flow: ten fast taps
        cannot stack ten ads (the bug the owner hit on the phone).
        """
        if self._rewarded_showing:
            return False
        if self._premium() or not _HAS_ADS or not self._is_mobile():
            # No ad platform: gated actions still run. (The credit UI
            # hides itself off mobile, so this branch serves actions only.)
            if inspect.iscoroutinefunction(on_close):
                await on_close()
            else:
                on_close()
            return grant_on_fail

        try:
            # Some mediation adapters fire on_error *and* on_close, or a
            # double-tap races two show() calls on one single-use instance.
            # The gated action (download / export) must run exactly once.
            done = False

            async def _run_action():
                nonlocal done
                if done:
                    return
                done = True
                if inspect.iscoroutinefunction(on_close):
                    await on_close()
                else:
                    on_close()

            async def _show(e):
                await e.control.show()

            async def _close(e):
                self._active_rewarded_ad = None
                self._rewarded_showing = False
                await _run_action()

            async def _failed(e):
                logger.warning(
                    "Rewarded interstitial failed: %s", getattr(e, "data", e)
                )
                self._active_rewarded_ad = None
                self._rewarded_showing = False
                if not grant_on_fail:
                    return  # a credit reward is not paid for an ad that never played
                # Gated action: no fill is a network outcome, not a user
                # outcome — downloads and exports still run.
                await _run_action()

            self._rewarded_showing = True
            self._active_rewarded_ad = fta.InterstitialAd(
                unit_id=self.interstitial_id,
                on_load=lambda e: self.page.run_task(_show, e),
                on_close=lambda e: self.page.run_task(_close, e),
                on_error=lambda e: self.page.run_task(_failed, e),
            )
            return True
        except Exception as err:
            logger.error("Failed to trigger rewarded interstitial: %s", err)
            self._rewarded_showing = False
            if grant_on_fail:
                if inspect.iscoroutinefunction(on_close):
                    await on_close()
                else:
                    on_close()
            return False

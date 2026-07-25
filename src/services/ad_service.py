"""AdMob service — banner and interstitial ads.

Direct port of Sherlock's production AdService pattern.
Uses test Ad IDs until Play Store launch.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

import flet as ft

logger = logging.getLogger(__name__)

try:
    import flet as ft
    import flet_ads as fta
    from flet_ads import base_ad
    from flet_ads.native_ad import NativeAd

    class CollabBannerAd(fta.BannerAd):
        def init(self):
            # Bypass fta.base_ad.BaseAd.init() which has a premature page.platform check
            super(base_ad.BaseAd, self).init()

    class CollabNativeAd(NativeAd):
        def init(self):
            super(base_ad.BaseAd, self).init()
            if self.factory_id is None and self.template_style is None:
                raise ValueError("factory_id or template_style must be set")

    class CollabInterstitialAd(fta.InterstitialAd):
        def init(self):
            super(base_ad.BaseAd, self).init()

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

    def get_banner_ad(self) -> ft.Control:
        """Return a banner ad control, or empty container on desktop."""
        if not _HAS_ADS or not self._is_mobile():
            return ft.Container(width=0, height=0)
        try:
            ad = CollabBannerAd(
                unit_id=self.banner_id,
                width=320,
                height=50,
                on_error=lambda e: None,
            )
            return ft.Container(
                content=ad,
                width=320,
                height=50,
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

    def get_native_ad(self, template_style=None) -> ft.Control:
        """Return a native ad control."""
        if not _HAS_ADS or not self._is_mobile():
            return ft.Container(width=0, height=0)
        try:
            ad = CollabNativeAd(
                unit_id=self.native_id,
                template_style=template_style,
                on_error=lambda e: None,
            )
            return ad
        except Exception as e:
            logger.warning("Failed to load NativeAd: %s", e)
            return ft.Container(width=0, height=0)

    async def preload_interstitial(self, on_close: Callable | None = None):
        """Pre-load an interstitial ad for later display."""
        self._on_close = on_close
        if not _HAS_ADS or not self._is_mobile():
            return
        try:
            new_ad = CollabInterstitialAd(
                unit_id=self.interstitial_id,
                on_load=lambda e: None,
                on_error=lambda e: None,
                on_close=lambda e: self.page.run_task(self._handle_close, e),
            )
            # InterstitialAd is a Service and must be mounted on the page to be
            # displayed. Replace any previously mounted instance so re-preloading
            # (e.g. after an ad closes) does not leak services.
            if (
                self.interstitial is not None
                and self.interstitial in self.page.services
            ):
                self.page.services.remove(self.interstitial)
            self.interstitial = new_ad
            self.page.services.append(self.interstitial)
        except Exception:
            self.interstitial = None

    async def _handle_close(self, e):
        if self._on_close:
            if asyncio.iscoroutinefunction(self._on_close):
                await self._on_close()
            else:
                self._on_close()
        await self.preload_interstitial(on_close=self._on_close)

    async def show_interstitial(self) -> bool:
        """Show a preloaded interstitial. Returns True if shown."""
        if self.interstitial:
            try:
                await self.interstitial.show()
                return True
            except Exception:
                return False
        return False

    async def show_rewarded_interstitial(self, on_close: Callable) -> bool:
        """Show a rewarded interstitial ad, triggering on_close when closed."""
        if not _HAS_ADS or not self._is_mobile():
            if asyncio.iscoroutinefunction(on_close):
                await on_close()
            else:
                on_close()
            return True

        try:

            async def _show(e):
                await e.control.show()

            async def _close(e):
                self._active_rewarded_ad = None
                if asyncio.iscoroutinefunction(on_close):
                    await on_close()
                else:
                    on_close()

            self._active_rewarded_ad = CollabInterstitialAd(
                unit_id=self.interstitial_id,
                on_load=lambda e: self.page.run_task(_show, e),
                on_close=lambda e: self.page.run_task(_close, e),
                on_error=lambda e: logger.error(
                    "Rewarded Interstitial error: %s", e.data
                ),
            )
            return True
        except Exception as err:
            logger.error("Failed to trigger rewarded interstitial: %s", err)
            if asyncio.iscoroutinefunction(on_close):
                await on_close()
            else:
                on_close()
            return False

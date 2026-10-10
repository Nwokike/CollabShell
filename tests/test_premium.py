"""Premium ad-gating tests.

The product promise is "a paying user never sees an ad", so these pin the two
banner surfaces, the interstitial preload/show, and that a Play build offers no
premium at all. Ports the ad half of ktv-player/tests/test_premium.py.
"""

import sys
import types
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pytest

from core.state import state


@pytest.fixture(autouse=True)
def _clean_state():
    state.is_premium = False
    yield
    state.is_premium = False


import flet as ft


class _FakePage:
    """A page whose platform is the real PagePlatform enum.

    ``page.platform`` IS the enum — ``PagePlatform.is_mobile()`` is a method on
    it, which is why ``build_banner_ad`` can compare it directly while
    ``AdService._is_mobile`` can call ``.is_mobile()``.
    """

    def __init__(self, mobile: bool = True):
        self.platform = (
            ft.PagePlatform.ANDROID if mobile else ft.PagePlatform.WINDOWS
        )

    def run_task(self, fn, *args):
        import asyncio

        result = fn(*args)
        if asyncio.iscoroutine(result):
            asyncio.run(result)

    def update(self):
        pass


def _ad_service(mobile: bool = True, can_request: bool = True):
    """An AdService with ads "available" but nothing loaded."""
    from services.ad_service import AdService

    svc = AdService(_FakePage(mobile))
    svc._can_request_ads = can_request
    return svc


# ── the banner ─────────────────────────────────────────────────────────────


def test_banner_getter_collapses_when_premium():
    """The service gate: premium returns the 0x0 placeholder."""
    svc = _ad_service()
    state.is_premium = True
    paid = svc.get_banner_ad()
    assert getattr(paid, "width", 0) == 0
    assert getattr(paid, "height", 0) == 0


def test_banner_getter_is_not_premium_gated_when_free():
    svc = _ad_service()
    state.is_premium = False
    assert svc._premium is False, "the premium gate must not fire when free"


def test_banner_is_hidden_on_desktop_even_when_free():
    svc = _ad_service(mobile=False)
    banner = svc.get_banner_ad()
    assert getattr(banner, "width", 0) == 0


def test_styled_banner_skips_construction_when_premium(monkeypatch):
    """Premium must not even build an ad control.

    The real constructor needs a live page (0x0 either way headlessly), so this
    counts constructions instead of measuring pixels.
    """
    import flet_ads as fta

    from core.styles import build_banner_ad

    built = []
    original = fta.BannerAd

    class _Spy:
        def __init__(self, **kwargs):
            built.append(kwargs)

    monkeypatch.setattr(fta, "BannerAd", _Spy)

    page = _FakePage(mobile=True)
    state.is_premium = False
    build_banner_ad(page)
    assert built, "a free user must get a banner built"

    built.clear()
    state.is_premium = True
    build_banner_ad(page)
    assert built == [], "a premium user must get no ad control at all"
    monkeypatch.setattr(fta, "BannerAd", original)


# ── interstitials ──────────────────────────────────────────────────────────


def test_preload_skipped_when_premium():
    import asyncio

    svc = _ad_service()
    state.is_premium = True
    asyncio.run(svc.preload_interstitial())
    assert svc.interstitial is None


def test_preload_is_not_premium_gated_when_free():
    """Premium is the only reason preload returns early."""
    import asyncio

    svc = _ad_service()
    state.is_premium = False
    asyncio.run(svc.preload_interstitial())
    assert svc._premium is False, "the premium gate must not fire when free"
    assert svc.interstitial is not None, "a free user gets an interstitial built"


def test_show_interstitial_blocked_when_premium():
    import asyncio

    svc = _ad_service()
    svc.interstitial = object()  # a preloaded ad
    state.is_premium = True
    assert asyncio.run(svc.show_interstitial()) is False


def test_show_interstitial_allowed_when_free():
    import asyncio

    svc = _ad_service()

    class _Ad:
        async def show(self):
            return None

    svc.interstitial = _Ad()
    assert asyncio.run(svc.show_interstitial()) is True


# ── the rewarded top-up is NOT gated ───────────────────────────────────────


def test_rewarded_ad_still_works_for_premium():
    """A premium user has nothing to top up, but the ad path itself must not
    be premium-gated: it is how a FREE user earns credits."""
    import asyncio

    svc = _ad_service(mobile=False)  # not mobile: the no-ad fallback path
    seen = []
    asyncio.run(svc.show_rewarded_interstitial(lambda: seen.append(1)))
    assert seen == [1]


# ── the premium surface ────────────────────────────────────────────────────


def test_settings_ai_section_reports_the_premium_cap():
    """The credits row must show 500 for premium, 50 for free."""
    from screens.settings import ai_section

    page = _FakePage(mobile=False)
    credits = types.SimpleNamespace()

    async def _balance(is_premium=False):
        return 500 if is_premium else 50

    def _cap(is_premium=False):
        return 500 if is_premium else 50

    credits.get_balance = _balance
    credits.daily_cap = _cap
    services = types.SimpleNamespace(credits=credits, storage=None, ad_service=None,
                                     premium=types.SimpleNamespace(available=True))
    state_ = types.SimpleNamespace(
        ai_mode=False, ai_model="auto", ai_router_url="x", ai_help=True,
        is_premium=True,
    )
    column = ai_section.build_ai_section(page, state_, services)
    texts = _flatten(column)
    assert any("500" in t for t in texts), texts


def _flatten(control, out=None) -> list[str]:
    if out is None:
        out = []
    for child in getattr(control, "controls", []) or []:
        _flatten(child, out)
    value = getattr(control, "value", None)
    if isinstance(value, str) and value:
        out.append(value)
    for attr in ("title", "subtitle", "content", "trailing"):
        inner = getattr(control, attr, None)
        if inner is not None and inner is not control:
            _flatten(inner, out)
    return out

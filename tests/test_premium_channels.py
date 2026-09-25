"""The two premium channels must not be able to vouch for each other.

A Play purchase is cached as a plain flag and re-confirmed with the store
every launch. A Kiri license is proved by a signed token. If the flag were
accepted as a general premium unlock, anyone who could write one boolean
into storage would own Premium — so the flag is only ever read for the
channel that wrote it.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ai.session import AiSession
from core import constants
from core.license_crypto import TokenError, verify_token
from core.state import state
from services import license_service as license
from services.premium_service import PremiumService


class FakeStorage:
    def __init__(self, seed=None):
        self.d: dict = dict(seed or {})

    async def get(self, k, default=None):
        return self.d.get(k, default)

    async def set(self, k, v):
        self.d[k] = v


class FakePage:
    class _Platform:
        @staticmethod
        def is_mobile():
            return False

    platform = _Platform()

    def __init__(self):
        self.services: list = []


def _service(seed=None) -> PremiumService:
    return PremiumService(FakePage(), FakeStorage(seed))


@pytest.fixture(autouse=True)
def clean_state():
    state.is_premium = False
    state.premium_source = ""
    state.premium_product = ""
    state.premium_offline = False
    yield
    state.is_premium = False
    state.premium_source = ""
    state.premium_product = ""


# ── What grants Premium at all ──────────────────────────────────────────
# KTV Player's model: one backend (the Kiri Worker) and a signed token.
# A bare flag in storage is not proof of anything, and the Play-channel
# build clears Premium instead of trusting even a token.


def test_a_bare_flag_never_grants():
    service = _service(
        {constants.STORAGE_PREMIUM: "true", constants.STORAGE_PREMIUM_SOURCE: "play"}
    )
    asyncio.run(service.load_local())
    assert state.is_premium is False


def test_a_flag_with_no_source_grants_nothing():
    asyncio.run(_service({constants.STORAGE_PREMIUM: "true"}).load_local())
    assert state.is_premium is False


def test_no_stored_token_means_free():
    asyncio.run(_service().load_local())
    assert state.is_premium is False


def test_the_play_build_clears_premium_instead_of_trusting_it(monkeypatch):
    """A token left over from a direct install must never unlock the Play
    build — that rule is why load_local clears rather than reads."""
    from core import build_channel

    monkeypatch.setattr(build_channel, "CHANNEL", "play")
    service = _service({constants.STORAGE_PREMIUM: "true"})
    asyncio.run(service.load_local())
    assert state.is_premium is False
    assert service.backend == "none"
    assert service.available is False


def test_the_service_is_the_ktv_surface_not_billing():
    """Play Billing is not part of this build: no buy/restore_purchases, and
    the four Worker methods are the entire public surface."""
    service = _service()
    assert service.backend == "kiri"
    assert service.available is True
    for method in (
        "kiri_catalog",
        "kiri_checkout",
        "kiri_restore",
        "kiri_check_status",
    ):
        assert callable(getattr(service, method)), method
    for method in ("buy", "restore_purchases", "query_products"):
        assert not hasattr(service, method), method


# ── The Kiri token ─────────────────────────────────────────────────────


def test_a_signed_token_grants_and_records_the_channel():
    entitlement = license.Entitlement(
        status="active", product="lifetime", scope="universal"
    )
    assert asyncio.run(license.apply_entitlement(entitlement)) is True
    assert state.is_premium is True
    assert state.premium_source == "kiri"
    assert state.premium_product == "lifetime"


def test_an_unreachable_server_never_removes_premium():
    asyncio.run(
        license.apply_entitlement(license.Entitlement(status="active", product="y"))
    )
    assert state.is_premium is True
    # A network failure surfaces as `unknown`, which is not a ruling.
    granted = asyncio.run(
        license.apply_entitlement(license.Entitlement(status="unknown"))
    )
    assert granted is False
    assert state.is_premium is True, "a flaky network must not cost a paying user"


def test_an_authoritative_revocation_does_remove_premium():
    asyncio.run(
        license.apply_entitlement(license.Entitlement(status="active", product="y"))
    )
    granted = asyncio.run(
        license.apply_entitlement(license.Entitlement(status="revoked"))
    )
    assert granted is False
    assert state.is_premium is False


def test_an_expired_license_does_remove_premium():
    asyncio.run(
        license.apply_entitlement(license.Entitlement(status="active", product="y"))
    )
    asyncio.run(license.apply_entitlement(license.Entitlement(status="expired")))
    assert state.is_premium is False


def test_grace_still_keeps_access():
    granted = asyncio.run(
        license.apply_entitlement(license.Entitlement(status="grace", product="m"))
    )
    assert granted is True
    assert state.is_premium is True


def test_an_offline_token_is_marked_offline():
    """A locally verified token grants, but the user can see the server has
    not confirmed it this session."""

    async def run():
        entitlement = license.Entitlement(
            status="active", product="lifetime", offline=True
        )
        await license.apply_entitlement(entitlement)

    asyncio.run(run())
    assert state.is_premium is True
    assert state.premium_offline is True


def test_a_forged_signature_is_rejected_by_the_crypto_layer():
    with pytest.raises(TokenError):
        verify_token(f"v1.e30.{'A' * 86}", license.APP_ID)


def test_a_forged_token_is_never_cached_as_entitlement():
    async def run():
        storage = FakeStorage()
        await storage.set(constants.STORAGE_LICENSE_TOKEN, f"v1.eyJ9.{'A' * 86}")
        assert await license.cached_entitlement(storage) is None
        assert await storage.get(constants.STORAGE_LICENSE_TOKEN) is not None

    asyncio.run(run())
    assert state.is_premium is False


# ── Where the channel may exist — the build-time marker decides ────────
# No platform branch, no runtime opt-in: the artifact carries the policy,
# exactly like KTV's core/channel.py.


class AndroidPage(FakePage):
    class _Platform:
        @staticmethod
        def is_mobile():
            return True

    platform = _Platform()


def _store():
    class _Store:
        async def get(self, k, default=None):
            return None

        async def set(self, k, v):
            return None

    return _Store()


def _section_labels(page, services) -> set:
    """Every visible string on the built Premium section."""
    import flet as ft

    from screens.settings.premium_section import build_premium_section

    labels: set = set()

    def walk(control):
        if isinstance(control, ft.Text):
            labels.add(control.value or "")
        # Buttons carry their label as a plain string `content`.
        content = getattr(control, "content", None)
        if isinstance(content, str):
            labels.add(content)
        if isinstance(control, ft.ListTile):
            for slot in (control.title, control.subtitle):
                if isinstance(slot, str):
                    labels.add(slot)
                elif isinstance(slot, ft.Text):
                    labels.add(slot.value or "")
        for attr in ("controls", "content", "leading", "trailing"):
            child = getattr(control, attr, None)
            if isinstance(child, (list, tuple)):
                for item in child:
                    walk(item)
            elif isinstance(child, ft.BaseControl):
                walk(child)

    walk(build_premium_section(page, None, services))
    return labels


def test_the_marker_decides_not_the_platform(monkeypatch):
    from core import build_channel

    monkeypatch.setattr(build_channel, "CHANNEL", "direct")
    assert license.is_available() is True
    assert license.is_available(AndroidPage()) is True, "a direct APK sells Kiri"
    assert license.is_available(FakePage()) is True

    monkeypatch.setattr(build_channel, "CHANNEL", "play")
    assert license.is_available() is False
    assert license.is_available(AndroidPage()) is False
    assert license.is_available(FakePage()) is False


def test_the_play_build_never_shows_any_purchase_ui(monkeypatch):
    """The Play AAB is free-only: no purchase row exists in any state."""
    from core import build_channel
    from state.service_ctx import Services

    class _PlayPremium:
        available = False
        backend = "none"

        async def kiri_catalog(self):
            return []

    monkeypatch.setattr(build_channel, "CHANNEL", "play")
    services = Services(ai=AiSession(), storage=_store(), premium=_PlayPremium())
    labels = _section_labels(AndroidPage(), services)
    for forbidden in (
        "Go Premium",
        "Pay directly",
        "Recovery ID",
        "Restore a purchase",
        "Check status",
        "Buy with Google Play",
        "Google Play payment not working?",
    ):
        assert not any(forbidden in t for t in labels), forbidden
    # What the build does offer is the free tier: credits and ads.
    assert any("credits" in t.lower() for t in labels)


def test_a_direct_apk_shows_the_kiri_channel(monkeypatch):
    """Direct APKs sell through Kiri outright — no opt-in, no escape hatch."""
    from core import build_channel
    from state.service_ctx import Services

    monkeypatch.setattr(build_channel, "CHANNEL", "direct")
    services = Services(ai=AiSession(), storage=_store(), premium=_service())
    labels = _section_labels(AndroidPage(), services)
    assert any("Pay directly" in t for t in labels)
    assert any("Recovery ID" in t for t in labels)
    assert any("Restore a purchase" in t for t in labels)
    assert any("Check status" in t for t in labels)
    # The one thing that must never return: external-payment rows about Google.
    assert not any("Google Play payment not working" in t for t in labels)
    assert not any("Buy with Google Play" in t for t in labels)


def test_desktop_shows_the_same_channel(monkeypatch):
    from core import build_channel
    from state.service_ctx import Services

    monkeypatch.setattr(build_channel, "CHANNEL", "direct")
    services = Services(ai=AiSession(), storage=_store(), premium=_service())
    labels = _section_labels(FakePage(), services)
    assert any("Pay directly" in t for t in labels)
    assert not any("Buy with Google Play" in t for t in labels)


# ── Renewal guard ──────────────────────────────────────────────────────


def _grant(status: str, paid_through=None):
    return asyncio.run(
        license.apply_entitlement(
            license.Entitlement(
                status=status, product="monthly", paid_through=paid_through
            )
        )
    )


def test_grace_grants_but_is_named_honestly():
    assert _grant("grace") is True
    assert state.is_premium is True
    assert state.premium_status == "grace"


def test_active_records_the_status_and_expiry():
    assert _grant("active", paid_through=1750000000) is True
    assert state.premium_status == "active"
    assert state.premium_paid_through == 1750000000


def test_expiry_records_the_status_so_the_card_can_say_so():
    _grant("active")
    assert _grant("expired") is False
    assert state.is_premium is False
    assert state.premium_status == "expired"


def test_refund_records_the_status():
    _grant("active")
    assert _grant("revoked") is False
    assert state.premium_status == "revoked"


def test_an_unknown_check_leaves_the_recorded_status_alone():
    _grant("active")
    assert _grant("unknown") is False
    assert state.is_premium is True
    assert state.premium_status == "active"

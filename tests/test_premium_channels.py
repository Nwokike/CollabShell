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


# ── The Play cache ─────────────────────────────────────────────────────


def test_a_play_purchase_survives_a_restart_instantly():
    service = _service(
        {
            constants.STORAGE_PREMIUM: "true",
            constants.STORAGE_PREMIUM_SOURCE: "play",
            constants.STORAGE_PREMIUM_PRODUCT: "premium_unlock",
        }
    )
    asyncio.run(service.load_local())
    assert state.is_premium is True
    assert state.premium_source == "play"


def test_a_kiri_license_is_never_granted_by_the_play_flag():
    """The rule the audit caught: `premium=true` is a Play cache, not a
    Kiri proof. A Kiri entitlement is only ever granted by a token."""
    service = _service(
        {
            constants.STORAGE_PREMIUM: "true",
            constants.STORAGE_PREMIUM_SOURCE: "kiri",
            constants.STORAGE_PREMIUM_PRODUCT: "lifetime",
        }
    )
    asyncio.run(service.load_local())
    assert state.is_premium is False
    assert state.premium_source == ""


def test_a_flag_with_no_source_grants_nothing():
    """A bare `premium=true` with no channel is not evidence of anything."""
    service = _service({constants.STORAGE_PREMIUM: "true"})
    asyncio.run(service.load_local())
    assert state.is_premium is False


def test_no_stored_flag_means_free():
    service = _service()
    asyncio.run(service.load_local())
    assert state.is_premium is False


def test_desktop_builds_attach_no_billing_service():
    """`in_app_purchase` has no desktop platform; attaching it there would
    stall every call for the full timeout."""
    service = _service()
    assert service.available is False
    assert service.billing is None
    # ...and buying is a clean False, not an exception.
    assert asyncio.run(service.buy()) is False


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

"""Kiri License service tests, against a scripted Worker.

Ports ktv-player/tests/test_kiri_license.py. The fixtures are real WebCrypto
P-256 signatures for this app's id (tests/license_fixtures.py), so the token
paths are exercised end to end without a live Worker.
"""

import asyncio
import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_spec = importlib.util.spec_from_file_location(
    "license_fixtures", _HERE / "license_fixtures.py"
)
_fixtures = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixtures)
PUBLIC_KEY = _fixtures.PUBLIC_KEY
TOKENS = _fixtures.TOKENS

import httpx

from services import license_service as ls
from services.license_service import (
    KiriLicenseService,
    LicenseUnavailable,
)

APP = "ng.kiri.collabshell"


def _fresh():
    """A service wired to an in-memory store and a scripted transport."""
    store: dict[str, str] = {}

    async def _get(key, default=None):
        return store.get(key, default)

    async def _set(key, value):
        store[key] = str(value)

    storage = MagicMock()
    storage.get = AsyncMock(side_effect=_get)
    storage.set = AsyncMock(side_effect=_set)
    svc = KiriLicenseService(storage)
    # The fixtures are signed by a throwaway keypair, so verification uses
    # that key rather than the production Worker key.
    svc.public_key = PUBLIC_KEY
    return svc, store


def _client(handler):
    """Patch the service's http seam to a mock transport."""
    def factory(timeout=None):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    return factory


def _patch_http(monkeypatch, handler):
    monkeypatch.setattr(ls, "_http_client", _client(handler))


def _response(body, status_code=200):
    """A real httpx.Response: MockTransport requires one, and a MagicMock
    there makes httpx try to `await` it."""
    return httpx.Response(status_code=status_code, json=body)


def _raw_response(text, status_code=200):
    """A non-JSON body, for the invalid-JSON paths."""
    return httpx.Response(status_code=status_code, text=text)


def _run(coro):
    return asyncio.run(coro)


# ── catalog ────────────────────────────────────────────────────────────────


def test_catalog_parses_products_and_prices(monkeypatch):
    def handler(request):
        assert request.url.path.endswith("/catalog")
        return _response(
            {
                "products": [
                    {"id": "monthly", "amount": 4.99, "currency": "USD",
                     "kind": "recurring", "description": "Renews monthly"},
                    {"id": "lifetime", "amount": 49.99, "currency": "USD"},
                ]
            }
        )

    _patch_http(monkeypatch, handler)
    svc, _store = _fresh()
    products = _run(svc.fetch_catalog())
    assert [p.id for p in products] == ["monthly", "lifetime"]
    assert products[0].price_label == "$4.99 USD"
    assert products[1].price_label == "$49.99 USD"


def test_catalog_is_cached_between_calls(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return _response({"products": [{"id": "a", "amount": 1, "currency": "USD"}]})

    _patch_http(monkeypatch, handler)
    svc, _ = _fresh()
    _run(svc.fetch_catalog())
    _run(svc.fetch_catalog())
    assert len(calls) == 1, "second call must hit the cache"
    # force bypasses it
    _run(svc.fetch_catalog(force=True))
    assert len(calls) == 2


def test_catalog_failure_is_explicit(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("offline")

    _patch_http(monkeypatch, handler)
    svc, _ = _fresh()
    try:
        _run(svc.fetch_catalog())
        raise AssertionError("should have raised")
    except LicenseUnavailable as ex:
        assert "Could not reach" in str(ex)


def test_catalog_non_dict_payload_rejected(monkeypatch):
    _patch_http(monkeypatch, lambda r: _response([1, 2, 3]))
    svc, _ = _fresh()
    try:
        _run(svc.fetch_catalog(force=True))
        raise AssertionError("should have raised")
    except LicenseUnavailable as ex:
        assert "invalid response" in str(ex)


def test_catalog_bad_amount_rejected(monkeypatch):
    _patch_http(
        monkeypatch,
        lambda r: _response({"products": [{"id": "x", "amount": "free"}]}),
    )
    svc, _ = _fresh()
    try:
        _run(svc.fetch_catalog(force=True))
        raise AssertionError("should have raised")
    except LicenseUnavailable as ex:
        assert "Invalid product pricing" in str(ex)


def test_price_label_handles_other_currencies():
    from services.license_service import LicenseProduct

    assert LicenseProduct("a", 1500, "NGN", "", "").price_label == "₦1,500 NGN"
    assert LicenseProduct("b", 9.5, "EUR", "", "").price_label == "€9.5 EUR"
    assert LicenseProduct("c", 10, "GBP", "", "").price_label == "10 GBP"


# ── checkout ───────────────────────────────────────────────────────────────


def test_checkout_posts_the_app_and_product_and_saves_recovery_id(monkeypatch):
    seen = {}

    def handler(request):
        seen["body"] = request.read().decode()
        return _response(
            {
                "recovery_id": "KIRI-L-123",
                "checkout_url": "https://pay.example/abc",
                "product": "monthly",
                "amount": 4.99,
                "currency": "USD",
            }
        )

    import json as _json

    _patch_http(monkeypatch, handler)
    svc, store = _fresh()
    checkout = _run(svc.checkout("monthly", "User@Example.com"))
    assert checkout.checkout_url == "https://pay.example/abc"
    # Email is normalised, and the app id is ours.
    body = _json.loads(seen["body"])
    assert body["app_id"] == "ng.kiri.collabshell"
    assert body["product_id"] == "monthly"
    assert body["email"] == "user@example.com"
    # Recovery ID persisted immediately — the only way back after a data wipe.
    assert store["kiri_recovery_id"] == "KIRI-L-123"


def test_checkout_reports_the_worker_message(monkeypatch):
    _patch_http(
        monkeypatch,
        lambda r: _response({"message": "email_required"}, status_code=400),
    )
    svc, _ = _fresh()
    try:
        _run(svc.checkout("monthly", "a@b.com"))
        raise AssertionError("should have raised")
    except LicenseUnavailable as ex:
        assert str(ex) == "email_required"
        assert ex.status_code == 400
        # 400 is transient, never a revocation.
        assert ex.is_refusal is False


def test_checkout_rejects_invalid_email_without_network(monkeypatch):
    called = []

    def handler(request):
        called.append(request)
        return _response({})

    _patch_http(monkeypatch, handler)
    svc, _ = _fresh()
    for bad in ("", "   ", "nope"):
        try:
            _run(svc.checkout("monthly", bad))
            raise AssertionError("should have raised")
        except LicenseUnavailable as ex:
            assert "email" in str(ex).lower()
    assert called == [], "no network on a validation failure"


def test_checkout_rejects_an_incomplete_order(monkeypatch):
    _patch_http(monkeypatch, lambda r: _response({"recovery_id": "X"}))
    svc, _ = _fresh()
    try:
        _run(svc.checkout("monthly", "a@b.com"))
        raise AssertionError("should have raised")
    except LicenseUnavailable as ex:
        assert "incomplete order" in str(ex)


# ── restore / status ───────────────────────────────────────────────────────


def _restore_handler(token_name, status="active"):
    def handler(request):
        return _response(
            {"status": status, "product": "lifetime", "token": TOKENS[token_name]}
        )

    return handler


def _token_status(name):
    """The status claim a fixture was minted with."""
    import base64
    import json

    payload = TOKENS[name].split(".")[1]
    raw = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    return json.loads(raw)["status"]


def test_restore_with_a_verified_token_unlocks_premium(monkeypatch):
    _patch_http(monkeypatch, _restore_handler("LIFETIME"))
    svc, store = _fresh()
    status = _run(svc.restore("KIRI-L-1"))
    assert status.unlocks is True
    assert status.effective_unlocks(svc.claims) is True
    assert svc.unlocked is True
    assert store["kiri_token"] == TOKENS["LIFETIME"]


def test_restore_accepts_a_token_stamped_for_another_kiri_app(monkeypatch):
    """The licence is universal: Worker scopeAllows returns true for any app.

    The Worker re-mints a token with the REQUESTING app's id on every restore,
    and every Kiri product carries scope "universal", so a token stamped for
    ktv-player is a valid entitlement here. Buy once, use it in every app.
    """
    _patch_http(monkeypatch, _restore_handler("OTHER_APP"))
    svc, store = _fresh()
    status = _run(svc.restore("KIRI-L-1"))
    assert status.unlocks is True
    assert svc.unlocked is True
    assert store["kiri_token"] == TOKENS["OTHER_APP"]


def test_restore_rejects_a_token_scoped_to_another_app(monkeypatch):
    """A per-app scope list is the one thing that gates."""
    _patch_http(monkeypatch, _restore_handler("SCOPED_OUT"))
    svc, store = _fresh()
    try:
        _run(svc.restore("KIRI-L-1"))
        raise AssertionError("should have raised")
    except LicenseUnavailable as ex:
        assert "could not verify" in str(ex)
    assert svc.unlocked is False
    assert store.get("kiri_token") in (None, "")


def test_restore_of_a_revoked_license_does_not_unlock(monkeypatch):
    """A revoked token is refused at verification, not merely "not unlocking":
    `verify_token` rejects any status outside active/grace, so the service
    never gets as far as caching it."""
    _patch_http(monkeypatch, _restore_handler("REVOKED", _token_status("REVOKED")))
    svc, store = _fresh()
    try:
        _run(svc.restore("KIRI-L-1"))
        raise AssertionError("should have raised")
    except LicenseUnavailable as ex:
        assert "could not verify" in str(ex)
    assert svc.unlocked is False
    # Nothing was cached, and any previous token was cleared.
    assert store.get("kiri_token") == ""


def test_expired_token_is_rejected(monkeypatch):
    _patch_http(monkeypatch, _restore_handler("EXPIRED", _token_status("EXPIRED")))
    svc, _ = _fresh()
    try:
        _run(svc.restore("KIRI-L-1"))
        raise AssertionError("should have raised")
    except LicenseUnavailable:
        pass
    assert svc.unlocked is False


def test_refresh_without_a_saved_license_is_a_no_op(monkeypatch):
    called = []

    def handler(request):
        called.append(request)
        return _response({})

    _patch_http(monkeypatch, handler)
    svc, _ = _fresh()
    assert _run(svc.refresh()) is None
    assert called == []


def test_restore_requires_a_recovery_id():
    svc, _ = _fresh()
    try:
        _run(svc.restore("   "))
        raise AssertionError("should have raised")
    except LicenseUnavailable as ex:
        assert "recovery ID" in str(ex)


# ── cached token (the offline path) ────────────────────────────────────────


def test_cached_token_unlocks_without_a_network(monkeypatch):
    _patch_http(monkeypatch, lambda r: (_ for _ in ()).throw(AssertionError("no net")))
    svc, store = _fresh()
    store["kiri_token"] = TOKENS["LIFETIME"]
    assert _run(svc.apply_cached_token()) is True
    assert svc.unlocked is True


def test_expired_cached_token_does_not_unlock(monkeypatch):
    _patch_http(monkeypatch, lambda r: (_ for _ in ()).throw(AssertionError("no net")))
    svc, store = _fresh()
    store["kiri_token"] = TOKENS["EXPIRED"]
    assert _run(svc.apply_cached_token()) is False
    assert svc.unlocked is False


def test_no_cached_token_is_not_an_error(monkeypatch):
    _patch_http(monkeypatch, lambda r: (_ for _ in ()).throw(AssertionError("no net")))
    svc, _ = _fresh()
    assert _run(svc.apply_cached_token()) is False


def test_cached_rejection_clears_the_disk_token(monkeypatch):
    """A forged token must not sit on disk failing every boot."""
    _patch_http(monkeypatch, lambda r: (_ for _ in ()).throw(AssertionError("no net")))
    svc, store = _fresh()
    store["kiri_token"] = "v1.garbage.garbage"
    assert _run(svc.apply_cached_token()) is False
    assert store["kiri_token"] == ""


def test_a_lapsed_cached_license_drops_premium(monkeypatch):
    _patch_http(monkeypatch, lambda r: (_ for _ in ()).throw(AssertionError("no net")))
    svc, store = _fresh()
    store["kiri_token"] = TOKENS["LIFETIME"]
    assert _run(svc.apply_cached_token()) is True
    store["kiri_token"] = TOKENS["EXPIRED"]
    assert _run(svc.apply_cached_token()) is False


# ── refusals, transients, retries ──────────────────────────────────────────


def test_refusal_clears_the_disk_token(monkeypatch):
    _patch_http(monkeypatch, lambda r: _response({}, status_code=403))
    svc, store = _fresh()
    store["kiri_token"] = TOKENS["LIFETIME"]
    store["kiri_recovery_id"] = "KIRI-L-1"
    try:
        _run(svc.restore("KIRI-L-1"))
        raise AssertionError("should have raised")
    except LicenseUnavailable as ex:
        assert ex.is_refusal is True
        assert ex.status_code == 403
    assert store["kiri_token"] == ""
    assert svc.unlocked is False


def test_400_is_transient_not_refusal(monkeypatch):
    """A 400 must never revoke a real license."""
    _patch_http(monkeypatch, lambda r: _response({}, status_code=400))
    svc, store = _fresh()
    store["kiri_token"] = TOKENS["LIFETIME"]
    # Unlock first from the cache, then let the refresh 400.
    _run(svc.apply_cached_token())
    assert svc.unlocked is True
    try:
        _run(svc.restore("KIRI-L-1"))
        raise AssertionError("should have raised")
    except LicenseUnavailable as ex:
        assert ex.is_refusal is False
    assert svc.unlocked is True
    assert store["kiri_token"] == TOKENS["LIFETIME"]


def test_transient_failure_retries_once_then_succeeds(monkeypatch):
    attempts = []

    def handler(request):
        attempts.append(1)
        if len(attempts) == 1:
            raise httpx.TimeoutException("dropped")
        return _response({"status": "active", "token": TOKENS["LIFETIME"]})

    _patch_http(monkeypatch, handler)
    svc, _ = _fresh()
    result = _run(svc.restore("KIRI-L-1"))
    assert len(attempts) == 2, "one immediate retry"
    assert result.unlocks is True


def test_double_transient_failure_does_not_store_or_revoke(monkeypatch):
    _patch_http(monkeypatch, lambda r: (_ for _ in ()).throw(httpx.TimeoutException("x")))
    svc, store = _fresh()
    store["kiri_token"] = TOKENS["LIFETIME"]
    store["kiri_recovery_id"] = "KIRI-L-1"
    try:
        _run(svc.restore("KIRI-L-1"))
        raise AssertionError("should have raised")
    except LicenseUnavailable:
        pass
    # Neither store nor revoke: the next boot retries from the cached token.
    assert store["kiri_token"] == TOKENS["LIFETIME"]


def test_no_plain_premium_flag_is_ever_written(monkeypatch):
    """Premium lives in a signed token, never a client-side boolean on disk."""
    _patch_http(monkeypatch, _restore_handler("LIFETIME"))
    svc, store = _fresh()
    _run(svc.restore("KIRI-L-1"))
    assert "premium" not in store
    assert "is_premium" not in store
    assert set(store) == {"kiri_recovery_id", "kiri_token", "kiri_product"}

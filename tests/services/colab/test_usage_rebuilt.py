"""Tests for the rebuilt usage pipeline (kwarg-free fetch, context cache).

Mirrors tests/services/colab/test_session_ops.py patterns (MagicMock State,
asyncio.run, patch colab_cli.common.State) + notebook-tabs tmp-dir service.
"""

import asyncio
import json
import sys
import time
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

sys.path.insert(0, "src")

from services import usage_cache
from services.colab import usage_ops


def _info(balance=12.34, rate=1.23, count=2):
    return NS(
        paid_compute_units_balance=balance,
        consumption_rate_hourly=rate,
        assignments_count=count,
    )


def _state_with(info=None, exc=None):
    st = MagicMock()
    client = MagicMock()
    if exc is not None:
        client.get_consumption_user_info = MagicMock(side_effect=exc)
    else:
        client.get_consumption_user_info = MagicMock(return_value=info)
    st.client = client
    return st


class FakeStorage:
    def __init__(self):
        self.data = {}

    async def get(self, key, default=None):
        return self.data.get(key, default)

    async def set(self, key, value):
        self.data[key] = value if isinstance(value, str) else str(value)

    async def delete(self, key):
        self.data.pop(key, None)


def _run(coro):
    return asyncio.run(coro)


def _authed(authenticated=True, online=True):
    return patch(
        "core.state.state",
        NS(is_authenticated=authenticated, is_online=online),
    )


def test_upstream_signature_takes_no_kwargs():
    """Live-signature guard: the method takes only self. Never pass timeout=
    (or any kwarg) again — that TypeError killed every fetch."""
    import inspect

    from colab_cli.client import Client

    params = list(inspect.signature(Client.get_consumption_user_info).parameters)
    assert params == ["self"], params


def test_fetch_mapping_and_precision():
    st = _state_with(_info())

    async def _online():
        return None

    svc_colab = NS(_ensure_online=_online)
    with (
        _authed(True, True),
        patch("colab_cli.common.State", side_effect=lambda: st),
    ):
        result = _run(usage_ops.get_usage_impl(svc_colab, "oauth2"))

    assert result["balance"] == 12.34
    assert result["rate"] == 1.23
    assert result["assignments"] == 2
    assert result["cached"] is False
    assert result["reason"] == "ok"
    # Kwarg-free call.
    _, kwargs = st.client.get_consumption_user_info.call_args
    assert kwargs == {}


def test_reason_matrix_signed_out_offline():
    svc = NS()
    with _authed(False, True):
        assert _run(usage_ops.get_usage_impl(svc)) is None
    with _authed(True, False):
        assert _run(usage_ops.get_usage_impl(svc)) is None
    # With fallback dicts, reasons flow through.
    fb = {"balance": 1.0, "rate": 0.5, "assignments": 1}
    with _authed(False, True):
        r = _run(usage_ops.get_usage_impl(svc, cached_fallback=fb))
        assert r["reason"] == "signed-out" and r["cached"] is True
    with _authed(True, False):
        r = _run(usage_ops.get_usage_impl(svc, cached_fallback=fb))
        assert r["reason"] == "offline" and r["cached"] is True


def test_fetch_failure_returns_fallback_or_none():
    svc = NS()
    st = _state_with(exc=RuntimeError("boom"))
    with (
        _authed(True, True),
        patch("colab_cli.common.State", side_effect=lambda: st),
    ):
        assert _run(usage_ops.get_usage_impl(svc)) is None
        fb = {"balance": 3.0, "rate": 0.25, "assignments": 0}
        r = _run(usage_ops.get_usage_impl(svc, cached_fallback=fb))
        assert r["reason"] == "fetch-failed" and r["balance"] == 3.0


def test_cache_write_read_roundtrip_and_ttl():
    from core import constants

    storage = FakeStorage()
    fresh = {
        "balance": 5.0,
        "rate": 1.0,
        "assignments": 1,
        "fetched_at": time.time(),
    }
    _run(usage_cache.write_cached_usage(storage, fresh))
    assert constants.STORAGE_USAGE_CACHE in storage.data
    cached = _run(usage_cache.read_cached_usage(storage))
    assert usage_cache.is_fresh(cached) is True
    assert cached["balance"] == 5.0
    # Backdate beyond TTL → stale.
    storage.data[constants.STORAGE_USAGE_UPDATED_AT] = str(time.time() - 100000)
    stale = _run(usage_cache.read_cached_usage(storage))
    assert usage_cache.is_fresh(stale) is False


def test_read_through_prefers_fresh_cache():
    from core import constants

    storage = FakeStorage()
    storage.data[constants.STORAGE_USAGE_CACHE] = json.dumps(
        {"balance": 7.0, "rate": 0.7, "assignments": 2}
    )
    storage.data[constants.STORAGE_USAGE_UPDATED_AT] = str(time.time())
    services = NS(storage=storage, colab=NS())
    st = _state_with(_info(balance=99.0))
    with (
        _authed(True, True),
        patch("colab_cli.common.State", side_effect=lambda: st),
    ):
        result = _run(usage_cache.get_usage_cached(services, "oauth2"))
    assert result["cached"] is True and result["balance"] == 7.0
    st.client.get_consumption_user_info.assert_not_called()


def test_read_through_fetches_and_writes_back_on_miss():
    storage = FakeStorage()
    services = NS(storage=storage, colab=NS())
    with _authed(True, True):
        import services.colab as colab_pkg

        async def _fake_impl(service, auth_method="oauth2", cached_fallback=None):
            return {
                "balance": 9.0,
                "rate": 0.9,
                "assignments": 3,
                "cached": False,
                "reason": "ok",
                "fetched_at": time.time(),
            }

        with patch.object(colab_pkg.usage_ops, "get_usage_impl", _fake_impl):
            result = _run(usage_cache.get_usage_cached(services, "oauth2"))
    assert result["balance"] == 9.0 and result["reason"] == "ok"
    from core import constants

    assert constants.STORAGE_USAGE_CACHE in storage.data


def test_usage_card_helpers():
    from screens.settings.account_section import format_usage_values, free_tier_copy

    rows, needs_copy = format_usage_values(
        {"balance": 12.34, "rate": 1.23, "assignments": 2}
    )
    assert rows[0] == ("Compute-unit balance", "12.34 compute units")
    assert rows[1] == ("Usage rate", "1.23/hr")
    assert rows[2] == ("Active assignments", "2")
    assert needs_copy is False
    _, needs_copy = format_usage_values({"balance": 0.0, "rate": 0.0, "assignments": 0})
    assert needs_copy is True
    assert "free-tier" in free_tier_copy()

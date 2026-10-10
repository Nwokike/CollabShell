"""Premium service tests: the checkout watcher, reconcile cadence, channel.

Ports ktv-player/tests/test_checkout_watcher.py. Uses a scripted license
transport so no Worker is contacted.

There is no pytest-asyncio in this project, so the ``env`` fixture owns one
event loop for the whole test: page.run_task needs a running loop, and the
fixture drains and closes it on teardown so a leaked task cannot hang the
suite. Tests read only the members they need off ``env``, which keeps the
unused-variable linter quiet without noisy underscore prefixes.
"""

import asyncio
import importlib.util
import sys
import time
from pathlib import Path
from typing import NamedTuple

import pytest

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
from services import premium_service as ps
from services.license_service import (
    KiriLicenseService,
    LicenseUnavailable,
)
from services.premium_service import PremiumService

RECOVERY = "KIRI-M-FIXTURE0000000000000000"


class _TaskPage:
    """A page whose run_task really creates a task (so cancel is testable)."""

    def __init__(self, loop):
        self.loop = loop
        self.tasks = []
        self.platform = type("P", (), {"is_mobile": staticmethod(lambda: False)})()

    def run_task(self, fn, *args):
        task = self.loop.create_task(fn(*args))
        self.tasks.append(task)
        return task

    def show_snack(self, message):
        self.last_snack = message


class _State:
    def __init__(self):
        self.is_premium = False


class _Storage:
    def __init__(self, data=None):
        self.data = dict(data or {})

    async def get(self, key, default=None):
        return self.data.get(key, default)

    async def set(self, key, value):
        self.data[key] = str(value)


class _Env(NamedTuple):
    """A fully wired service plus its collaborators, for one test."""

    premium: PremiumService
    state: _State
    page: _TaskPage
    storage: _Storage
    loop: asyncio.AbstractEventLoop


@pytest.fixture(autouse=True)
def _fast_watcher(monkeypatch):
    """Real monotonic clock, but seconds-scale intervals."""
    monkeypatch.setattr(ps, "CHECKOUT_WATCH_INTERVAL", 0.005)
    monkeypatch.setattr(ps, "CHECKOUT_WATCH_TIMEOUT", 0.5)


@pytest.fixture(autouse=True)
def _direct_channel(monkeypatch):
    monkeypatch.setattr(ps, "CHANNEL", "direct")


def _make_premium(loop) -> PremiumService:
    """Build a service against the shared loop (channel already patched)."""
    premium = PremiumService(_TaskPage(loop), _State(), _Storage())
    premium.license = KiriLicenseService(
        premium.storage, on_change=premium._recompute_premium
    )
    premium.license.public_key = PUBLIC_KEY
    return premium


@pytest.fixture
def env():
    """One loop plus a fully wired service, for the whole test."""
    loop = asyncio.new_event_loop()
    premium = _make_premium(loop)
    try:
        yield _Env(premium, premium.state, premium.page, premium.storage, loop)
    finally:
        tasks = list(asyncio.all_tasks(loop))
        if tasks:
            loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
        loop.close()


def _settle(loop):
    tasks = [t for t in asyncio.all_tasks(loop) if not t.done()]
    if tasks:
        loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))


def _seed(premium, data):
    premium.storage.data.update(data)


def _patch_http(monkeypatch, script):
    """Serve a scripted sequence of license responses.

    An overrun raises AssertionError, so a loop that polls more than intended
    is caught rather than silently passing.
    """
    remaining = list(script)
    urls = []

    def handler(request):
        urls.append(str(request.url))
        if not remaining:
            raise AssertionError("unexpected extra license request")
        item = remaining.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def factory(timeout=None):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(ls, "_http_client", factory)
    return urls


def _active():
    return httpx.Response(
        status_code=200,
        json={"status": "active", "product": "lifetime", "token": TOKENS["LIFETIME"]},
    )


def _not_found():
    return httpx.Response(status_code=404, json={"message": "license_not_found"})


def _refused():
    return httpx.Response(status_code=403, json={"message": "app not entitled"})


# ── the checkout watcher ──────────────────────────────────────────────────


def test_watcher_polls_pending_then_unlocks(env, monkeypatch):
    _seed(env.premium, {"kiri_recovery_id": RECOVERY})
    _patch_http(monkeypatch, [_not_found(), _not_found(), _active()])

    env.premium.start_checkout_watch(RECOVERY)
    _settle(env.loop)

    assert env.state.is_premium is True
    assert env.storage.data.get("kiri_token") == TOKENS["LIFETIME"]


def test_watcher_gives_up_after_the_window(env, monkeypatch):
    _seed(env.premium, {"kiri_recovery_id": RECOVERY})
    # Always pending: the watcher must time out and leave premium off.
    _patch_http(monkeypatch, [_not_found() for _ in range(500)])

    env.premium.start_checkout_watch(RECOVERY)
    _settle(env.loop)

    assert env.state.is_premium is False


def test_double_start_is_safe(env, monkeypatch):
    _patch_http(monkeypatch, [_not_found() for _ in range(500)])
    premium = env.premium

    premium.start_checkout_watch(RECOVERY)
    first = premium._checkout_watch_task
    premium.start_checkout_watch(RECOVERY)
    second = premium._checkout_watch_task
    assert first is not second
    premium.shutdown()
    _settle(env.loop)
    assert second.cancelled() or second.done()


def test_hard_refusal_aborts_fast(env, monkeypatch):
    _seed(env.premium, {"kiri_recovery_id": RECOVERY})
    urls = _patch_http(monkeypatch, [_refused()])

    env.premium.start_checkout_watch(RECOVERY)
    _settle(env.loop)

    assert len(urls) == 1, "a 403 must stop the watcher immediately"
    assert env.state.is_premium is False


def test_404_keeps_polling(env, monkeypatch):
    """A webhook lag looks like a 404; the payment is usually real, so keep
    polling rather than treating it as a refusal."""
    _seed(env.premium, {"kiri_recovery_id": RECOVERY})
    urls = _patch_http(monkeypatch, [_not_found(), _not_found(), _active()])

    env.premium.start_checkout_watch(RECOVERY)
    _settle(env.loop)

    assert len(urls) == 3
    assert env.state.is_premium is True


def test_generic_exception_continues(env, monkeypatch):
    _seed(env.premium, {"kiri_recovery_id": RECOVERY})
    _patch_http(monkeypatch, [httpx.TimeoutException("db hiccup"), _active()])

    env.premium.start_checkout_watch(RECOVERY)
    _settle(env.loop)
    assert env.state.is_premium is True


def test_manual_restore_stops_the_watcher(env, monkeypatch):
    _seed(env.premium, {"kiri_recovery_id": RECOVERY, "kiri_token": TOKENS["LIFETIME"]})
    urls = _patch_http(monkeypatch, [_active()])

    # Already premium from the cache.
    env.loop.run_until_complete(env.premium.license.apply_cached_token())
    assert env.state.is_premium is True

    env.premium.start_checkout_watch(RECOVERY)
    _settle(env.loop)
    assert urls == [], "an already-premium watcher makes no request"


# ── reconcile ──────────────────────────────────────────────────────────────


def test_reconcile_uses_the_token_issuing_path(env, monkeypatch):
    _seed(env.premium, {"kiri_recovery_id": RECOVERY})
    urls = _patch_http(monkeypatch, [_active()])

    env.loop.run_until_complete(env.premium.reconcile())
    assert urls[0].endswith("/restore"), urls
    assert env.state.is_premium is True


def test_reconcile_without_a_recovery_id_makes_no_request(env, monkeypatch):
    _patch_http(monkeypatch, [_active()])

    env.loop.run_until_complete(env.premium.reconcile())
    assert env.state.is_premium is False


def test_resume_debounces_bursts(env, monkeypatch):
    _seed(env.premium, {"kiri_recovery_id": RECOVERY})
    urls = _patch_http(monkeypatch, [_active()])

    # Simulate "just reconciled" — the constructor seeds the clock negative so
    # the FIRST resume is never debounced (that is the point of the sentinel).
    env.premium._last_reconcile_at = time.monotonic()
    env.loop.run_until_complete(env.premium.reconcile_if_due())
    assert urls == [], "a burst of resumes must collapse to one call"

    env.premium._last_reconcile_at = time.monotonic() - ps.RESUME_DEBOUNCE - 1
    env.loop.run_until_complete(env.premium.reconcile_if_due())
    assert len(urls) == 1


def test_hourly_loop_runs_until_shutdown(env, monkeypatch):
    monkeypatch.setattr(ps, "RECONCILE_INTERVAL", 0.01)
    _seed(env.premium, {"kiri_recovery_id": RECOVERY})
    premium = env.premium

    calls = []
    original = premium.reconcile

    async def _counting():
        calls.append(1)
        await original()

    monkeypatch.setattr(premium, "reconcile", _counting)
    premium.start_reconcile_loop()
    env.loop.run_until_complete(asyncio.sleep(0.08))
    premium.shutdown()
    _settle(env.loop)
    assert len(calls) >= 1


def test_reconcile_loop_survives_failure(env, monkeypatch):
    monkeypatch.setattr(ps, "RECONCILE_INTERVAL", 0.01)
    premium = env.premium

    calls = []

    async def _boom_once():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("db blew up")

    monkeypatch.setattr(premium, "reconcile", _boom_once)
    premium.start_reconcile_loop()
    env.loop.run_until_complete(asyncio.sleep(0.08))
    premium.shutdown()
    _settle(env.loop)
    assert len(calls) >= 2, "the loop must survive a failing tick"


def test_reconcile_stamps_after_work(env, monkeypatch):
    """An unreadable recovery ID must not raise, and must stamp the clock."""
    async def _bad_get(*_a, **_k):
        raise OSError("unreadable")

    monkeypatch.setattr(env.premium.license, "recovery_id", _bad_get)
    before = env.premium._last_reconcile_at
    env.loop.run_until_complete(env.premium.reconcile())
    assert env.premium._last_reconcile_at > before


# ── listeners and notifications ───────────────────────────────────────────


def test_recompute_notifies_only_on_flip(env):
    premium, state = env.premium, env.state
    seen = []
    premium.add_listener(lambda: seen.append(1))

    premium.license._unlocked = True
    premium._recompute_premium()
    assert seen == [1] and state.is_premium is True

    premium.license._unlocked = True  # no change
    premium._recompute_premium()
    assert seen == [1], "notifying on a non-flip is noise"

    premium.license._unlocked = False
    premium._recompute_premium()
    assert seen == [1, 1]


def test_listener_failure_is_swallowed(env):
    premium = env.premium

    def _boom():
        raise RuntimeError("listener blew up")

    premium.add_listener(_boom)
    premium.license._unlocked = True
    premium._recompute_premium()  # must not raise


def test_unlock_notice_is_mobile_aware(env):
    premium = env.premium
    premium.page.platform.is_mobile = staticmethod(lambda: True)
    premium._notify_premium_unlocked()
    assert premium.page.last_snack == "Premium unlocked. Ads removed."


def test_unlock_notice_on_desktop(env):
    premium = env.premium
    premium._notify_premium_unlocked()
    assert premium.page.last_snack == "Premium unlocked."


# ── channel gating ─────────────────────────────────────────────────────────


def test_play_build_starts_no_watcher(env, monkeypatch):
    monkeypatch.setattr(ps, "CHANNEL", "play")
    # Built AFTER the patch: backend is decided in __init__.
    premium = _make_premium(env.loop)
    premium.storage.data["kiri_recovery_id"] = RECOVERY
    _patch_http(monkeypatch, [_active()])

    assert premium.available is False
    premium.start_checkout_watch(RECOVERY)
    premium.start_reconcile_loop()
    _settle(env.loop)
    assert premium.page.tasks == [], "a Play build must schedule nothing"


def test_play_build_reconcile_is_a_noop(env, monkeypatch):
    monkeypatch.setattr(ps, "CHANNEL", "play")
    premium = _make_premium(env.loop)
    premium.storage.data["kiri_recovery_id"] = RECOVERY
    _patch_http(monkeypatch, [_active()])

    env.loop.run_until_complete(premium.reconcile())
    env.loop.run_until_complete(premium.reconcile_if_due())
    assert premium.state.is_premium is False


def test_play_build_load_local_forces_free(env, monkeypatch):
    monkeypatch.setattr(ps, "CHANNEL", "play")
    premium = _make_premium(env.loop)
    premium.storage.data["kiri_token"] = TOKENS["LIFETIME"]
    premium.state.is_premium = True

    env.loop.run_until_complete(premium.load_local())
    assert premium.state.is_premium is False


def test_play_build_checkout_is_refused(env, monkeypatch):
    monkeypatch.setattr(ps, "CHANNEL", "play")
    premium = _make_premium(env.loop)
    try:
        env.loop.run_until_complete(premium.kiri_checkout("monthly", "a@b.com"))
        raise AssertionError("should have raised")
    except LicenseUnavailable as ex:
        assert "not available" in str(ex)


def test_play_build_catalog_is_empty(env, monkeypatch):
    monkeypatch.setattr(ps, "CHANNEL", "play")
    premium = _make_premium(env.loop)
    assert env.loop.run_until_complete(premium.kiri_catalog()) == []

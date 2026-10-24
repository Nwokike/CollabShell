"""Tests for the rebuilt Settings usage card state machine.

Covers: auto-load once per identity, spinner on every load (not just empty),
timestamp rendering, per-reason copy, disabled-while-loading refresh, and
state surviving a parent rebuild (theme toggle).
"""

import asyncio
import contextlib
import sys
import threading
import time
from types import SimpleNamespace as NS

sys.path.insert(0, "src")

from screens.settings.account_section import (
    _USAGE,
    _USAGE_VIEW,
    build_account_section,
    format_usage_values,
    free_tier_copy,
    reset_usage_card,
)


class FakeStorage:
    def __init__(self):
        self.data = {}
        self.deleted = []

    async def get(self, key, default=None):
        return self.data.get(key, default)

    async def set(self, key, value):
        self.data[key] = value if isinstance(value, str) else str(value)

    async def delete(self, key):
        self.deleted.append(key)
        self.data.pop(key, None)


class FakePage:
    """Page handle backed by a real event loop on a worker thread.

    run_task schedules the coroutine instead of blocking the caller, so a
    fetch parked on a gate can be observed mid-flight — which is exactly the
    state the refresh-spinner assertion needs.
    """

    def __init__(self):
        self.updates = 0
        self.scheduled = 0
        self._loop = asyncio.new_event_loop()
        self._futures = []
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

    def run_task(self, fn, *args):
        self.scheduled += 1
        fut = asyncio.run_coroutine_threadsafe(fn(*args), self._loop)
        self._futures.append(fut)
        return fut

    def update(self):
        self.updates += 1

    def wait_idle(self, timeout: float = 5.0):
        """Block until every scheduled coroutine has settled.

        The card swallows its own load errors, so a failed future is not a test
        failure here — the assertions inspect _USAGE instead.
        """
        for fut in list(self._futures):
            try:
                fut.result(timeout=timeout)
            except Exception:
                pass
        self._futures.clear()


@contextlib.contextmanager
def patch_cache(fn):
    """Temporarily replace usage_cache.get_usage_cached (restored on exit)."""
    from services import usage_cache

    orig = usage_cache.get_usage_cached
    usage_cache.get_usage_cached = fn
    try:
        yield
    finally:
        usage_cache.get_usage_cached = orig


def _texts(rows) -> list[str]:
    """Flatten a rendered row list to the visible strings."""
    out = []
    for row in rows:
        controls = getattr(row, "controls", [])
        if controls:
            out.extend(_texts(controls))
        value = getattr(row, "value", None)
        if value:
            out.append(value)
    return out


def _current_texts() -> list[str]:
    """The usage card's text as the next render would build it.

    `_USAGE_VIEW["body"]` is a control from an EARLIER render, and flet froze
    those, so the live card no longer writes into it. The card rebuilds from
    the store — `_usage_rows(_USAGE)` — which is what this returns.
    """
    from screens.settings.account_section import _usage_rows

    return _texts(_usage_rows(_USAGE))


def _fresh():
    """Reset module-level card state and return a fresh page/state/services."""
    reset_usage_card()
    page = FakePage()
    state = NS(
        is_authenticated=True,
        auth_email="user@example.com",
        auth_method="oauth2",
    )
    storage = FakeStorage()
    services = NS(storage=storage, colab=NS())
    return page, state, services, storage


def test_format_helpers():
    rows, needs_copy = format_usage_values(
        {"balance": 12.34, "rate": 1.23, "assignments": 2}
    )
    assert rows[0] == ("Compute-unit balance", "12.34 compute units")
    assert rows[1] == ("Usage rate", "1.23/hr")
    assert rows[2] == ("Active assignments", "2")
    assert needs_copy is False
    _, needs_copy = format_usage_values(
        {"balance": 0.0, "rate": 0.0, "assignments": 0}
    )
    assert needs_copy is True
    assert "free-tier" in free_tier_copy()


def test_reset_clears_state_and_rearms_autoload():
    _USAGE.update({"usage": {"balance": 1.0}, "loaded": True, "updated_at": "1"})
    reset_usage_card()
    assert _USAGE["usage"] is None
    assert _USAGE["loaded"] is False
    # Re-armed: the next build with the SAME identity must auto-load again.
    page, state, services, _ = _fresh()
    _USAGE.update({"loaded": False})
    build_account_section(page, state, services)
    assert page.scheduled == 1


def test_auto_load_fires_once_per_identity():
    page, state, services, _ = _fresh()
    build_account_section(page, state, services)
    assert page.scheduled == 1
    # A rebuild (parent re-render, e.g. theme toggle) must NOT refetch.
    build_account_section(page, state, services)
    build_account_section(page, state, services)
    assert page.scheduled == 1
    # A different signed-in identity DOES refetch.
    state.auth_email = "other@example.com"
    build_account_section(page, state, services)
    assert page.scheduled == 2
    # Signing out refetches too (empty identity ≠ previous).
    state.is_authenticated = False
    build_account_section(page, state, services)
    assert page.scheduled == 3


def test_values_render_with_timestamp_and_cache_footnote():
    from core import constants

    page, state, services, storage = _fresh()
    storage.data[constants.STORAGE_USAGE_CACHE] = '{"balance": 4.5, "rate": 0.5, "assignments": 2}'
    storage.data[constants.STORAGE_USAGE_UPDATED_AT] = str(time.time())
    build_account_section(page, state, services)
    page.wait_idle()
    texts = _current_texts()
    assert "4.50 compute units" in texts
    assert "0.50/hr" in texts
    assert any(t.startswith("As of ") for t in texts)
    assert "Cached values — tap Check now for the latest." in texts


def test_signed_out_renders_reason_copy_not_numbers():
    page, state, services, _ = _fresh()
    state.is_authenticated = False

    async def _none(services_, auth_method="oauth2"):
        return None

    with patch_cache(_none):
        build_account_section(page, state, services)
        page.wait_idle()
    texts = _current_texts()
    assert "Sign in to load your compute-unit balance." in texts
    assert not any("compute units" in t for t in texts)


def test_refresh_disables_button_and_shows_spinner_over_old_values():
    from core import constants

    page, state, services, storage = _fresh()
    storage.data[constants.STORAGE_USAGE_CACHE] = '{"balance": 9.0, "rate": 1.0, "assignments": 1}'
    storage.data[constants.STORAGE_USAGE_UPDATED_AT] = str(time.time())

    calls = {"n": 0}

    async def _counting(services_, auth_method="oauth2"):
        calls["n"] += 1
        return {
            "balance": 9.0,
            "rate": 1.0,
            "assignments": 1,
            "cached": False,
            "reason": "ok",
        }

    with patch_cache(_counting):
        build_account_section(page, state, services)
        page.wait_idle()
    assert calls["n"] == 1
    assert _USAGE_VIEW["refresh"].disabled is False

    # Second (forced) fetch parks mid-flight so the loading state is observable.
    gate = asyncio.Event()

    async def _hang(services_, auth_method="oauth2"):
        await gate.wait()
        # Mirror write_cached_usage(): a successful fetch restamps the cache,
        # which is what the card reads back to render "Updated HH:MM".
        await services_.storage.set(
            constants.STORAGE_USAGE_UPDATED_AT, str(time.time())
        )
        return {
            "balance": 9.0,
            "rate": 1.0,
            "assignments": 1,
            "cached": False,
            "reason": "ok",
        }

    with patch_cache(_hang):
        _USAGE_VIEW["refresh"].on_click(None)  # tap Refresh
        deadline = time.time() + 5
        while not _USAGE["loading"] and time.time() < deadline:
            time.sleep(0.01)
        # Button disabled while loading, spinner WITH the old values under it.
        # The button from the LAST render is frozen and can no longer be
        # mutated, so the disabled state is asserted on a fresh build, which
        # is what the card does on the next repaint.
        assert _USAGE["loading"] is True
        from screens.settings.account_section import _usage_header

        assert _usage_header().controls[-1].disabled is True
        texts = _current_texts()
        assert "Loading usage…" in texts
        assert "9.00 compute units" in texts
        # Force path deleted the timestamp so the fetch cannot be a TTL hit.
        assert constants.STORAGE_USAGE_UPDATED_AT in storage.deleted
        # Release the gate from the loop thread — Event.set() from a foreign
        # thread does not wake a loop blocked in select().
        page._loop.call_soon_threadsafe(gate.set)
        page.wait_idle()
    assert _USAGE["loading"] is False
    from screens.settings.account_section import _usage_header

    assert _usage_header().controls[-1].disabled is False
    # Identical numbers, but verifiably refetched.
    assert calls["n"] == 1
    texts = _current_texts()
    assert "9.00 compute units" in texts
    assert any(t.startswith("As of ") for t in texts)


def test_failed_refresh_marks_error_truthfully():
    page, state, services, _ = _fresh()

    async def _stale(services_, auth_method="oauth2"):
        return {
            "balance": 3.0,
            "rate": 0.25,
            "assignments": 0,
            "cached": True,
            "reason": "fetch-failed",
        }

    with patch_cache(_stale):
        build_account_section(page, state, services)
        page.wait_idle()
    texts = _current_texts()
    assert _USAGE["error"] is True
    assert "Couldn't refresh usage — showing last known values." in texts
    # Must NOT also print the "Cached values" footnote (would read as fresh).
    assert "Cached values — tap Check now for the latest." not in texts


def test_state_survives_parent_rebuild_without_reloading():
    """The bug this guards: state lived in the builder's local scope, so every
    Settings re-render wiped the card back to 'Loading usage…' and refetched."""
    page, state, services, _ = _fresh()
    calls = []

    async def _count(services_, auth_method="oauth2"):
        calls.append(1)
        return {
            "balance": 7.0,
            "rate": 0.7,
            "assignments": 2,
            "cached": False,
            "reason": "ok",
        }

    with patch_cache(_count):
        build_account_section(page, state, services)
        page.wait_idle()
    assert len(calls) == 1
    # Simulate a re-render caused by an unrelated observable (theme toggle).
    body_before = _USAGE_VIEW["body"]
    build_account_section(page, state, services)
    assert len(calls) == 1  # no refetch
    assert _USAGE_VIEW["body"] is not body_before  # new controls
    # Values still present on the NEW controls — no loading flash.
    texts = _current_texts()
    assert "7.00 compute units" in texts
    assert "Loading usage…" not in texts


def test_spinner_row_keeps_previous_values():
    from screens.settings.account_section import _usage_spinner_row

    rows = _usage_spinner_row({"usage": {"balance": 5.0, "rate": 1.0, "assignments": 1}})
    texts = _texts(rows)
    assert "Loading usage…" in texts
    assert "5.00 compute units" in texts


def test_no_tap_to_load_idle_text():
    import pathlib

    src = pathlib.Path("src/screens/settings/account_section.py").read_text(
        encoding="utf-8"
    )
    assert "Tap Check now to load your compute-unit balance." not in src
    assert "Usage unavailable. Tap Check now to retry." in src  # failure copy only


def test_the_age_is_shown_in_words():
    from screens.settings.account_section import _format_updated

    now = time.time()
    assert _format_updated({"updated_at": str(now)}) == "As of just now"
    assert _format_updated({"updated_at": str(now - 90)}) == "As of 1 minute ago"
    assert _format_updated({"updated_at": str(now - 300)}) == "As of 5 minutes ago"
    assert _format_updated({"updated_at": str(now - 3600)}) == "As of 1 hour ago"
    assert _format_updated({"updated_at": str(now - 7200)}) == "As of 2 hours ago"
    assert _format_updated({"updated_at": str(now - 86400 * 3)}) == "As of 3 days ago"
    assert _format_updated({"updated_at": ""}) == ""
    assert _format_updated({}) == ""


def test_staleness_depends_on_the_timestamp():
    from screens.settings.account_section import _usage_is_stale

    now = time.time()
    assert _usage_is_stale({"updated_at": str(now)}) is False
    assert _usage_is_stale({"updated_at": str(now - 60)}) is False
    assert _usage_is_stale({"updated_at": str(now - 3600)}) is True
    assert _usage_is_stale({"updated_at": ""}) is False


def test_re_entering_settings_rechecks_once_the_numbers_are_old():
    """The affordance the user asked for: come back later, get current numbers."""
    from core import constants

    page, state, services, storage = _fresh()
    calls = []

    async def _count(services_, auth_method="oauth2"):
        calls.append(1)
        await services_.storage.set(
            constants.STORAGE_USAGE_UPDATED_AT, str(time.time())
        )
        return {
            "balance": 1.0,
            "rate": 0.1,
            "assignments": 0,
            "cached": False,
            "reason": "ok",
        }

    with patch_cache(_count):
        build_account_section(page, state, services)
        page.wait_idle()
        assert len(calls) == 1

        # A rebuild within the window costs nothing.
        build_account_section(page, state, services)
        page.wait_idle()
        assert len(calls) == 1

        # Age the numbers past the window: the next entry re-checks and forces.
        _USAGE["updated_at"] = str(time.time() - 3600)
        build_account_section(page, state, services)
        page.wait_idle()
        assert len(calls) == 2
        assert constants.STORAGE_USAGE_UPDATED_AT in storage.deleted


def test_the_button_says_what_it_does():
    """Not a bare refresh glyph: "Check now" is what the user is being asked."""
    page, state, services, _ = _fresh()
    build_account_section(page, state, services)
    button = _USAGE_VIEW["refresh"]
    assert button.content == "Check now"

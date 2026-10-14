"""The router status loop — the bridge from the router to the screens.

What matters is that the loop never invents state, never stops the app, and
repaints only when something actually moved. The loop is driven for real here
(its own coroutine, with the interval patched to zero) rather than reimplemented,
so a change to the liveness rules fails these tests instead of passing them.
"""

import asyncio
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from services import router_watchdog as wd


class _FakeSession:
    def __init__(self):
        self.nudges = 0

    def refresh_model_chip(self):
        self.nudges += 1


class _BoomSession:
    """A session whose widget was released — the loop must survive it."""

    nudge_error = RuntimeError("widget released")

    def refresh_model_chip(self):
        raise self.nudge_error


class _FakePage:
    def __init__(self, session=None):
        self._assistant_session = session


class _InstantEvent(asyncio.Event):
    """An event whose wait returns immediately, so a tick costs no wall-clock.

    It yields once before returning: without that suspension the loop's body
    never hands control back, and the coroutine counting probes would starve
    instead of the test finishing.
    """

    async def wait(self, timeout=None):
        await asyncio.sleep(0)
        return True


@pytest.fixture
def instant_event(monkeypatch):
    monkeypatch.setattr(asyncio, "Event", _InstantEvent)


@pytest.fixture
def probe(monkeypatch):
    """Patch `router.probe_router`; returns a list of the requests it took."""
    from services import router

    answers: list[tuple[str, int | None]] = []
    calls: list[bool] = []

    async def fake_probe():
        calls.append(True)
        index = len(calls) - 1
        if index < len(answers):
            return answers[index]
        return answers[-1] if answers else ("unavailable", None)

    monkeypatch.setattr(router, "probe_router", fake_probe)

    def set(*pairs):
        answers[:] = list(pairs)
        calls.clear()

    set.answers = answers
    set.calls = calls
    return set


def _run_ticks(
    watchdog: wd.RouterStatusWatchdog, probe, count: int
) -> wd.RouterStatusWatchdog:
    """Run the given watchdog's real loop until it has taken `count` probes.

    The interval is patched to zero by the `instant_event` fixture, so this
    completes in milliseconds while still exercising `RouterStatusWatchdog`'s
    own coroutine — not a copy of it.
    """

    async def go():
        task = asyncio.ensure_future(watchdog._loop())
        while len(probe.calls) < count:
            await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(go())
    return watchdog


# ── the loop's own rules ────────────────────────────────────────────────────


def test_a_transition_notifies_open_session(monkeypatch, probe, instant_event):
    probe(("starting", None), ("ready", 8083))
    session = _FakeSession()
    watchdog = wd.RouterStatusWatchdog(_FakePage(session))
    _run_ticks(watchdog, probe, 2)
    assert session.nudges == 1, session.nudges
    assert watchdog._last == ("ready", 8083), watchdog._last


def test_the_first_tick_only_seeds_the_baseline(monkeypatch, probe, instant_event):
    """Publishing on the first tick would paint a state nobody watched change."""
    probe(("unavailable", None))
    session = _FakeSession()
    watchdog = wd.RouterStatusWatchdog(_FakePage(session))
    _run_ticks(watchdog, probe, 1)
    assert session.nudges == 0, session.nudges


def test_a_repeated_status_is_not_a_transition(monkeypatch, probe, instant_event):
    probe(("starting", None), ("ready", 8083), ("ready", 8083))
    session = _FakeSession()
    watchdog = wd.RouterStatusWatchdog(_FakePage(session))
    _run_ticks(watchdog, probe, 3)
    assert session.nudges == 1, session.nudges


def test_a_router_coming_back_is_a_transition(monkeypatch, probe, instant_event):
    probe(("unavailable", None), ("ready", 8083), ("stopped", None), ("ready", 8084))
    session = _FakeSession()
    watchdog = wd.RouterStatusWatchdog(_FakePage(session))
    _run_ticks(watchdog, probe, 4)
    assert session.nudges == 3, session.nudges


def test_no_page_is_not_an_error(monkeypatch, probe, instant_event):
    probe(("starting", None), ("ready", 8083))
    watchdog = wd.RouterStatusWatchdog()
    _run_ticks(watchdog, probe, 2)
    assert watchdog._last == ("ready", 8083), watchdog._last


def test_a_failing_nudge_does_not_kill_the_loop(monkeypatch, probe, instant_event):
    probe(("starting", None), ("ready", 8083))
    session = _BoomSession()
    watchdog = wd.RouterStatusWatchdog(_FakePage(session))
    _run_ticks(watchdog, probe, 2)
    # The state still moved, which is the loop's whole job.
    assert watchdog._last == ("ready", 8083), watchdog._last


def test_a_failing_probe_keeps_the_previous_answer(monkeypatch, instant_event):
    from services import router

    answers = [Exception("socket dead")]

    async def fake_probe():
        raise answers[0]

    monkeypatch.setattr(router, "probe_router", fake_probe)
    watchdog = wd.RouterStatusWatchdog()

    async def go():
        task = asyncio.ensure_future(watchdog._loop())
        for _ in range(3):
            await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(go())
    assert watchdog._last is None, "a failed probe must not invent a status"


# ── the registry the router nudges ──────────────────────────────────────────


@pytest.fixture
def clean_router_state():
    """Snapshot and restore the router's observable state.

    Two tests below publish for real, and `state` is a process-wide singleton —
    without this the leaked status would change `pill_state` and the catalog
    behaviour in every test file that runs after.
    """
    from core.state import state

    saved = (state.ai_router_status, state.ai_router_port)
    yield
    state.ai_router_status, state.ai_router_port = saved


def test_a_published_status_wakes_the_watchdog(clean_router_state):
    """A turn that just embedded a router must not wait a full interval."""
    from services import router

    wd._active = None
    try:
        woken = []

        class _Fake:
            def wake(self):
                woken.append(True)

        wd._active = _Fake()
        router._publish_status("ready", 8083)
        assert woken == [True], woken
        # A no-op publish must not wake anything.
        router._publish_status("ready", 8083)
        assert woken == [True], woken
    finally:
        wd._active = None


def test_no_watchdog_is_not_an_error(clean_router_state):
    from core.state import state
    from services import router

    wd._active = None
    try:
        router._publish_status("starting", None)
        assert state.ai_router_status == "starting"
    finally:
        wd._active = None

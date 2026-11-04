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
    """Patch `router.probe_router` AND `ensure_router`; returns the call log.

    `ensure_router` is stubbed too, because the loop now calls it once at boot to
    attach-or-embed (the owner: no manual `start gateway`). Without the stub the
    boot path would hit the real network and make these tests slow and flaky.
    """
    from services import router

    answers: list[tuple[str, int | None]] = []
    calls: list[bool] = []

    async def fake_probe():
        calls.append(True)
        index = len(calls) - 1
        if index < len(answers):
            return answers[index]
        return answers[-1] if answers else ("unavailable", None)

    async def fake_ensure(*_a, **kw):
        # Never touch the network: a real attach-or-embed here would download
        # an engine and make these tests slow and environment-dependent.
        return None

    monkeypatch.setattr(router, "probe_router", fake_probe)
    monkeypatch.setattr(router, "ensure_router", fake_ensure)

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


# ── starting the router at boot ─────────────────────────────────────────────


def test_the_first_tick_starts_the_router(monkeypatch, instant_event):
    """Attach-or-embed at boot, so nobody has to tap "Start gateway".

    Both references do this (DDGS `app_controller.py:160`, lm-router
    `main.py:296-297`) and the owner asked for it directly. Stubbed here so the
    test proves the CALL happens, without the network.
    """
    from services import router

    asked = []

    async def fake_ensure(*_a, **kw):
        asked.append(kw)
        return 8083

    monkeypatch.setattr(router, "ensure_router", fake_ensure)
    monkeypatch.setattr(router, "probe_router", _probe_never)
    watchdog = wd.RouterStatusWatchdog()

    async def go():
        task = asyncio.ensure_future(watchdog._loop())
        for _ in range(6):
            await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(go())
    assert asked, "the router was never started at boot"


def test_a_failure_to_start_is_not_fatal(monkeypatch, instant_event):
    """No engine cached, no network: the loop keeps observing anyway.

    The pill stays honest and the Settings "Start router" action still works —
    an automatic path must not remove the manual one.
    """
    from services import router

    async def boom(*_a, **kw):
        raise RuntimeError("offline")

    monkeypatch.setattr(router, "ensure_router", boom)
    watchdog = wd.RouterStatusWatchdog()

    async def go():
        task = asyncio.ensure_future(watchdog._loop())
        for _ in range(6):
            await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(go())  # must not raise


def _probe_never():
    return _never_answered()


async def _never_answered():
    return ("unavailable", None)


# ── the loop's own rules ────────────────────────────────────────────────────


def _seed_state(status="starting", port=None):
    """Put the app's belief where each test expects it.

    The loop compares its first probe against what the app currently believes,
    so the belief is part of the test's setup — not something a previous test
    should be allowed to decide.
    """
    from core.state import state

    state.ai_router_status = status
    state.ai_router_port = port


def test_a_transition_notifies_open_session(
    monkeypatch, probe, instant_event, clean_router_state
):
    _seed_state()
    probe(("starting", None), ("ready", 8083))
    session = _FakeSession()
    watchdog = wd.RouterStatusWatchdog(_FakePage(session))
    _run_ticks(watchdog, probe, 2)
    assert session.nudges == 1, session.nudges
    assert watchdog._last == ("ready", 8083), watchdog._last


def test_the_first_probe_corrects_the_boot_guess(
    monkeypatch, probe, instant_event, clean_router_state
):
    """The app boots guessing "starting"; the first probe replaces the guess.

    Seeding a private baseline instead would leave a router that was already up
    showing "Starting router…" until the app itself did something.
    """
    _seed_state()
    probe(("unavailable", None))
    session = _FakeSession()
    watchdog = wd.RouterStatusWatchdog(_FakePage(session))
    _run_ticks(watchdog, probe, 1)
    assert session.nudges == 1, session.nudges
    assert watchdog._last == ("unavailable", None), watchdog._last


def test_a_first_probe_matching_the_boot_guess_is_silent(
    monkeypatch, probe, instant_event, clean_router_state
):
    """Nothing changed, so nothing is painted."""
    _seed_state("starting", None)
    probe(("starting", None))
    session = _FakeSession()
    watchdog = wd.RouterStatusWatchdog(_FakePage(session))
    _run_ticks(watchdog, probe, 1)
    assert session.nudges == 0, session.nudges


def test_a_repeated_status_is_not_a_transition(
    monkeypatch, probe, instant_event, clean_router_state
):
    _seed_state()
    probe(("starting", None), ("ready", 8083), ("ready", 8083))
    session = _FakeSession()
    watchdog = wd.RouterStatusWatchdog(_FakePage(session))
    _run_ticks(watchdog, probe, 3)
    assert session.nudges == 1, session.nudges


def test_a_router_coming_back_is_a_transition(
    monkeypatch, probe, instant_event, clean_router_state
):
    # The app already knows there is no router, so every nudge below is a real
    # transition rather than the correction of a boot-time guess.
    _seed_state("unavailable", None)
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
    from core.state import state
    from services import router

    # A different starting value, so the first publish really is a change.
    state.ai_router_status = "starting"
    state.ai_router_port = None
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


def test_the_watchdog_publishes_a_passive_transition(
    monkeypatch, probe, instant_event, clean_router_state
):
    """A router killed by something other than this app must still move the UI.

    The loop owns liveness: if it only compared a private baseline and nudged,
    a status the app did not itself publish would be dropped on the floor and
    every screen would keep showing the state from before the router died.
    """
    from core.state import state

    _seed_state("ready", 8083)
    probe(("ready", 8083), ("unavailable", None), ("unavailable", None))

    watchdog = wd.RouterStatusWatchdog()
    _run_ticks(watchdog, probe, 3)
    # The private baseline moved AND the observable state moved with it.
    assert watchdog._last == ("unavailable", None), watchdog._last
    assert state.ai_router_status == "unavailable", state.ai_router_status


def test_the_first_tick_publishes_the_state_it_reads(
    monkeypatch, probe, instant_event, clean_router_state
):
    """The first observation must reach state, not only a private baseline.

    The app boots guessing "starting" whether or not a router is already up;
    the first probe is what replaces that guess with the truth.
    """
    _seed_state("starting", 8082)
    probe(("unavailable", None))
    watchdog = wd.RouterStatusWatchdog()
    _run_ticks(watchdog, probe, 1)
    from core.state import state

    assert state.ai_router_status == "unavailable", state.ai_router_status
    assert state.ai_router_port is None, state.ai_router_port


def test_stop_releases_the_page():
    """The loop holds the page strongly; a release must drop it.

    Otherwise a closed assistant keeps a whole screen tree alive.
    """
    watchdog = wd.RouterStatusWatchdog(_FakePage())
    assert watchdog._page is not None
    watchdog.stop()
    assert watchdog._page is None, "stop must release the page"


def test_a_second_start_stops_the_orphan():
    """Two watchdogs would both tick, and only one is reachable."""
    wd._active = None
    try:
        asyncio.run(_drive_two_starts())
    finally:
        wd._active = None


async def _drive_two_starts():
    first = wd.RouterStatusWatchdog()
    first.start()
    second = wd.RouterStatusWatchdog()
    second.start()
    try:
        # The first loop is cancelled, not left running unseen.
        assert first is not second
        assert wd.current_watchdog() is second, "the newest start is the active one"
        first.stop()
        assert wd.current_watchdog() is second
        second.stop()
        assert wd.current_watchdog() is None
    finally:
        first.stop()
        second.stop()

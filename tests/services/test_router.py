"""Router lifecycle tests.

Each case is a property DDGS learned in the field, and each has a
corresponding comment in its source:

* **A foreign service on 8082 is never adopted.** Accepting whatever happens to
  be listening would point the assistant at something that is not a router.
* **A stale port is re-checked, not trusted.** Returning a port forever is what
  made DDGS's picker "Start router" look inert, and what double-embedded 8082
  and 8083.
* **Only an embedded router is ever stopped**, never the user's own.
* **A full-scan miss is memoised**, so a 3-second watchdog does not pay a
  serial 11-port scan on every tick.
* **A broken probe is not a miss** — a local fault (DDGS documents an Android
  CA crash escaping here) must not poison the miss-TTL.
* **`_publish_status` writes only on a real change**, or the UI repaints on
  every watchdog tick for nothing.
"""

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from services import router


@pytest.fixture(autouse=True)
def _reset_router():
    """Module state is process-global, so every test starts clean."""
    with router._router_lock:
        router._router_server = None
        router._router_port = None
    router._probe_miss_until = 0.0
    router._router_failed_until = 0.0
    yield
    router.stop_router()
    with router._router_lock:
        router._router_server = None
        router._router_port = None
    router._probe_miss_until = 0.0
    router._router_failed_until = 0.0


def _run(coro):
    import asyncio

    return asyncio.run(coro)


class _FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload or {}


class _FakeClient:
    """Serves /health with whatever the test says, and counts the scans."""

    def __init__(self, ports, **kw):
        self.ports = ports
        self.scans = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **kw):
        self.scans += 1
        port = int(url.rsplit(":", 1)[1].split("/")[0])
        for want, status, payload in self.ports:
            if want == port:
                return _FakeResponse(status, payload)
        raise OSError("refused")


def _patch_probe(monkeypatch, ports):
    made = []

    def factory(**kw):
        client = _FakeClient(ports, **kw)
        made.append(client)
        return client

    monkeypatch.setattr(router.httpx, "AsyncClient", factory)
    return made


# ── the probe ────────────────────────────────────────────────────────────────


def test_a_foreign_service_on_8082_is_not_adopted(monkeypatch):
    """A port is accepted only when /health says `adapter == "kiri-router"`.
    Adopting whatever happens to be listening would point the assistant at
    something that is not a router at all."""
    # A service on 8082 that is NOT a router, and a real one on 8083.
    _patch_probe(
        monkeypatch,
        [
            (8082, 200, {"adapter": "some-other-server"}),
            (8083, 200, {"adapter": "kiri-router"}),
        ],
    )
    found = _run(router._probe_existing_router())
    assert found == 8083, "a foreign service must be skipped"


def test_the_users_own_router_is_found_and_reused(monkeypatch):
    _patch_probe(monkeypatch, [(8085, 200, {"adapter": "kiri-router"})])
    assert _run(router._probe_existing_router()) == 8085


def test_a_full_miss_is_memoised(monkeypatch):
    """A 3-second watchdog paying a serial 11-port scan on every tick is a
    burst of refused sockets for no reason."""
    made = _patch_probe(monkeypatch, [])
    assert _run(router._probe_existing_router()) is None
    first = made[0].scans
    assert first > 1, "a full miss scans the whole span"
    # A second probe immediately after must not construct a client at all.
    assert _run(router._probe_existing_router()) is None
    assert len(made) == 1, "a remembered miss must not rescan"


def test_a_broken_probe_is_not_a_miss(monkeypatch):
    """A local fault (DDGS documents an Android CA crash escaping here) must
    return None WITHOUT poisoning the miss-TTL."""

    def boom(**kw):
        raise RuntimeError("no CA store")

    monkeypatch.setattr(router.httpx, "AsyncClient", boom)
    assert _run(router._probe_existing_router()) is None
    assert router._probe_miss_until == 0.0, "a broken probe must not memoise a miss"


# ── status reporting ─────────────────────────────────────────────────────────


def test_probe_router_reports_without_starting_anything(monkeypatch):
    """A UI question must have no side effect."""
    _patch_probe(monkeypatch, [])
    status, port = _run(router.probe_router())
    assert status == "unavailable"
    assert port is None
    assert router._router_server is None, "probing must never embed"


def test_publish_writes_only_on_a_real_change(monkeypatch):
    """A watchdog assigning unconditionally repaints the whole UI every tick."""
    from core.state import state

    monkeypatch.setattr(state, "ai_router_status", "starting", raising=False)
    monkeypatch.setattr(state, "ai_router_port", None, raising=False)
    writes = []

    class FakeState:
        ai_router_status = "starting"
        ai_router_port = None

        def __setattr__(self, k, v):
            writes.append((k, v))
            object.__setattr__(self, k, v)

    import core.state as cs

    monkeypatch.setattr(cs, "state", FakeState())
    router._publish_status("starting", None)
    assert writes == [], "an identical publish must not write"
    router._publish_status("ready", 8083)
    assert ("ai_router_status", "ready") in writes


# ── attaching vs embedding ───────────────────────────────────────────────────


def test_a_probe_hit_attaches_and_embeds_nothing(monkeypatch):
    """The user's own router must be reused, never shadowed by a second one."""
    _patch_probe(monkeypatch, [(8087, 200, {"adapter": "kiri-router"})])
    port = _run(router.ensure_router())
    assert port == 8087
    assert router._router_server is None, "attaching must not embed"


def test_a_held_port_is_returned_without_a_probe(monkeypatch):
    """The normal turn path must not pay a health check it does not need."""
    with router._router_lock:
        router._router_port = 8089
    made = _patch_probe(monkeypatch, [])
    assert _run(router.ensure_router()) == 8089
    assert made == [], "a held port must be trusted without probing"


def test_verify_forgets_a_dead_port_and_re_attaches(monkeypatch):
    """Returning a stale port forever is what made DDGS's "Start router" look
    inert — and what double-embedded 8082 and 8083."""
    with router._router_lock:
        router._router_port = 8082
    # The first health check is dead; the rescan then finds a live one.
    state = {"dead": True}

    class Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **kw):
            if state["dead"]:
                state["dead"] = False
                raise OSError("gone")
            return _FakeResponse(200, {"adapter": "kiri-router"})

    monkeypatch.setattr(router.httpx, "AsyncClient", Client)
    router._probe_miss_until = 1e18  # a stale miss must be cleared too
    port = _run(router.ensure_router(verify=True))
    assert port is not None, "a dead port must be re-attached, not returned"
    assert router._probe_miss_until == 0.0, "the rescan must be real"


def test_stop_never_kills_a_foreign_instance():
    """The user started it; the app only ever stops what it started."""
    with router._router_lock:
        router._router_port = 8090  # attached, not embedded
    router.stop_router()
    assert router._router_server is None
    # The port is cleared, so the next turn re-attaches rather than assuming.
    assert router._router_port is None


def test_shutdown_is_safe_to_call_twice():
    router.shutdown()
    router.shutdown()


# ── the cool-off ─────────────────────────────────────────────────────────────


def test_a_failure_cools_off_and_recovers_early(monkeypatch):
    """The blackout is for a dead loopback; a router that answers again lifts
    it immediately instead of blocking for the rest of the 60 seconds."""
    from core.state import state

    monkeypatch.setattr(state, "ai_router_url", "", raising=False)
    with router._router_lock:
        router._router_port = 8091
    router._router_failed_until = 1e18  # in the blackout

    _patch_probe(monkeypatch, [(8091, 200, {"adapter": "kiri-router"})])
    url = _run(router.router_base())
    assert url == "http://127.0.0.1:8091/v1", url
    assert router._router_failed_until == 0.0, "a live router must lift the blackout"


def test_the_override_wins_over_probing():
    """Someone pointing the app at a remote router means it.

    The override is read one layer up, in ai_service._ensure_router_for_turn,
    because that is where Settings writes it — router itself only owns the
    probe/embed path.
    """
    from core.state import state
    from services.ai_service import _ensure_router_for_turn

    state.ai_router_url = "http://example.test:9999/v1"
    try:
        assert _run(_ensure_router_for_turn()) == "http://example.test:9999/v1"
    finally:
        state.ai_router_url = ""


# ── the URL helpers ──────────────────────────────────────────────────────────


def test_current_url_is_empty_with_no_router():
    assert router.current_url() == ""


def test_current_url_reflects_the_held_port():
    with router._router_lock:
        router._router_port = 8095
    assert router.current_url() == "http://127.0.0.1:8095/v1"

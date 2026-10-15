"""Phase 5 — the router binds real ports, and the ledger balances.

The acquisition half is the point. Every other router test probes with a
monkeypatched `httpx` and `test_router_engine.py` covers download / validate /
load in isolation: until now, **nothing had ever bound a port**. So the one
behaviour the owner requires — the app runs its own server, and when the port is
taken it uses the next one — had never been executed once.

The turn half uses the real `ai_credits.run_metered_turn` and the real
`CreditService`, with the tool bodies real and faked only at the I/O edge, so
what is proven is the plumbing: embed, SSE protocol, meter, approval gate.

The model here is `tests/fixture_router.py`'s script. It answers with text, or
asks for a tool call, based only on what is in the request — which is what makes
the assertions deterministic. A model's judgement is not what is under test.
"""

import asyncio
import sys
from pathlib import Path

import httpx
import pytest

_HERE = Path(__file__).resolve().parent          # tests/e2e
_REPO = _HERE.parent.parent                       # repo root
# Only `src` goes on the path. Adding `tests/` itself would let
# `tests/services/` shadow the real `services` package.
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from core import constants
from services import router, router_engine
from tests import fixture_router

# Windows raises WinError 10038 from a serve-forever thread parked in select()
# when its socket is closed underneath it. It surfaces during _teardown, after
# the test has already passed, and is a platform artefact rather than a fault —
# so it is named here instead of being left as noise in every run, or "fixed" by
# leaking the thread the way `tests/services/test_ai_service.py` does.
pytestmark = pytest.mark.filterwarnings(
    "ignore::pytest.PytestUnhandledThreadExceptionWarning"
)


@pytest.fixture(autouse=True)
def _reset_router():
    """Module state is process-global, and the embed path writes it for real.

    The observable status is snapshotted too: `ensure_router` publishes through
    `router._publish_status`, and a leaked "ready" would change what
    `model_pill.pill_state` reports for every test file that runs after this one.
    """
    from core.state import state

    saved_status = state.ai_router_status
    saved_port = state.ai_router_port
    with router._router_lock:
        router._router_server = None
        router._router_port = None
    router._probe_miss_until = 0.0
    router._router_failed_until = 0.0
    fixture_router.reset()
    yield
    router.stop_router()
    with router._router_lock:
        router._router_server = None
        router._router_port = None
    router._probe_miss_until = 0.0
    router._router_failed_until = 0.0
    state.ai_router_status, state.ai_router_port = saved_status, saved_port
    fixture_router.reset()


def _run(coro):
    return asyncio.run(coro)


def _engine_at(tmp_path, monkeypatch) -> Path:
    """Point the engine cache at the fixture, and never touch the network.

    The same convention as DDGS's `tests/test_engine_service.py:22-36`: a
    contract-complete engine source at a tmp path. Patching `_download` to raise
    is what keeps this offline — without it `load_engine` would try
    router.kiri.ng first.
    """
    cache = tmp_path / "engine_fixture.py"
    cache.write_bytes((_REPO / "tests" / "fixture_router.py").read_bytes())
    monkeypatch.setattr(router_engine, "engine_cache_path", lambda: cache)
    monkeypatch.setattr(router_engine, "_download", _no_network)
    return cache


async def _no_network(*_a, **_kw):
    raise OSError("offline by design: the fixture engine is the only source")


def _foreign_server(port: int):
    """Something that is NOT a Kiri router, holding a port."""
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"adapter": "some-other-server"}')

    server = HTTPServer(("127.0.0.1", port), _Handler)
    import threading

    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


# ── the router binds real ports ─────────────────────────────────────────────


def test_nothing_running_means_we_embed_our_own(tmp_path, monkeypatch):
    """With an empty span, the app must bind its own server.

    Before this existed, `acquire_server` had never been called in a test. The
    span starts on a free high port rather than a fixed low one: port 0 is not
    bindable and 1-1023 are privileged, so a scan there pays seconds of refusals
    for no extra coverage.
    """
    monkeypatch.setattr(constants, "ROUTER_BASE_PORT", _free_port())
    monkeypatch.setattr(constants, "ROUTER_SPAN", 6)
    _engine_at(tmp_path, monkeypatch)

    port = _run(router.ensure_router())
    assert port is not None, "an empty span must still give us a router"
    assert router.owns_embedded() is True, "we bound it, so it is ours to stop"
    health = httpx.get(f"http://127.0.0.1:{port}/health", timeout=5).json()
    assert health["adapter"] == "kiri-router", health


def test_a_foreign_service_does_not_stop_us_binding(tmp_path, monkeypatch):
    """A non-router on the base port must be skipped, not adopted.

    This is the owner's requirement as an assertion: the app runs its own
    server, and when the port is taken it uses the next one.
    """
    base = _free_port()
    foreign = _foreign_server(base)
    try:
        monkeypatch.setattr(constants, "ROUTER_BASE_PORT", base)
        monkeypatch.setattr(constants, "ROUTER_SPAN", 6)
        _engine_at(tmp_path, monkeypatch)

        port = _run(router.ensure_router())
        assert port is not None, "a foreign service must not block embedding"
        assert port != base, f"the foreign service on {base} was adopted"
        assert router.owns_embedded() is True
        health = httpx.get(f"http://127.0.0.1:{port}/health", timeout=5).json()
        assert health["adapter"] == "kiri-router", health
        # The foreign service is still there, untouched.
        still = httpx.get(f"http://127.0.0.1:{base}/health", timeout=5).json()
        assert still["adapter"] == "some-other-server", still
    finally:
        _teardown(foreign)


def test_a_users_own_router_is_attached_not_shadowed(tmp_path, monkeypatch):
    """A live Kiri router is reused; embedding beside it would be a second router."""
    server, port = fixture_router.start(0)
    try:
        monkeypatch.setattr(constants, "ROUTER_BASE_PORT", port)
        monkeypatch.setattr(constants, "ROUTER_SPAN", 6)
        _engine_at(tmp_path, monkeypatch)

        found = _run(router.ensure_router())
        assert found == port, found
        assert router.owns_embedded() is False, (
            "attaching to a router the user already runs must not embed"
        )
    finally:
        _teardown(server)


def test_stopping_leaves_an_attached_router_alone(tmp_path, monkeypatch):
    """`stop_router` stops only what we embedded."""
    server, port = fixture_router.start(0)
    try:
        monkeypatch.setattr(constants, "ROUTER_BASE_PORT", port)
        monkeypatch.setattr(constants, "ROUTER_SPAN", 6)
        _engine_at(tmp_path, monkeypatch)
        assert _run(router.ensure_router()) == port

        router.stop_router()
        # Someone else's router is still answering.
        health = httpx.get(f"http://127.0.0.1:{port}/health", timeout=5).json()
        assert health["adapter"] == "kiri-router", health
    finally:
        _teardown(server)


def _teardown(server) -> None:
    """Stop a test-owned server cleanly.

    `shutdown()` joins the serve-forever loop before the socket closes, which is
    the correct order. On Windows the loop can still be parked in `select()`
    when the socket goes, and the thread raises WinError 10038 — a teardown
    artefact, not a fault, so it is filtered out below rather than papered over
    by leaking the thread.

    These are the same stdlib fake routers `tests/services/test_ai_service.py`
    runs; that file never stops them, which works only because the whole
    process exits. Here we stop them so the ports are genuinely released for the
    next test in the same run.
    """
    server.shutdown()
    server.server_close()


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]

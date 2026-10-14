"""The model router: probe, embed, and report its state honestly.

Ported from DDGS `src/services/ai_service.py` (the router half) and
`src/services/engine.py`. The app owns its router — it probes for one already
running before embedding its own.

Three properties, each one a bug DDGS hit in the field:

1. **A foreign service on 8082 is never adopted.** A port is accepted only
   when `/health` answers 200 AND says `adapter == "kiri-router"`. Adopting
   whatever happens to be listening would point the assistant at a server that
   is not a model router.
2. **A stale port is re-checked, not trusted.** `ensure_router(verify=True)`
   health-checks a port the app thinks it holds and forgets it if dead, then
   resets the miss-TTL so the rescan is real. Returning a stale port forever is
   what made the picker's "Start router" look like it did nothing, and what
   double-embedded 8082 and 8083.
3. **Only an embedded router is ever stopped.** If the user started their own,
   the app attaches to it and must leave it alone.

`probe_router()` reports without starting anything, so a UI question has no
side effect. That is what lets the header pill and Settings show an honest
state, and why an empty catalog during discovery reads as "still starting"
rather than as a broken app.
"""

from __future__ import annotations

import logging
import threading
import time

import httpx

from core import constants

logger = logging.getLogger("router")

# Module state. `_router_server` is only ever set when WE embedded it — that
# distinction is what makes stop_router safe.
_router_server: object | None = None
_router_port: int | None = None
_router_lock = threading.Lock()

# A full port-scan miss is remembered this long.
_probe_miss_until = 0.0
# Cool-off after a failure, so the UI stops claiming a dead loopback is ready.
_router_failed_until = 0.0


def _publish_status(status: str, port: int | None) -> None:
    """Write router lifecycle to observable state, only on a real change.

    The status watchdog ticks every few seconds; assigning unconditionally
    would repaint the whole UI on every tick for no reason.
    """
    from core.state import state

    if (
        getattr(state, "ai_router_status", None) != status
        or getattr(state, "ai_router_port", None) != port
    ):
        state.ai_router_status = status
        state.ai_router_port = port
        _wake_watchdog()


def _wake_watchdog() -> None:
    """Nudge the status loop so a transition shows up now, not in 3 seconds.

    Imported lazily and guarded: the loop is optional, and the router must never
    depend on the UI being up.
    """
    try:
        from services.router_watchdog import current_watchdog

        watchdog = current_watchdog()
    except Exception:
        return
    if watchdog is not None:
        watchdog.wake()


async def _probe_existing_router() -> int | None:
    """Scan 8082..8092 for a live Kiri router — ours or the user's own.

    Returns `None` on a full miss, and remembers that miss so the status
    watchdog stops paying a serial 11-port scan of refused sockets on every
    tick.

    A *broken probe* is deliberately NOT a miss: if the HTTP client cannot even
    be constructed, that is a local fault, not evidence that nothing is
    listening. DDGS documents an Android CA crash escaping here and killing the
    picker callback — so it returns None without poisoning the miss-TTL, and
    without raising.
    """
    global _probe_miss_until

    if time.monotonic() < _probe_miss_until:
        return None
    try:
        async with httpx.AsyncClient(http2=False) as client:
            for port in range(
                constants.ROUTER_BASE_PORT,
                constants.ROUTER_BASE_PORT + constants.ROUTER_SPAN + 1,
            ):
                try:
                    resp = await client.get(
                        f"http://{constants.ROUTER_HOST}:{port}/health",
                        timeout=constants.ROUTER_PROBE_TIMEOUT,
                    )
                    if (
                        resp.status_code == 200
                        and resp.json().get("adapter") == "kiri-router"
                    ):
                        _probe_miss_until = 0.0
                        return port
                except Exception:
                    pass  # closed port or not a router - keep scanning
    except Exception as exc:
        # A broken probe (client construction) is NOT a miss. Never poison the
        # miss-TTL from one, and never let it reach the caller.
        logger.debug("router scan failed: %r", exc)
        return None
    _probe_miss_until = time.monotonic() + constants.PROBE_MISS_TTL
    return None


async def probe_router() -> tuple[str, int | None]:
    """Report the router's live status without starting anything.

    Returns `(status, port)` where status is one of:
      ready        attached and answering /health
      stopped      a port was known but nothing is answering now
      unavailable  no router, and none is embedded
      starting     our embedded server is coming up but not yet healthy

    Callers turn this into an honest label, so an empty list during discovery
    reads as "still starting" rather than as a broken app.
    """
    with _router_lock:
        port = _router_port
    if port is None:
        # A cheap probe only: never embed a server just to report status.
        found = await _probe_existing_router()
        if found is None:
            return ("unavailable", None)
        return ("ready", found)
    try:
        async with httpx.AsyncClient(http2=False) as client:
            resp = await client.get(
                f"http://{constants.ROUTER_HOST}:{port}/health",
                timeout=constants.ROUTER_HEALTH_TIMEOUT,
            )
        if resp.status_code == 200:
            return ("ready", port)
    except Exception as exc:
        logger.debug("router health probe failed on %s: %r", port, exc)
    return ("stopped", port)


def stop_router() -> None:
    """Stop ONLY an embedded router, never the user's own instance."""
    global _router_server, _router_port
    with _router_lock:
        server, _router_server = _router_server, None
        _router_port = None
    if server is None:
        return
    try:
        server.shutdown()
        server.server_close()
        logger.info("AI router: stopped embedded instance")
    except Exception:
        pass
    _publish_status("stopped", None)


def owns_embedded() -> bool:
    """Whether the router currently running was embedded by this app.

    Only an embedded router may be stopped or restarted by the user; one the
    user started by hand is attached to, and must be left alone.
    """
    with _router_lock:
        return _router_server is not None


def _mark_router_failed() -> None:
    """Cool-off after a failure, so the UI stops claiming a dead loopback is
    ready."""
    global _router_failed_until
    _router_failed_until = time.monotonic() + constants.ROUTER_STICKY_COOLDOWN
    with _router_lock:
        port = _router_port
    _publish_status("starting", port)


async def router_base() -> str | None:
    """The base URL for a model request, or None when there is no router.

    The hot path trusts the remembered port with NO probe: a 3-second watchdog
    owns liveness, and a dead port surfaces as a request failure that
    invalidates it through `_mark_router_failed`. Probing here would stack a
    burst of health checks onto every turn.

    The blackout after a failure exists for a dead loopback, so it lifts early
    if the router answers a health check right now — otherwise a restarted
    router would stay blocked for the rest of the 60 seconds.
    """
    global _router_failed_until

    if time.monotonic() < _router_failed_until:
        with _router_lock:
            port = _router_port
        if port is None:
            return None
        try:
            async with httpx.AsyncClient(http2=False) as client:
                resp = await client.get(
                    f"http://{constants.ROUTER_HOST}:{port}/health", timeout=1.0
                )
            if resp.status_code != 200:
                return None
        except Exception:
            return None
        _router_failed_until = 0.0
        logger.info("AI router recovered; blackout lifted early")
    port = await ensure_router()
    if port is None:
        return None
    return f"http://{constants.ROUTER_HOST}:{port}/v1"


async def ensure_router(*, verify: bool = False) -> int | None:
    """Attach to a running Kiri router, or embed one. Returns its port.

    `verify=True` health-checks the port we already hold before trusting it.
    Without it a stale port is returned forever, which is what made the
    picker's "Start router" look like it did nothing. Callers that are acting
    on a user request pass `verify=True`; the normal turn path does not, because
    paying a 2s probe on every turn is not worth it.
    """
    global _router_server, _router_port, _probe_miss_until

    with _router_lock:
        known = _router_port
    if known is not None:
        if not verify:
            return known
        status, _port = await probe_router()
        if status == "ready":
            return known
        # The port is dead. Forget it so the normal attach path runs again.
        with _router_lock:
            if _router_port == known:
                _router_port = None
        # A just-forgotten port must be rescanned for real: our own server may
        # still be listening, and a stale miss-TTL shortcut returning None is
        # what double-embedded 8082 and 8083.
        _probe_miss_until = 0.0
        logger.info("AI router on %s is gone; re-attaching", known)

    # Publish "starting" before the slow parts so the picker can say so.
    _publish_status("starting", None)

    existing = await _probe_existing_router()
    if existing is None:
        # The full scan found nobody. If we still hold an embedded-server
        # object it is genuinely dead: close it before starting a new one so a
        # re-embed can never leak the previous listener.
        stop_router()
    else:
        with _router_lock:
            _router_port = existing
        _probe_miss_until = 0.0
        _publish_status("ready", existing)
        logger.info("AI router: attached to existing instance on %d", existing)
        return existing

    try:
        from services.router_engine import EngineUnavailable, load_engine

        engine, how = await load_engine()
        logger.info("AI router: engine %s", how)
        server, port = engine.acquire_server(
            constants.ROUTER_BASE_PORT, constants.ROUTER_SPAN
        )
        if server is None:
            # Raced with another Kiri instance on the wanted port - attach.
            with _router_lock:
                _router_port = port
            _probe_miss_until = 0.0  # someone is listening: rescan live
            _publish_status("ready", port)
            logger.info("AI router: attached to instance on %d", port)
            return port
        server.access_log = False
        threading.Thread(target=server.serve_forever, daemon=True).start()
        with _router_lock:
            _router_server, _router_port = server, port
        _probe_miss_until = 0.0  # our own server now listens: rescan live
        _publish_status("ready", port)
        logger.info("AI router: embedded on %s:%d", constants.ROUTER_HOST, port)
        return port
    except EngineUnavailable as exc:
        # No engine and no cache: honest label. The next turn reports
        # unavailable — there is no second source (owner: router only).
        logger.warning("AI router: %s", exc)
        _mark_router_failed()
        return None
    except SystemExit:
        logger.warning(
            "AI router: no free port in %d..%d",
            constants.ROUTER_BASE_PORT,
            constants.ROUTER_BASE_PORT + constants.ROUTER_SPAN,
        )
        _mark_router_failed()
        return None
    except Exception as exc:
        logger.warning("AI router: failed to start: %r", exc)
        _mark_router_failed()
        return None


def router_base_url(port: int | None = None) -> str:
    """The OpenAI-compatible base URL for a port.

    Used to point the model client at whatever `ensure_router` settled on,
    rather than at a URL the user typed.
    """
    with _router_lock:
        port = _router_port if port is None else port
    if port is None:
        return constants.AI_DEFAULT_ROUTER_URL
    return f"http://{constants.ROUTER_HOST}:{port}/v1"


def current_url() -> str:
    """The URL the app is actually using right now, or "" with no router yet.

    Reads the held port under the lock, so a caller (Settings) never sees a
    torn value while `ensure_router` swaps the port.
    """
    with _router_lock:
        port = _router_port
    if port is None:
        return ""
    return f"http://{constants.ROUTER_HOST}:{port}/v1"


def shutdown() -> None:
    """Stop our embedded router. Registered with atexit by main."""
    stop_router()

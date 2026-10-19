"""The router status loop — the bridge between the router and the screens.

`services/router.py` owns the router and deliberately knows nothing about the
UI. Something has to carry a status change across, and this is that something:
it is the only module that holds a page.

Ported from DDGS's watchdog (`src/app_controller.py`, the router loop), with
the one change the owner asked for. Three properties it gets right there, each
learned the hard way:

1. **It starts the router, once, at boot.** Both references attach-or-embed at
   startup: the assistant is supposed to work with no setup, and a pill that
   says "Starting gateway…" until someone clicks a button is exactly the
   complaint — "when you open the app, I don't have to manually go and click
   start gateway". So the first tick attaches to a router already running, or
   embeds the app's own. If that fails (no engine cached, no network) the loop
   keeps observing and the Settings button still works — the failure path is
   not removed by the automatic path.
2. **It publishes only on a real change.** `_publish_status` already guards
   that, so the loop's own transition check is about the nudge, not the state.
3. **It nudges the visible pill, and nothing else.** A status change is only
   worth a repaint where a model name is on screen, and the pill's own
   signature check stops a tick from becoming a rebuild.

The loop costs one health check per tick against a port we already hold, or
nothing at all for `PROBE_MISS_TTL` after a full-scan miss — which is why it can
run every few seconds. See `constants.ROUTER_STATUS_INTERVAL_S`.
"""

from __future__ import annotations

import asyncio
import logging

from core import constants

logger = logging.getLogger("router_watchdog")

# The single live watchdog, if there is one. `router._publish_status` nudges it
# so a transition it just made repaints immediately instead of on the next tick;
# keeping the reference here rather than in `router` is what lets the router stay
# free of any UI knowledge.
_active: RouterStatusWatchdog | None = None


def current_watchdog() -> RouterStatusWatchdog | None:
    return _active


class RouterStatusWatchdog:
    """Reports the router's live status, and tells the UI when it moved.

    The session hook is a name, not an import: the chat screen outlives this
    module's knowledge of it, and `getattr` is what keeps the watchdog usable
    from a test that has no page at all.
    """

    def __init__(self, page=None, *, session_hook: str = "_assistant_session"):
        self._page = page
        self._session_hook = session_hook
        self._task: asyncio.Task | None = None
        self._wake = asyncio.Event()
        self._last: tuple[str, int | None] | None = None
        self._background = False

    # ── lifecycle ───────────────────────────────────────────────────────────

    def start(self) -> None:
        """Begin observing. Safe to call twice: the running loop is kept.

        Starting a second instance would otherwise orphan the first loop —
        still ticking, no longer reachable through `current_watchdog()`, and
        still holding a page. The previous one is stopped first.
        """
        global _active
        if self._task is not None and not self._task.done():
            return
        previous = _active
        if previous is not None and previous is not self:
            previous.stop()
        self._wake = asyncio.Event()
        self._task = asyncio.ensure_future(self._loop())
        _active = self
        logger.debug("Router status watchdog started")

    def stop(self) -> None:
        """Stop observing and drop the page.

        The page is released explicitly: the loop holds it strongly, and a
        reference kept after the view is closed is exactly the kind of leak
        that keeps a whole screen tree alive. `task.cancel()` is best-effort —
        from atexit the loop may already be closed, in which case there is
        nothing left to cancel and that is not an error.
        """
        global _active
        if _active is self:
            _active = None
        task, self._task = self._task, None
        self._page = None
        if task is not None and not task.done():
            try:
                task.cancel()
            except Exception:
                logger.debug("watchdog cancel failed", exc_info=True)

    def wake(self) -> None:
        """Re-read now instead of at the next tick.

        A turn that just embedded a router should not wait up to 3 seconds for
        its own header to notice.

        Callable from any thread, and guarded: `router._publish_status` reaches
        this from `stop_router()`, which is also an atexit handler, and
        `asyncio.Event.set` is only safe on the loop that owns it.
        """
        event = self._wake
        try:
            event.set()
        except Exception:
            logger.debug("watchdog wake failed", exc_info=True)

    def set_background(self, background: bool) -> None:
        """Backgrounded windows tick slowly; the resume path wakes the loop."""
        if background == self._background:
            return
        self._background = background
        self.wake()

    # ── the loop ────────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        from core.state import state
        from services import router

        # Attach-or-embed ONCE, before the first observe. Both references do
        # exactly this at boot — DDGS `app_controller.py:160` fires
        # `_refresh_ai_catalog` (which calls `ensure_router()`), lm-router
        # `main.py:296-297` runs `_start_gateway_quiet` — because the assistant
        # is supposed to work with no setup. Waiting for a tap is what the owner
        # called out: "I don't have to manually go and click start gateway."
        #
        # Failure is not fatal and does not remove the button: if there is no
        # cached engine and no network, the pill stays honest ("Offline" + Start
        # router) and the Settings action still works. Probes continue below.
        try:
            port = await router.ensure_router()
            if port:
                logger.info("AI router: ready on port %s at boot", port)
                # Read the catalog while we are here, so the pill can name a
                # model on the first paint instead of "Starting gateway…".
                try:
                    from services import model_catalog

                    await model_catalog.refresh_catalog(router.router_base_url(port))
                except Exception:
                    logger.debug("boot catalog fetch failed", exc_info=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.info("AI router: not started at boot (%s); will keep watching", exc)

        while True:
            # Probe first, then wait: waiting first delays the very first
            # observation by a full interval, which is exactly the window in
            # which the user is looking at a pill that says nothing.
            try:
                status, port = await router.probe_router()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # A probe that raises is a probe that learned nothing: the
                # previous answer stands until the next tick.
                logger.debug("Router status probe failed: %r", exc)
                status = port = None
            else:
                current = (status, port)
                if self._last is None:
                    # The first observation is compared against what the app
                    # believes right now, not against nothing: the boot default
                    # is "starting", and a router that is already up must
                    # correct it rather than wait for the app to notice.
                    believed = (
                        str(getattr(state, "ai_router_status", "") or ""),
                        getattr(state, "ai_router_port", None),
                    )
                else:
                    believed = self._last
                if current != believed:
                    logger.info("AI router status: %s (port %s)", status, port)
                    self._last = current
                    # Publishing IS the point: without it a router killed by
                    # something other than this app never moves the screens,
                    # because nothing else writes the state.
                    try:
                        router._publish_status(status, port)
                    except Exception:
                        logger.debug("status publish failed", exc_info=True)
                    self._notify()

            interval = (
                constants.ROUTER_STATUS_INTERVAL_BG_S
                if self._background
                else constants.ROUTER_STATUS_INTERVAL_S
            )
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=interval)
            except TimeoutError:
                pass
            self._wake.clear()

    def _notify(self) -> None:
        """Tell the visible pill to re-read. No page, no nudge, no error."""
        session = self._session()
        refresh = getattr(session, "refresh_model_chip", None)
        if callable(refresh):
            try:
                refresh()
            except Exception:
                logger.debug("Router status nudge failed", exc_info=True)

    def _session(self):
        page = self._page
        if page is None:
            return None
        return getattr(page, self._session_hook, None)

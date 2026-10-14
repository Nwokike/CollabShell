"""The router status loop — the bridge between the router and the screens.

`services/router.py` owns the router and deliberately knows nothing about the
UI. Something has to carry a status change across, and this is that something:
it is the only module that holds a page.

Ported from DDGS's watchdog (`src/app_controller.py`, the router loop). Three
properties it gets right, each learned the hard way there:

1. **It only observes.** It never starts, stops, or re-points a router. Starting
   is the turn path's job and the user's job (a Settings button and a pill
   action); a loop that quietly embedded a router would make "Start router"
   look like it did nothing when it had already been done.
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
        """Begin observing. Safe to call twice: the running loop is kept."""
        global _active
        if self._task is not None and not self._task.done():
            return
        self._wake = asyncio.Event()
        self._task = asyncio.ensure_future(self._loop())
        _active = self
        logger.debug("Router status watchdog started")

    def stop(self) -> None:
        global _active
        if _active is self:
            _active = None
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()

    def wake(self) -> None:
        """Re-read now instead of at the next tick.

        A turn that just embedded a router should not wait up to 3 seconds for
        its own header to notice.
        """
        self._wake.set()

    def set_background(self, background: bool) -> None:
        """Backgrounded windows tick slowly; the resume path wakes the loop."""
        if background == self._background:
            return
        self._background = background
        self.wake()

    # ── the loop ────────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        from services import router

        while True:
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

            try:
                status, port = await router.probe_router()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # A probe that raises is a probe that learned nothing: the
                # previous answer stands until the next tick.
                logger.debug("Router status probe failed: %r", exc)
                continue

            if (status, port) == self._last:
                continue
            changed = self._last is not None
            self._last = (status, port)
            if not changed:
                # The first tick only seeds the baseline: publishing here would
                # paint a state the user never watched change.
                continue
            logger.info("AI router status: %s (port %s)", status, port)
            self._notify()

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

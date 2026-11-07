"""Keep the active Colab runtime alive while the app is open.

Colab's backend idle-prunes a VM after a few minutes without *kernel
activity*. Upstream google-colab-cli removed its client-side keep-alive
daemon (PR #144): liveness is now driven by kernel activity and active
connections only — a WebSocket ping does NOT reset the idle timer. So while
a session is active we execute a no-op ``pass`` well inside Colab's idle
window, and on failure we re-sync the session list so the UI and the AI
assistant see fresh server-side state instead of a stale "idle" record.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("colab_keepalive")

# Colab idle-prunes VMs after ~7-8 min without kernel activity; stay well
# inside that window.
KEEPALIVE_INTERVAL_SEC = 240.0
KEEPALIVE_CODE = "pass  # ColabShell keep-alive: resets Colab's idle timer\n"


class SessionKeepAlive:
    """Background task that keeps the active session's runtime alive."""

    def __init__(self, colab_service, state):
        self._colab = colab_service
        self._state = state
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def _auth_method(self) -> str:
        return str(getattr(self._state, "auth_method", "oauth2") or "oauth2")

    async def astart(self) -> None:
        """Run the keep-alive loop until cancelled (astop/shutdown)."""
        self._task = asyncio.create_task(self._loop())
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    async def astop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    def _target_session(self) -> str:
        """The session to keep alive: the open one if any, else the first listed.

        A session merely LISTED on the home tab still counts — Colab
        idle-prunes it after ~7-8 min without kernel activity regardless of
        whether the user opened it (that is how a listed session vanished).
        """
        name = str(getattr(self._state, "active_session_name", "") or "").strip()
        if name:
            return name
        sessions = getattr(self._state, "active_sessions", None) or []
        for entry in sessions:
            if isinstance(entry, dict):
                candidate = str(entry.get("name", "") or "").strip()
            else:
                candidate = str(getattr(entry, "name", "") or "").strip()
            if candidate:
                return candidate
        return ""

    async def _loop(self) -> None:
        failures = 0
        while True:
            await asyncio.sleep(KEEPALIVE_INTERVAL_SEC)
            name = self._target_session()
            if not name:
                continue
            try:
                await self._colab.exec_code(
                    KEEPALIVE_CODE,
                    name,
                    timeout=15.0,
                    auth_method=self._auth_method(),
                    intercept_oauth=False,
                )
                failures = 0
            except Exception as exc:
                # The runtime may have been idle-pruned or the token expired:
                # re-sync so everyone sees the fresh server-side state.
                failures += 1
                logger.warning(
                    "keep-alive exec failed for %s (failure #%d): %s",
                    name,
                    failures,
                    exc,
                )
                try:
                    await self._colab.list_sessions(self._auth_method())
                except Exception:
                    logger.warning("keep-alive list_sessions failed", exc_info=True)

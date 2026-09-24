"""Daily AI credit ledger — 50 per rolling 24 hours, one per model call.

A call is one model request, so a task that thinks, searches, fetches, then
answers spends four. A call that produced nothing (rate limit, dropped
connection) is refunded — users are not charged for our failures.

Device-local for now: grants live in SharedPreferences, which a reinstall
or clear-data resets. Server-backed balance comes with the premium work.
"""

from __future__ import annotations

import logging
import time

from core import constants

logger = logging.getLogger("ai.credits")

DAILY_CREDITS = 50
_WINDOW_SECONDS = 24 * 60 * 60


class CreditsLedger:
    def __init__(self, storage):
        self._storage = storage

    async def _load(self) -> tuple[float, int]:
        try:
            window = float(await self._storage.get(constants.STORAGE_AI_WINDOW) or 0.0)
        except (TypeError, ValueError):
            window = 0.0
        try:
            used = int(await self._storage.get(constants.STORAGE_AI_USED) or 0)
        except (TypeError, ValueError):
            used = 0
        return window, max(used, 0)

    async def _save(self, window: float, used: int) -> None:
        await self._storage.set(constants.STORAGE_AI_WINDOW, str(window))
        await self._storage.set(constants.STORAGE_AI_USED, str(used))

    async def _roll(self, window: float, used: int) -> tuple[float, int]:
        """Start a fresh window once the old one is 24h old."""
        now = time.time()
        if now - window >= _WINDOW_SECONDS:
            return now, 0
        return window, used

    async def remaining(self) -> int:
        window, used = await self._load()
        _, used = await self._roll(window, used)
        return max(DAILY_CREDITS - used, 0)

    async def spend(self, count: int = 1) -> bool:
        """Charge `count` credits. False means the user is out."""
        window, used = await self._load()
        window, used = await self._roll(window, used)
        if used + count > DAILY_CREDITS:
            return False
        await self._save(window, used + count)
        return True

    async def refund(self, count: int = 1) -> None:
        window, used = await self._load()
        window, used = await self._roll(window, used)
        await self._save(window, max(used - count, 0))

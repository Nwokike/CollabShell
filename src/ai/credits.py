"""Daily AI credit ledger — 50 per rolling 24 hours, 2 per model call.

A "turn" is one model call. Asking "hello" and getting a reply is one
turn; a task that thinks, searches, fetches, then answers is four turns
and costs 8 credits. A call that produced nothing (rate limit, dropped
connection) is refunded — users are not charged for our failures.
Credits are only ever spent, never deleted; the window resets on its own.

Device-local for now: grants live in SharedPreferences, which a reinstall
or clear-data resets. Server-backed balance comes with the premium work.
"""

from __future__ import annotations

import asyncio
import logging
import time

from core import constants

logger = logging.getLogger("ai.credits")

DAILY_CREDITS = 50
COST_PER_TURN = 2
_WINDOW_SECONDS = 24 * 60 * 60


class CreditsLedger:
    def __init__(self, storage):
        self._storage = storage
        # Spend/refund is read-modify-write over async storage; without this
        # two concurrent operations (spend + refund, double send) lose one.
        self._lock = asyncio.Lock()

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

    def _roll(self, window: float, used: int) -> tuple[float, int]:
        """Start a fresh window once the old one is 24h old.

        Device clock only: a forward jump refills early, a rollback delays
        it. Server time replaces both when the balance moves server-side.
        """
        now = time.time()
        if now - window >= _WINDOW_SECONDS:
            return now, 0
        return window, used

    async def remaining(self) -> int:
        async with self._lock:
            window, used = await self._load()
            _, used = self._roll(window, used)
            return max(DAILY_CREDITS - used, 0)

    async def spend(self, count: int = COST_PER_TURN) -> bool:
        """Charge `count` credits. False means the user is out."""
        async with self._lock:
            window, used = await self._load()
            window, used = self._roll(window, used)
            if used + count > DAILY_CREDITS:
                return False
            await self._save(window, used + count)
            return True

    async def refund(self, count: int = COST_PER_TURN) -> None:
        async with self._lock:
            window, used = await self._load()
            window, used = self._roll(window, used)
            await self._save(window, max(used - count, 0))

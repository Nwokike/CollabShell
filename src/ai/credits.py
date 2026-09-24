"""Daily AI credit ledger — 50 free, 200 premium, plus ad-earned credits.

A "turn" is one model call. Asking "hello" and getting a reply is one
turn; a task that thinks, searches, fetches, then answers is four turns
and costs 8 credits. A call that produced nothing (rate limit, dropped
connection, empty reply) is refunded — users are not charged for our
failures.

Two kinds of credit, and the difference matters:

- **Daily credits** refill on a rolling 24-hour window. They cannot be
  bought and never accumulate: a rolling window is kinder to someone who
  checks in twice, because a single big day still refills.
- **Bonus credits** come from watching an ad and never expire. They are
  counted in the same balance, so "50 credits left" means "50 you can
  spend", not "50 before your bonus is hidden".

Premium raises the daily grant from 50 to 200. Credits are only ever
spent, never deleted; the window resets on its own.

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
PREMIUM_DAILY_CREDITS = 200
# What a completed rewarded ad is worth. Small on purpose: it buys a
# handful of good questions, not a day of unlimited use.
AD_CREDIT_REWARD = 10
COST_PER_TURN = 2
_WINDOW_SECONDS = 24 * 60 * 60


def daily_cap() -> int:
    """The daily grant for whoever is using the app right now."""
    from core.state import state

    return PREMIUM_DAILY_CREDITS if state.is_premium else DAILY_CREDITS


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

    async def _load_bonus(self) -> int:
        try:
            return max(int(await self._storage.get(constants.STORAGE_AI_BONUS) or 0), 0)
        except (TypeError, ValueError):
            return 0

    async def _save_bonus(self, bonus: int) -> None:
        await self._storage.set(constants.STORAGE_AI_BONUS, str(max(bonus, 0)))

    async def _load_bonus_spent(self) -> int:
        """How much of the bonus has been charged, so a refund knows to give
        it back there. Without this, a refund would hand back expiring daily
        credits and quietly eat the ad credits the user earned."""
        try:
            return max(
                int(await self._storage.get(constants.STORAGE_AI_BONUS_SPENT) or 0), 0
            )
        except (TypeError, ValueError):
            return 0

    async def _save_bonus_spent(self, spent: int) -> None:
        await self._storage.set(constants.STORAGE_AI_BONUS_SPENT, str(max(spent, 0)))

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
        """Everything the user can spend right now: daily grant, bonus, and
        what is left of the daily grant today."""
        async with self._lock:
            window, used = await self._load()
            _, used = self._roll(window, used)
            bonus = await self._load_bonus()
            return max(daily_cap() - used, 0) + bonus

    async def daily_remaining(self) -> int:
        """Just the part that refills tomorrow."""
        async with self._lock:
            window, used = await self._load()
            _, used = self._roll(window, used)
            return max(daily_cap() - used, 0)

    async def bonus(self) -> int:
        async with self._lock:
            return await self._load_bonus()

    async def spend(self, count: int = COST_PER_TURN) -> bool:
        """Charge `count` credits. False means the user is at zero.

        A turn is never aborted for being 1 credit short: it starts, the
        balance clamps at zero, and the work completes — losing a user's
        in-flight work over one credit is worse than one turn free.
        """
        async with self._lock:
            window, used = await self._load()
            window, used = self._roll(window, used)
            bonus = await self._load_bonus()
            bonus_spent = await self._load_bonus_spent()

            # Daily grant first, then ad-earned credits: the bonus is the
            # user's reward for watching an ad, and it is the part they
            # expect to still be there.
            need = count
            from_daily = min(used + need, daily_cap())
            drawn_daily = from_daily - used
            need -= drawn_daily
            drawn_bonus = 0
            if need > 0:
                if bonus < need:
                    if used >= daily_cap() and bonus <= 0:
                        return False
                    # Short: spend what is there, clamp at zero, run anyway.
                    drawn_bonus = bonus
                    bonus = 0
                else:
                    drawn_bonus = need
                    bonus -= need

            used = from_daily
            await self._save(window, used)
            await self._save_bonus(bonus)
            if drawn_bonus:
                await self._save_bonus_spent(bonus_spent + drawn_bonus)
            return True

    async def refund(self, count: int = COST_PER_TURN) -> None:
        """Give back what a failed call cost, in the same place it came from.

        Spend draws from the daily grant first and ad credits second, so a
        refund has to walk that in reverse. Refunding into bonus
        unconditionally would mint credits the user never earned — a second
        refund on the same turn would quietly top them up.
        """
        async with self._lock:
            window, used = await self._load()
            window, used = self._roll(window, used)
            bonus = await self._load_bonus()
            bonus_spent = await self._load_bonus_spent()

            # Ad credits first, because that is where a charge is recorded
            # as having come from; only the overflow goes back to daily.
            to_bonus = min(count, bonus_spent)
            bonus += to_bonus
            bonus_spent -= to_bonus
            from_daily = min(count - to_bonus, used)
            used -= from_daily
            await self._save(window, used)
            await self._save_bonus(bonus)
            await self._save_bonus_spent(bonus_spent)

    async def add_bonus(self, amount: int = AD_CREDIT_REWARD) -> int:
        """Credit an earned reward. Returns the new bonus total."""
        async with self._lock:
            bonus = await self._load_bonus() + max(amount, 0)
            await self._save_bonus(bonus)
            return bonus

    async def cap(self) -> int:
        """The daily grant in force right now (50, or 200 when premium)."""
        return daily_cap()


__all__ = [
    "AD_CREDIT_REWARD",
    "COST_PER_TURN",
    "DAILY_CREDITS",
    "PREMIUM_DAILY_CREDITS",
    "CreditsLedger",
    "daily_cap",
]

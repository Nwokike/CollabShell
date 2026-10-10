"""Assistant credits — metering for AI use.

Owns the balance and enforces the daily cap. Deliberately SOFT: a low balance
never revokes an in-flight turn, because killing a reply the user is watching
is worse than a small overspend. The counter is clamped at zero so it can
never go negative, and an idempotent commit stops a double-charge if the same
transaction is settled twice.

Three-phase settlement follows the proven DDGS shape:
    reserve()      -> hold credits for a turn in progress
    commit(tx, n)  -> charge exactly what was used
    rollback(tx)   -> release the hold without charging

A reserve that is never settled auto-releases after ROLLBACK_SECONDS, so a
crashed turn cannot strand the user's balance.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import time

logger = logging.getLogger("credit_service")

# Caps and the step cost live in core.constants so the UI copy generated from
# them can never drift from what ai_credits.run_metered_turn charges.
from core.constants import (
    COST_STEP,
    DAILY_FREE_CREDITS,
    DAILY_PREMIUM_CREDITS,
)

# A hold older than this is released without charging.
ROLLBACK_SECONDS = 240.0

UTC_MIDNIGHT_RESET = True


class NotEnoughCredits(Exception):
    """Raised when the balance cannot cover the request (never mid-turn)."""

    def __init__(self, balance: int):
        super().__init__(balance)
        self.balance = balance


def _today_utc() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")


class CreditService:
    """Balance + daily cap, persisted through the app StorageService."""

    def __init__(self, storage=None):
        self._storage = storage
        self._lock = asyncio.Lock()
        self._balance: int | None = None
        self._day: str = _today_utc()
        # tx -> (amount, opened_at). The timestamp is what makes the sweep
        # safe: without it every hold looks "expired" and a live turn is
        # released mid-flight, which both frees the turn and lets the next
        # reserve ignore it.
        self._holds: dict[str, tuple[int, float]] = {}
        self._settled: set[str] = set()

    # ── daily cap ──────────────────────────────────────────────────────────

    def daily_cap(self, is_premium: bool = False) -> int:
        return DAILY_PREMIUM_CREDITS if is_premium else DAILY_FREE_CREDITS

    def _reset_if_new_day(self) -> None:
        """Flat UTC reset with no rollover: yesterday's unused credits go."""
        if UTC_MIDNIGHT_RESET and self._day != _today_utc():
            self._day = _today_utc()
            self._balance = None

    async def get_balance(self, is_premium: bool = False) -> int:
        """Balance remaining today._refills to the cap on a new UTC day."""
        async with self._lock:
            self._reset_if_new_day()
            if self._balance is None:
                self._balance = self.daily_cap(is_premium)
            return max(0, self._balance)

    async def add_credits(self, amount: int, is_premium: bool = False) -> int:
        async with self._lock:
            self._reset_if_new_day()
            if self._balance is None:
                self._balance = self.daily_cap(is_premium)
            self._balance = max(0, self._balance + int(amount))
            return self._balance

    # ── settlement ─────────────────────────────────────────────────────────

    async def reserve(
        self, amount: int = COST_STEP, is_premium: bool = False
    ) -> str | None:
        """Hold credits for a turn. Returns a transaction id, or None when the
        balance cannot cover it (the caller reports out-of-credits).

        A hold reduces spendable balance immediately so a burst of turns cannot
        each see the full balance.
        """
        async with self._lock:
            self._reset_if_new_day()
            balance = (
                self._balance
                if self._balance is not None
                else self.daily_cap(is_premium)
            )
            available = balance - sum(a for a, _ in self._holds.values())
            if available < amount:
                return None
            import uuid

            tx = uuid.uuid4().hex
            self._holds[tx] = (amount, time.monotonic())
            return tx

    async def reserve_more(self, tx: str | None, amount: int) -> bool:
        """Extend a hold. Never blocks: a False return means "keep going",
        because stopping a turn the user is watching is worse than overspending.
        """
        if not tx:
            return False
        async with self._lock:
            current = self._holds.get(tx)
            if current is None:
                return False
            # Keep the original open time: a hold that has grown is still the
            # same turn, and resetting the clock would let a long turn starve
            # the sweep forever.
            self._holds[tx] = (current[0] + amount, current[1])
            return True

    async def commit(
        self, tx: str | None, amount: int | None = None, is_premium: bool = False
    ) -> int:
        """Charge a settled turn and release its hold.

        Idempotent: a transaction already committed is ignored, so a double
        settle cannot double-charge. ``amount=None`` charges the whole hold.
        """
        if not tx:
            return await self.get_balance(is_premium)
        async with self._lock:
            self._reset_if_new_day()
            if tx in self._settled:
                return max(0, self._balance or 0)
            self._settled.add(tx)
            held = self._holds.pop(tx, (COST_STEP, 0.0))[0]
            charge = held if amount is None else max(0, int(amount))
            if self._balance is None:
                self._balance = self.daily_cap(is_premium)
            self._balance = max(0, self._balance - charge)
            return self._balance

    async def rollback(self, tx: str | None, is_premium: bool = False) -> int:
        """Release a hold without charging (cancelled or failed turn)."""
        if not tx:
            return await self.get_balance(is_premium)
        async with self._lock:
            self._holds.pop(tx, None)
            self._settled.add(tx)
            return max(0, self._balance or self.daily_cap(is_premium))

    async def available(self, is_premium: bool = False) -> int:
        """Spendable now: balance minus outstanding holds."""
        async with self._lock:
            self._reset_if_new_day()
            balance = (
                self._balance
                if self._balance is not None
                else self.daily_cap(is_premium)
            )
            return max(0, balance - sum(a for a, _ in self._holds.values()))

    async def charge(self, amount: int, is_premium: bool = False) -> int:
        """Subtract directly, with no hold.

        The hold-less half of settlement: `reserve` is best-effort and fails at
        balance 1, and credits must never block work, so the turn runs anyway
        and pays here instead. Clamps at zero like commit.
        """
        async with self._lock:
            self._reset_if_new_day()
            if self._balance is None:
                self._balance = self.daily_cap(is_premium)
            self._balance = max(0, self._balance - max(0, int(amount)))
            return self._balance

    async def sweep_expired_holds(self, max_age_sec: float = ROLLBACK_SECONDS) -> int:
        """Release holds stranded by a crashed turn, and refuse their charge.

        Only holds older than ``max_age_sec`` are touched. Age matters: a turn
        that is still streaming has an open hold, and releasing it would both
        free that turn's charge (a sweep marks it settled, so a later ``commit``
        becomes a no-op) *and* let the next ``reserve`` ignore it, overspending
        past the daily cap.

        Returns how many holds were released.
        """
        async with self._lock:
            self._reset_if_new_day()
            now = time.monotonic()
            expired = [
                tx
                for tx, (_amount, opened_at) in self._holds.items()
                if now - opened_at >= max_age_sec
            ]
            for tx in expired:
                del self._holds[tx]
            # Marked settled on purpose: the hold is gone, so a late commit must
            # not charge for a turn whose hold we just wrote off.
            self._settled.update(expired)
            return len(expired)

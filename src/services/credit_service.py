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
    STORAGE_CREDITS,
    STORAGE_LAST_RESET,
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

    def daily_cap(self) -> int:
        """The cap for WHO IS LOGGED IN RIGHT NOW, read live from state.

        DDGS parity (credit_service.py:242-248): the premium flag is never a
        parameter. A parameter made the boot order a trap — main.py ran
        initialize() before the licence loaded, the day's reset stamped the
        FREE cap, and a paying user sat at 50 until midnight. state.is_premium
        at the moment of the read is always the truth.
        """
        from core.state import state

        return DAILY_PREMIUM_CREDITS if getattr(state, "is_premium", False) else DAILY_FREE_CREDITS

    def _sync_state(self, balance: int) -> None:
        """Mirror the balance into the observable so readers (wallet dialog,
        pill) can use it synchronously, DDGS-style."""
        try:
            from core.state import state

            state.credits_remaining = int(balance)
        except Exception:
            pass

    async def _check_daily_reset(self) -> None:
        """Flat UTC reset with no rollover: yesterday's unused credits go."""
        if not UTC_MIDNIGHT_RESET:
            return
        today = _today_utc()
        if self._storage is not None:
            last_reset = await self._storage.get(STORAGE_LAST_RESET)
            if last_reset != today:
                new_balance = self.daily_cap()
                await self._storage.set(STORAGE_CREDITS, str(new_balance))
                await self._storage.set(STORAGE_LAST_RESET, today)
                self._balance = new_balance
                self._day = today
                self._sync_state(new_balance)
                return
            if self._balance is None:
                val = await self._storage.get(STORAGE_CREDITS)
                if val is not None:
                    try:
                        self._balance = int(val)
                    except (TypeError, ValueError):
                        self._balance = self.daily_cap()
                else:
                    self._balance = self.daily_cap()
                self._day = today
                self._sync_state(self._balance)
            return

        if self._day != today:
            self._day = today
            self._balance = self.daily_cap()
            self._sync_state(self._balance)

    async def initialize(self) -> int:
        """Load credits from storage, reset if new day. Returns current balance."""
        return await self.get_balance()

    async def get_balance(self) -> int:
        """Balance remaining today. Refills to the cap on a new UTC day."""
        await self._check_daily_reset()
        async with self._lock:
            if self._balance is None:
                self._balance = self.daily_cap()
            balance = max(0, self._balance)
            self._sync_state(balance)
            return balance

    async def add_credits(self, amount: int) -> int:
        await self._check_daily_reset()
        async with self._lock:
            if self._balance is None:
                self._balance = self.daily_cap()
            self._balance = max(0, self._balance + int(amount))
            if self._storage is not None:
                await self._storage.set(STORAGE_CREDITS, str(self._balance))
            self._sync_state(self._balance)
            return self._balance

    # ── settlement ─────────────────────────────────────────────────────────

    async def reserve(
        self, amount: int = COST_STEP
    ) -> str | None:
        """Hold credits for a turn. Returns a transaction id, or None when the
        balance cannot cover it (the caller reports out-of-credits).

        A hold reduces spendable balance immediately so a burst of turns cannot
        each see the full balance.
        """
        await self._check_daily_reset()
        async with self._lock:
            balance = (
                self._balance
                if self._balance is not None
                else self.daily_cap()
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
        self, tx: str | None, amount: int | None = None
    ) -> int:
        """Charge a settled turn and release its hold.

        Idempotent: a transaction already committed is ignored, so a double
        settle cannot double-charge. ``amount=None`` charges the whole hold.
        """
        if not tx:
            return await self.get_balance()
        await self._check_daily_reset()
        async with self._lock:
            if tx in self._settled:
                return max(0, self._balance or 0)
            self._settled.add(tx)
            held = self._holds.pop(tx, (COST_STEP, 0.0))[0]
            charge = held if amount is None else max(0, int(amount))
            if self._balance is None:
                self._balance = self.daily_cap()
            self._balance = max(0, self._balance - charge)
            if self._storage is not None:
                await self._storage.set(STORAGE_CREDITS, str(self._balance))
            self._sync_state(self._balance)
            return self._balance

    async def rollback(self, tx: str | None) -> int:
        """Release a hold without charging (cancelled or failed turn)."""
        if not tx:
            return await self.get_balance()
        await self._check_daily_reset()
        async with self._lock:
            self._holds.pop(tx, None)
            self._settled.add(tx)
            return max(0, self._balance or self.daily_cap())

    async def available(self) -> int:
        """Spendable now: balance minus outstanding holds."""
        await self._check_daily_reset()
        async with self._lock:
            balance = (
                self._balance
                if self._balance is not None
                else self.daily_cap()
            )
            return max(0, balance - sum(a for a, _ in self._holds.values()))

    async def charge(self, amount: int) -> int:
        """Subtract directly, with no hold.

        The hold-less half of settlement: `reserve` is best-effort and fails at
        balance 1, and credits must never block work, so the turn runs anyway
        and pays here instead. Clamps at zero like commit.
        """
        await self._check_daily_reset()
        async with self._lock:
            if self._balance is None:
                self._balance = self.daily_cap()
            self._balance = max(0, self._balance - max(0, int(amount)))
            if self._storage is not None:
                await self._storage.set(STORAGE_CREDITS, str(self._balance))
            self._sync_state(self._balance)
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
        await self._check_daily_reset()
        async with self._lock:
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

    async def astart(self, interval_sec: float = 60.0) -> None:
        """Background loop: release holds stranded by crashed turns.

        ``sweep_expired_holds`` only runs when called; without this loop a
        crash between reserve() and commit/rollback would hold credits until
        the next launch.
        """
        while True:
            await asyncio.sleep(interval_sec)
            try:
                released = await self.sweep_expired_holds()
                if released:
                    logger.info("Released %d expired credit holds", released)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.debug("Hold sweep failed", exc_info=True)

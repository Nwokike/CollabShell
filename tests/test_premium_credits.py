"""Premium credits: a bigger daily grant, and ad-earned credits that stay.

Two things must be true at once and they pull against each other:

- a paying user gets 200 a day, a free user 50, and the grant refills;
- credits earned by watching an ad are never deleted by a window reset, and
  a refund gives back exactly what was taken — no more.

That second half is where a credit economy quietly pays users for free or
eats their balance, so it is tested directly.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ai.credits import (
    AD_CREDIT_REWARD,
    COST_PER_TURN,
    DAILY_CREDITS,
    PREMIUM_DAILY_CREDITS,
    CreditsLedger,
    daily_cap,
)
from core.state import state


class FakeStorage:
    def __init__(self):
        self.d: dict = {}

    async def get(self, k, default=None):
        return self.d.get(k, default)

    async def set(self, k, v):
        self.d[k] = v


@pytest.fixture(autouse=True)
def free_user():
    """Every test starts as a free user and leaves no premium state behind."""
    state.is_premium = False
    state.premium_source = ""
    state.premium_product = ""
    state.premium_offline = False
    yield
    state.is_premium = False
    state.premium_source = ""
    state.premium_product = ""


def _ledger():
    return CreditsLedger(FakeStorage())


# ── The daily grant ────────────────────────────────────────────────────


def test_a_free_user_gets_fifty():
    ledger = _ledger()
    assert daily_cap() == DAILY_CREDITS == 50
    assert asyncio.run(ledger.remaining()) == 50


def test_a_premium_user_gets_two_hundred():
    ledger = _ledger()
    state.is_premium = True
    assert daily_cap() == PREMIUM_DAILY_CREDITS == 200
    assert asyncio.run(ledger.remaining()) == 200


def test_becoming_premium_raises_the_balance_immediately():
    ledger = _ledger()
    assert asyncio.run(ledger.remaining()) == 50
    state.is_premium = True
    assert asyncio.run(ledger.remaining()) == 200, "no restart required"


def test_spending_comes_out_of_the_daily_grant():
    ledger = _ledger()
    state.is_premium = True

    async def run():
        await ledger.spend()
        return await ledger.remaining()

    assert asyncio.run(run()) == PREMIUM_DAILY_CREDITS - COST_PER_TURN


# ── Ad-earned credits ──────────────────────────────────────────────────


def test_watching_an_ad_adds_credits_that_do_not_expire():
    ledger = _ledger()

    async def run():
        await ledger.add_bonus()
        return await ledger.remaining(), await ledger.bonus()

    remaining, bonus = asyncio.run(run())
    assert bonus == AD_CREDIT_REWARD
    assert remaining == DAILY_CREDITS + AD_CREDIT_REWARD


def test_bonus_credits_survive_a_window_reset():
    ledger = _ledger()
    storage = ledger._storage

    async def run():
        await ledger.add_bonus(30)
        await ledger.spend()  # 2 from the daily grant
        # Pretend the 24h window rolled over.
        await storage.set("colab_ai_credits_window", "1")
        return await ledger.remaining(), await ledger.bonus()

    remaining, bonus = asyncio.run(run())
    assert bonus == 30, "the OS or the clock cannot take earned credits"
    assert remaining == DAILY_CREDITS + 30


def test_bonus_is_only_spent_after_the_daily_grant():
    ledger = _ledger()
    storage = ledger._storage

    async def run():
        await ledger.add_bonus(10)
        # Burn the daily grant: 25 calls of 2 credits.
        for _ in range(DAILY_CREDITS // COST_PER_TURN):
            assert await ledger.spend()
        return await ledger.remaining(), await ledger.bonus()

    remaining, bonus = asyncio.run(run())
    assert bonus == 10, "the daily grant is spent first"
    assert remaining == 10
    assert storage is not None


def test_spending_past_the_daily_grant_uses_bonus():
    ledger = _ledger()

    async def run():
        await ledger.add_bonus(6)
        for _ in range(DAILY_CREDITS // COST_PER_TURN + 2):
            await ledger.spend()
        return await ledger.remaining(), await ledger.bonus()

    remaining, bonus = asyncio.run(run())
    assert bonus == 2, "6 ad credits minus two more calls of 2"
    assert remaining == 2


def test_at_zero_the_next_call_is_refused():
    ledger = _ledger()

    async def run():
        while await ledger.spend():
            pass
        return await ledger.spend(), await ledger.remaining()

    allowed, remaining = asyncio.run(run())
    assert allowed is False
    assert remaining == 0


# ── Refunds ────────────────────────────────────────────────────────────


def test_a_refund_returns_exactly_what_was_taken():
    ledger = _ledger()

    async def run():
        await ledger.spend()
        await ledger.refund()
        return await ledger.remaining(), await ledger.bonus()

    remaining, bonus = asyncio.run(run())
    assert remaining == DAILY_CREDITS
    assert bonus == 0, "a refund must not mint ad credits"


def test_a_double_refund_does_not_pay_the_user():
    ledger = _ledger()

    async def run():
        await ledger.spend()
        await ledger.refund()
        await ledger.refund()
        return await ledger.remaining(), await ledger.bonus()

    remaining, bonus = asyncio.run(run())
    assert remaining == DAILY_CREDITS
    assert bonus == 0


def test_a_refund_returns_bonus_credits_that_were_spent():
    ledger = _ledger()

    async def run():
        await ledger.add_bonus(4)
        for _ in range(DAILY_CREDITS // COST_PER_TURN + 1):
            await ledger.spend()  # the last call comes out of bonus
        before = await ledger.bonus()
        await ledger.refund()
        return before, await ledger.bonus()

    before, after = asyncio.run(run())
    assert before == 2
    assert after == 4, "the ad credits the user earned come back"


def test_a_refund_cannot_push_the_balance_over_the_cap():
    ledger = _ledger()

    async def run():
        await ledger.refund()  # refunding a call that never happened
        return await ledger.remaining()

    assert asyncio.run(run()) == DAILY_CREDITS


def test_bonus_never_goes_negative():
    ledger = _ledger()

    async def run():
        await ledger.refund(100)
        return await ledger.bonus(), await ledger.remaining()

    bonus, remaining = asyncio.run(run())
    assert bonus == 0
    assert remaining == DAILY_CREDITS

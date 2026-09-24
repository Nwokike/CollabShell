"""Credit ledger: 2 per turn, the cap, refunds, and no lost updates."""

import asyncio

from ai.credits import COST_PER_TURN, DAILY_CREDITS, CreditsLedger


class FakeStorage:
    def __init__(self):
        self.d = {}

    async def get(self, k, default=None):
        return self.d.get(k, default)

    async def set(self, k, v):
        self.d[k] = v


def _ledger():
    return CreditsLedger(FakeStorage())


def test_cost_is_two_per_turn():
    assert COST_PER_TURN == 2
    assert DAILY_CREDITS == 50


def test_turn_costs_two_credits():
    ledger = _ledger()

    async def run():
        assert await ledger.remaining() == DAILY_CREDITS
        assert await ledger.spend()
        return await ledger.remaining()

    assert asyncio.run(run()) == DAILY_CREDITS - 2


def test_cap_refuses_beyond_daily():
    ledger = _ledger()

    async def run():
        for _ in range(DAILY_CREDITS // COST_PER_TURN):
            assert await ledger.spend()
        assert await ledger.remaining() == 0
        return not await ledger.spend()

    assert asyncio.run(run())


def test_refund_returns_credits_and_never_goes_negative():
    ledger = _ledger()

    async def run():
        await ledger.spend()
        await ledger.refund()
        await ledger.refund()
        return await ledger.remaining()

    assert asyncio.run(run()) == DAILY_CREDITS


def test_concurrent_spend_does_not_lose_updates():
    ledger = _ledger()

    async def run():
        await asyncio.gather(*(ledger.spend() for _ in range(10)))
        return await ledger.remaining()

    # Read-modify-write races used to drop charges entirely.
    assert asyncio.run(run()) == DAILY_CREDITS - 10 * COST_PER_TURN

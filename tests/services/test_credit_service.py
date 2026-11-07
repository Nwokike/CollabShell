"""Credit service tests: reserve/commit/rollback semantics."""

import asyncio
import sys

sys.path.insert(0, "src")

from services.credit_service import (
    COST_STEP,
    CreditService,
    NotEnoughCredits,
)


def _svc(balance: int | None = None) -> CreditService:
    svc = CreditService()
    if balance is not None:
        svc._balance = balance
    return svc


# ── balance and cap ────────────────────────────────────────────────────────


def test_default_balance_is_the_daily_cap():
    # Fresh services: the cap is applied on first read of the day. The cap
    # reads state.is_premium LIVE (DDGS parity) — it is never a parameter.
    from core.state import state

    assert asyncio.run(_svc().get_balance()) == 50
    state.is_premium = True
    try:
        assert asyncio.run(_svc().get_balance()) == 500
    finally:
        state.is_premium = False


def test_premium_upgrade_does_not_retroactively_refill():
    """Once a balance is established it persists for the day; the premium cap
    applies on the next daily reset, not mid-session (DDGS's flat-reset rule).
    """
    from core.state import state

    svc = _svc()
    assert asyncio.run(svc.get_balance()) == 50
    state.is_premium = True
    try:
        assert asyncio.run(svc.get_balance()) == 50
    finally:
        state.is_premium = False


def test_balance_never_goes_negative():
    svc = _svc(0)
    assert asyncio.run(svc.commit("tx-1", 5)) == 0


def test_add_credits_raises_balance():
    svc = _svc(10)
    assert asyncio.run(svc.add_credits(2)) == 12


def test_daily_reset_refills_on_a_new_day():
    svc = _svc(3)
    assert asyncio.run(svc.get_balance()) == 3
    # Simulate the UTC day changing.
    svc._day = "1999-01-01"
    assert asyncio.run(svc.get_balance()) == 50


# ── reserve / commit / rollback ────────────────────────────────────────────


def test_reserve_returns_a_transaction_id():
    svc = _svc(10)
    tx = asyncio.run(svc.reserve())
    assert tx, "reserve should hand back a transaction id"


def test_reserve_returns_none_when_balance_is_too_low():
    svc = _svc(0)
    assert asyncio.run(svc.reserve()) is None


def test_reserve_reduces_available_not_balance_until_commit():
    svc = _svc(10)
    assert asyncio.run(svc.reserve(3)) is not None
    assert asyncio.run(svc.available()) == 7  # held
    assert asyncio.run(svc.get_balance()) == 10  # not yet charged


def test_commit_charges_the_hold_and_releases_it():
    svc = _svc(10)
    tx = asyncio.run(svc.reserve(3))
    assert asyncio.run(svc.commit(tx)) == 7
    assert asyncio.run(svc.available()) == 7  # hold released


def test_commit_with_explicit_amount_beats_the_hold():
    svc = _svc(10)
    tx = asyncio.run(svc.reserve(3))
    # Only 2 steps were actually used.
    assert asyncio.run(svc.commit(tx, amount=2)) == 8


def test_rollback_releases_without_charging():
    svc = _svc(10)
    tx = asyncio.run(svc.reserve(3))
    assert asyncio.run(svc.rollback(tx)) == 10
    assert asyncio.run(svc.available()) == 10


def test_commit_is_idempotent():
    """A double settle must not double-charge."""
    svc = _svc(10)
    tx = asyncio.run(svc.reserve(3))
    first = asyncio.run(svc.commit(tx))
    second = asyncio.run(svc.commit(tx))
    assert first == 7
    assert second == 7, "committing twice charged twice"


def test_reserve_more_extends_a_hold():
    svc = _svc(10)
    tx = asyncio.run(svc.reserve(1))
    assert asyncio.run(svc.reserve_more(tx, 2)) is True
    assert asyncio.run(svc.commit(tx)) == 7


def test_reserve_more_does_not_block_on_unknown_transaction():
    svc = _svc(10)
    assert asyncio.run(svc.reserve_more("nope", 5)) is False


def test_concurrent_reserves_cannot_overspend():
    """Five parallel reserves against a balance of 4 must yield 4 holds."""
    svc = _svc(4)

    async def go():
        return await asyncio.gather(*[svc.reserve(1) for _ in range(5)])

    results = asyncio.run(go())
    assert sum(1 for r in results if r) == 4


def test_none_transaction_commit_is_a_noop():
    svc = _svc(12)
    assert asyncio.run(svc.commit(None)) == 12


def test_sweep_releases_stranded_holds():
    svc = _svc(10)
    tx = asyncio.run(svc.reserve(3))
    assert asyncio.run(svc.available()) == 7
    # Backdate the hold so it is genuinely abandoned, not in flight.
    svc._holds[tx] = (3, svc._holds[tx][1] - 10_000)
    assert asyncio.run(svc.sweep_expired_holds(max_age_sec=100)) == 1
    assert asyncio.run(svc.available()) == 10
    # A swept transaction settles as a no-charge commit.
    assert asyncio.run(svc.commit(tx)) == 10


def test_sweep_leaves_a_live_turn_alone():
    """The money leak this pins: sweeping a hold that is still in flight both
    frees that turn's charge and lets the next reserve ignore it, so the daily
    cap is overspent and the user gets the turn for nothing."""
    svc = _svc(10)
    tx = asyncio.run(svc.reserve(3))
    # No age override: a fresh hold is a live turn.
    assert asyncio.run(svc.sweep_expired_holds()) == 0
    assert asyncio.run(svc.available()) == 7
    # The turn settles and IS charged.
    assert asyncio.run(svc.commit(tx, 3)) == 7


def test_a_live_turn_is_not_overspent_by_the_next_turn():
    """A hold must reduce `available` for the whole life of the turn, so
    simultaneous turns cannot each see the full balance."""
    svc = _svc(10)
    first = asyncio.run(svc.reserve(3))
    assert asyncio.run(svc.available()) == 7
    # 8 exceeds the 7 that is actually spendable, so it must be refused.
    assert asyncio.run(svc.reserve(8)) is None, "the second turn overspent the cap"
    # 7 exactly fits — the boundary still works.
    assert asyncio.run(svc.reserve(7)) is not None
    # Settling the first releases only its own hold.
    asyncio.run(svc.commit(first, 3))
    assert asyncio.run(svc.available()) == 0


def test_sweep_does_not_void_a_real_charge():
    svc = _svc(10)
    tx = asyncio.run(svc.reserve(3))
    before = asyncio.run(svc.get_balance())
    # A sweep that touches nothing must not mark anything settled, or a later
    # commit silently charges zero.
    asyncio.run(svc.sweep_expired_holds(max_age_sec=1000))
    assert asyncio.run(svc.commit(tx, 3)) == before - 3, (
        "an untouched sweep voided a charge"
    )


def test_cost_step_is_one_credit():
    assert COST_STEP == 1


def test_not_enough_credits_carries_balance():
    err = NotEnoughCredits(3)
    assert err.balance == 3


# ── persistent storage parity (DDGS shape) ───────────────────────────────────


class _FakeStorage:
    def __init__(self):
        self.data: dict[str, str] = {}

    async def get(self, key: str, default=None):
        return self.data.get(key, default)

    async def set(self, key: str, value: str):
        self.data[key] = str(value)
        return True


def test_storage_preserves_balance_on_restart():
    """Restarting the app on the same day must NOT reset to 50 — no cheat!"""
    from core.constants import STORAGE_CREDITS

    storage = _FakeStorage()
    svc1 = CreditService(storage=storage)
    assert asyncio.run(svc1.initialize()) == 50
    # User spends 20 credits, 30 remaining
    tx = asyncio.run(svc1.reserve(20))
    assert asyncio.run(svc1.commit(tx)) == 30
    assert storage.data[STORAGE_CREDITS] == "30"

    # New app session starts with the same storage
    svc2 = CreditService(storage=storage)
    assert asyncio.run(svc2.initialize()) == 30
    assert asyncio.run(svc2.get_balance()) == 30


def test_storage_daily_reset_with_no_rollover():
    """Yesterday's surplus or deficit resets to the daily cap on UTC day boundary."""
    from core.constants import STORAGE_CREDITS, STORAGE_LAST_RESET

    storage = _FakeStorage()
    # Stored 70 credits (e.g. from ad rewards) on an old date
    storage.data[STORAGE_CREDITS] = "70"
    storage.data[STORAGE_LAST_RESET] = "1970-01-01"

    svc = CreditService(storage=storage)
    assert asyncio.run(svc.initialize()) == 50
    assert storage.data[STORAGE_CREDITS] == "50"



def test_daily_cap_reads_premium_live_from_state():
    """Regression (pre-ship verifier): ai_section called daily_cap with the
    dead is_premium parameter and the TypeError was swallowed by the UI's
    except — the credits line showed the fallback forever. The real service
    takes NO parameters; the cap always reads state.is_premium."""
    from core.state import state

    svc = _svc()
    state.is_premium = False
    assert svc.daily_cap() == 50
    state.is_premium = True
    try:
        assert svc.daily_cap() == 500
    finally:
        state.is_premium = False


# ── licence: a /status 404 must not revoke a token that verifies offline ─────


def test_status_refusal_keeps_a_valid_cached_token():
    """The 11/7 log: 'server refusal HTTP 404' on a background /status cleared
    a valid lifetime token and dropped the owner to free mid-session. A
    read-only status refusal must not clear a cache that still verifies."""
    import asyncio

    from services import license_service as ls

    class _Storage:
        def __init__(self):
            self.data = {}

        async def get(self, key, default=None):
            return self.data.get(key, default)

        async def set(self, key, value):
            self.data[key] = str(value)

    async def go():
        storage = _Storage()
        svc = ls.KiriLicenseService(storage, app_id="ng.kiri.collabshell")
        # Plant a VALID cached token by stubbing verify_token to accept it.
        real_verify = ls.verify_token
        ls.verify_token = lambda token, key, app: ls.LicenseClaims(
            ent="kiri", app=app, product="lifetime", scope="", mode="",
            status="active", paid_through=None, issued_at=0, expires_at=None,
        ) if token == "good" else (_ for _ in ()).throw(ls.TokenRejected("bad", "x"))
        try:
            await storage.set(ls.SETTING_TOKEN, "good")
            assert await svc.apply_cached_token() is True  # premium from cache

            async def fake_post(path, body):
                raise ls.LicenseUnavailable("license not found", status_code=404, is_refusal=True)

            svc._post = fake_post
            try:
                await svc._query("/status", "KIRI-L-X", issue_token=False)
                raise AssertionError("should have raised")
            except ls.LicenseUnavailable:
                pass
            # The cached token survived — no revoke happened.
            assert (await storage.get(ls.SETTING_TOKEN, "")) == "good"
            assert svc._unlocked is True, "the 404 must not revoke the valid cache"
        finally:
            ls.verify_token = real_verify

    asyncio.run(go())

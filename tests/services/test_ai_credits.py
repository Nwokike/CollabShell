"""Metered-turn tests: charge, the floor rule, the gate, soft metering.

The metering policy lives in `services/ai_credits.py`; `ai_service.run_turn`
is stubbed so these exercise the policy, not the transport.
"""

import asyncio
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from services import ai_credits, ai_service
from services.credit_service import CreditService


class _State:
    def __init__(self, is_premium=False):
        self.is_premium = is_premium
        self.credits_revision = 0


class _Credits:
    """A stand-in that records settle calls instead of touching a balance."""

    def __init__(self, balance=10):
        self.balance = balance
        self.available_balance = balance
        self.reserved = []
        self.committed = []
        self.rolled_back = []
        self.charged = []

    async def get_balance(self, is_premium=False):
        return self.balance

    async def reserve(self, amount=1, is_premium=False):
        if self.available_balance < amount:
            return None  # the best-effort hold failed
        self.available_balance -= amount
        tx = f"tx-{len(self.reserved)}"
        self.reserved.append(tx)
        return tx

    async def reserve_more(self, tx, amount):
        if not tx or self.available_balance < amount:
            return False
        self.available_balance -= amount
        return True

    async def commit(self, tx, amount=None, is_premium=False):
        self.committed.append((tx, amount))
        return self.balance

    async def rollback(self, tx, is_premium=False):
        self.rolled_back.append(tx)
        return self.balance

    async def charge(self, amount, is_premium=False):
        self.charged.append(amount)
        return self.balance


def _patch_turn(monkeypatch, result=None, exc=None, on_step=None):
    """Stub ai_service.run_turn."""
    seen = {"steps": []}

    async def _fake(**kwargs):
        seen["steps"].append(kwargs.get("on_model_step"))
        seen["kwargs"] = kwargs
        seen["messages"] = kwargs.get("messages")
        if exc is not None:
            raise exc
        return (
            result
            if result is not None
            else {
                "text": "done",
                "steps": [],
                "model_steps": 1,
                "cancelled": False,
                "model": "m",
            }
        )

    monkeypatch.setattr(ai_service, "run_turn", _fake)
    return seen


def _run(coro):
    return asyncio.run(coro)


# ── the floor rule ─────────────────────────────────────────────────────────


def test_charged_steps_floors_at_one_when_text_was_delivered():
    assert ai_credits.charged_steps(0, "hello") == 1
    assert ai_credits.charged_steps(2, "hello") == 2
    # Whitespace does not count as delivered.
    assert ai_credits.charged_steps(0, "   \n ") == 0
    assert ai_credits.charged_steps(0, "") == 0


# ── the gate ───────────────────────────────────────────────────────────────


def test_zero_balance_blocks_before_any_model_call(monkeypatch):
    seen = _patch_turn(monkeypatch)
    credits = _Credits(balance=0)

    result = _run(
        ai_credits.run_metered_turn(
            state=_State(),
            credits=credits,
            model="auto",
            tools=[],
            messages=[{"role": "user", "content": "hi"}],
        )
    )

    assert result["ok"] is False
    assert result["out_of_credits"] is True
    assert result["error"] == "Out of assistant credits."
    assert result["cost"] == 0
    assert seen["steps"] == [], "no model call may happen at zero balance"
    assert credits.reserved == [] and credits.committed == []


def test_missing_credit_service_is_reported_not_raised(monkeypatch):
    _patch_turn(monkeypatch)
    result = _run(
        ai_credits.run_metered_turn(
            state=_State(),
            credits=None,
            model="auto",
            tools=[],
            messages=[{"role": "user", "content": "hi"}],
        )
    )
    assert result["ok"] is False
    assert "unavailable" in result["error"].lower()


# ── normal settlement ──────────────────────────────────────────────────────


def test_one_round_turn_costs_one_credit(monkeypatch):
    _patch_turn(
        monkeypatch,
        result={
            "text": "answer",
            "steps": [],
            "model_steps": 1,
            "cancelled": False,
            "model": "m",
        },
    )
    credits = _Credits(balance=10)
    result = _run(
        ai_credits.run_metered_turn(
            state=_State(),
            credits=credits,
            model="auto",
            tools=[],
            messages=[{"role": "user", "content": "hi"}],
        )
    )
    assert result["ok"] is True
    assert result["cost"] == 1
    assert credits.committed == [(credits.reserved[0], 1)]


def test_tool_output_callback_reaches_the_ai_turn(monkeypatch):
    seen = _patch_turn(monkeypatch)
    output = []

    async def _turn():
        return await ai_credits.run_metered_turn(
            state=_State(),
            credits=_Credits(balance=10),
            model="auto",
            tools=[],
            messages=[],
            on_tool_output=lambda name, text: output.append((name, text)),
        )

    _run(_turn())
    seen["kwargs"]["on_tool_output"]("read_terminal", "visible output")
    assert output == [("read_terminal", "visible output")]


def test_unexpected_turn_error_is_visible_and_rolls_back_empty_hold(monkeypatch):
    _patch_turn(monkeypatch, exc=TypeError("unexpected callback keyword"))
    credits = _Credits(balance=10)

    result = _run(
        ai_credits.run_metered_turn(
            state=_State(),
            credits=credits,
            model="auto",
            tools=[],
            messages=[],
        )
    )

    assert result["ok"] is False
    assert result["error"] == "TypeError: unexpected callback keyword"
    assert result["cost"] == 0
    assert credits.rolled_back == [credits.reserved[0]]


def test_multi_round_turn_costs_one_per_round(monkeypatch):
    _patch_turn(
        monkeypatch,
        result={
            "text": "answer",
            "steps": [{"id": "1"}, {"id": "2"}],
            "model_steps": 3,
            "cancelled": False,
            "model": "m",
        },
    )
    credits = _Credits(balance=10)
    result = _run(
        ai_credits.run_metered_turn(
            state=_State(),
            credits=credits,
            model="auto",
            tools=[],
            messages=[{"role": "user", "content": "hi"}],
        )
    )
    assert result["cost"] == 3
    assert credits.committed == [(credits.reserved[0], 3)]


def test_every_exit_settles_exactly_once(monkeypatch):
    """A double settle cannot double-charge: commit is idempotent per tx."""
    _patch_turn(
        monkeypatch,
        result={
            "text": "a",
            "steps": [],
            "model_steps": 1,
            "cancelled": False,
            "model": "m",
        },
    )
    credits = _Credits(balance=10)
    _run(
        ai_credits.run_metered_turn(
            state=_State(),
            credits=credits,
            model="auto",
            tools=[],
            messages=[{"role": "user", "content": "hi"}],
        )
    )
    assert len(credits.committed) == 1
    # The service itself is idempotent for the same tx.
    real = CreditService()
    tx = asyncio.run(real.reserve(1))
    first = asyncio.run(real.commit(tx, 1))
    second = asyncio.run(real.commit(tx, 1))
    assert first == second, "committing the same tx twice charged twice"


def test_exhausted_router_rolls_back(monkeypatch):
    _patch_turn(monkeypatch, exc=ai_service.AIUnavailable("all models down"))
    credits = _Credits(balance=10)
    result = _run(
        ai_credits.run_metered_turn(
            state=_State(),
            credits=credits,
            model="auto",
            tools=[],
            messages=[{"role": "user", "content": "hi"}],
        )
    )
    assert result["ok"] is False
    assert "all models down" in result["error"]
    assert result["cost"] == 0
    assert credits.rolled_back == [credits.reserved[0]]
    assert credits.committed == []


def test_nothing_delivered_refunds_the_hold(monkeypatch):
    """An immediate Stop must not be a free model call — nor a charged one."""
    _patch_turn(
        monkeypatch,
        result={
            "text": "",
            "steps": [],
            "model_steps": 0,
            "cancelled": True,
            "model": "m",
        },
    )
    credits = _Credits(balance=10)
    result = _run(
        ai_credits.run_metered_turn(
            state=_State(),
            credits=credits,
            model="auto",
            tools=[],
            messages=[{"role": "user", "content": "hi"}],
        )
    )
    assert result["ok"] is True
    assert result["cost"] == 0
    assert credits.rolled_back == [credits.reserved[0]]
    assert credits.committed == []


# ── soft metering ──────────────────────────────────────────────────────────


def test_last_credit_still_runs_and_clamps_at_zero(monkeypatch):
    """Balance 1: the hold succeeds, the turn runs, and the balance clamps at
    zero rather than the credit being refused."""
    _patch_turn(
        monkeypatch,
        result={
            "text": "answer",
            "steps": [],
            "model_steps": 1,
            "cancelled": False,
            "model": "m",
        },
    )
    credits = CreditService()
    credits._balance = 1
    result = _run(
        ai_credits.run_metered_turn(
            state=_State(),
            credits=credits,
            model="auto",
            tools=[],
            messages=[{"role": "user", "content": "hi"}],
        )
    )
    assert result["ok"] is True, "credits must never block the work"
    assert result["cost"] == 1
    assert result["balance"] == 0


def test_an_over_hold_settles_by_clamping_not_refusing(monkeypatch):
    """A turn longer than the balance must still finish and land on zero."""
    _patch_turn(
        monkeypatch,
        result={
            "text": "answer",
            "steps": [],
            "model_steps": 6,
            "cancelled": False,
            "model": "m",
        },
    )
    credits = CreditService()
    credits._balance = 2
    result = _run(
        ai_credits.run_metered_turn(
            state=_State(),
            credits=credits,
            model="auto",
            tools=[],
            messages=[{"role": "user", "content": "hi"}],
        )
    )
    assert result["ok"] is True
    assert result["cost"] == 6
    assert result["balance"] == 0, "the balance clamps, it never goes negative"


def test_low_balance_is_flagged_but_not_blocking(monkeypatch):
    _patch_turn(monkeypatch)
    credits = _Credits(balance=2)
    result = _run(
        ai_credits.run_metered_turn(
            state=_State(),
            credits=credits,
            model="auto",
            tools=[],
            messages=[{"role": "user", "content": "hi"}],
        )
    )
    assert result["ok"] is True
    assert result["low_balance"] is True
    assert result["out_of_credits"] is False


def test_revision_bumps_so_the_pill_refreshes():
    state = _State()
    before = state.credits_revision
    ai_credits._bump_revision(state)
    assert state.credits_revision == before + 1


def test_revision_bump_survives_a_read_only_state():
    class _RO:
        __slots__ = ()

    ai_credits._bump_revision(_RO())  # must not raise


# ── the real service ───────────────────────────────────────────────────────


def test_charge_subtracts_clamps_and_ignores_holds():
    svc = CreditService()
    assert _run(svc.charge(3)) == 47
    assert _run(svc.charge(999)) == 0
    assert _run(svc.charge(0)) == 0


def test_charge_subtracts_from_the_balance_and_leaves_the_hold():
    """charge is the hold-less half of settlement: it moves the balance and
    must not disturb a hold that some other turn still owns."""
    svc = CreditService()
    _run(svc.reserve(10))
    assert _run(svc.available()) == 40  # balance 50 minus the 10 held
    assert _run(svc.charge(5)) == 45  # balance only
    assert _run(svc.available()) == 35  # 45 minus the 10 still held


def test_metered_turn_against_the_real_service(monkeypatch):
    """End to end with the real CreditService, not a stand-in."""
    _patch_turn(
        monkeypatch,
        result={
            "text": "answer",
            "steps": [],
            "model_steps": 2,
            "cancelled": False,
            "model": "m",
        },
    )
    credits = CreditService()
    before = _run(credits.get_balance())
    result = _run(
        ai_credits.run_metered_turn(
            state=_State(),
            credits=credits,
            model="auto",
            tools=[],
            messages=[{"role": "user", "content": "hi"}],
        )
    )
    assert result["cost"] == 2
    assert _run(credits.get_balance()) == before - 2
    assert result["balance"] == before - 2


# ── generated copy ─────────────────────────────────────────────────────────


def test_credits_are_for_copy_is_generated_from_the_constant():
    from core.constants import COST_STEP

    copy = ai_credits.credits_are_for_copy()
    assert str(COST_STEP) in copy
    assert "Search" in copy and "free" in copy


def test_out_of_credits_notice_matches_the_cap():
    assert "Out of assistant credits." in ai_credits.out_of_credits_notice(0, False)
    assert "of 50" in ai_credits.out_of_credits_notice(0, False)
    assert "of 500" in ai_credits.out_of_credits_notice(0, True)
    assert "00:00 UTC" in ai_credits.out_of_credits_notice(0, False)


def test_credit_word_is_plural_safe():
    assert ai_credits.credit_word(1) == "1 credit"
    assert ai_credits.credit_word(2) == "2 credits"
    assert ai_credits.credit_word(0) == "0 credits"


def test_credit_color_bands():
    from components.credit_pill import credit_color

    assert credit_color(50) is not None
    assert credit_color(10) is not None
    assert credit_color(1) is not None
    # Bands must be distinct, not three aliases of one colour.
    assert len({credit_color(50), credit_color(10), credit_color(1)}) == 3

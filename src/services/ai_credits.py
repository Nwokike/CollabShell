"""Metered assistant turns — the one place credits are spent.

Policy lives here so `ai_service.run_turn` stays a pure transport loop. The
semantics are ported from DDGS's chat_agent (verified at
DDGS/src/services/chat_agent.py:394-416 and :537-589):

* **One credit per model step** — one streamed model reply. A tool round is
  NOT a step: kani yields a result message for those, and counting it would
  bill two credits for a single model call.
* **Soft metering.** A low balance never kills a running turn; the balance
  clamps at zero and the turn finishes. Only a zero balance blocks *starting*.
  The hold is best-effort and, once taken, may grow past the balance — that is
  deliberate: an over-hold settles by clamping, never by refusing to run.
* **The floor rule.** If the user saw any text, at least one step is billed
  whatever ended the turn — stop, crash, dropped connection. Nothing
  delivered refunds the hold entirely. This is what stops "Stop immediately"
  from being a free model call.
* **Reserve is best-effort.** A hold that cannot be taken means settlement
  charges directly rather than blocking the work.
* **Retries are not billable.** A candidate that fails before streaming adds
  no step, so run_turn's candidate walk is free.
"""

from __future__ import annotations

import logging

from core.constants import (
    COST_STEP,
    DAILY_FREE_CREDITS,
    DAILY_PREMIUM_CREDITS,
)
from services import ai_service

logger = logging.getLogger("ai_credits")

# Below this many credits the caller is told, so the UI can nudge without
# stopping the turn (DDGS's "Low credit balance…" behaviour).
LOW_BALANCE_NUDGE = COST_STEP * 3

OUT_OF_CREDITS_COPY = "Out of assistant credits."
LOW_BALANCE_COPY = "Low credit balance. This message finishes regardless."


def credit_word(n: int) -> str:
    """Plural-safe credit count for user-facing copy."""
    return "1 credit" if n == 1 else f"{n} credits"


def credits_are_for_copy() -> str:
    """The "what credits are for" line, generated from the constants.

    Never hand-typed, so the Settings copy cannot drift from what
    run_metered_turn actually charges.
    """
    return (
        f"Each Assistant reply costs {credit_word(COST_STEP)}. A reply that "
        "calls a tool is still one step — the tool runs as part of the same "
        "reply. Search, uploading files, and everything else in the app is "
        "free."
    )


def out_of_credits_notice(balance: int, is_premium: bool) -> str:
    """The gate message, honest about the number and where it resets."""
    cap = DAILY_PREMIUM_CREDITS if is_premium else DAILY_FREE_CREDITS
    return (
        f"{OUT_OF_CREDITS_COPY} {balance} of {cap} left today · "
        "resets at 00:00 UTC."
    )


def charged_steps(model_steps: int, text: str) -> int:
    """Steps to bill under the floor rule.

    Delivered work is worth one step, whatever ended the turn. With nothing
    delivered the hold is refunded.
    """
    delivered = bool((text or "").strip())
    return max(model_steps, 1) if delivered else model_steps


async def run_metered_turn(
    *,
    state,
    credits,
    model: str,
    tools: list,
    messages: list,
    system: str = "",
    on_token=None,
    on_thought=None,
    on_tool_start=None,
    on_tool_done=None,
    should_stop=None,
    max_rounds: int = ai_service.MAX_TOOL_ROUNDS,
) -> dict:
    """Run one assistant turn, metered.

    Returns a dict that always includes ``ok`` (False when blocked before any
    model call), ``out_of_credits``, ``low_balance``, ``balance`` (after
    settling), and — on success — run_turn's ``text`` / ``steps`` /
    ``model_steps`` / ``model``. Never raises for ordinary failures: an
    exhausted router comes back as ``ok=False`` with an ``error`` string so
    the UI can retry.
    """
    is_premium = bool(getattr(state, "is_premium", False))

    # The question is recorded before any gate, so an out-of-credits turn
    # still shows what was asked and Retry can re-send it.
    if credits is None:
        return {
            "ok": False,
            "out_of_credits": False,
            "low_balance": False,
            "balance": 0,
            "cost": 0,
            "error": "Assistant credits are unavailable in this build.",
        }

    balance = await credits.get_balance(is_premium)
    if balance <= 0:
        return {
            "ok": False,
            "out_of_credits": True,
            "low_balance": False,
            "balance": balance,
            "cost": 0,
            "error": OUT_OF_CREDITS_COPY,
        }

    # Best-effort hold; at balance 1 it fails and we run hold-less.
    tx = await credits.reserve(COST_STEP, is_premium)
    low_balance = balance < LOW_BALANCE_NUDGE

    async def _reserve_more():
        if tx:
            await credits.reserve_more(tx, COST_STEP)

    try:
        result = await ai_service.run_turn(
            model=model,
            tools=tools,
            messages=messages,
            system=system,
            on_token=on_token,
            on_thought=on_thought,
            on_tool_start=on_tool_start,
            on_tool_done=on_tool_done,
            on_model_step=_reserve_more,
            should_stop=should_stop,
            max_rounds=max_rounds,
        )
    except ai_service.AIUnavailable as ex:
        # Nothing was delivered, so the hold goes back untouched. (A connection
        # drop AFTER the model answered is not this case: run_turn returns the
        # partial it got, and the floor rule below bills it.)
        if tx:
            await credits.rollback(tx, is_premium)
        _bump_revision(state)
        return {
            "ok": False,
            "out_of_credits": False,
            "low_balance": low_balance,
            "balance": await credits.get_balance(is_premium),
            "cost": 0,
            "error": str(ex),
        }

    steps = charged_steps(result.get("model_steps", 0), result.get("text", ""))
    if steps <= 0:
        await credits.rollback(tx, is_premium)
    elif tx:
        await credits.commit(tx, steps, is_premium)
    else:
        await credits.charge(steps, is_premium)

    balance = await credits.get_balance(is_premium)
    _bump_revision(state)
    return {
        "ok": True,
        "out_of_credits": balance <= 0,
        "low_balance": low_balance,
        "balance": balance,
        "cost": steps,
        "text": result.get("text", ""),
        "steps": result.get("steps", []),
        "model_steps": result.get("model_steps", 0),
        "cancelled": result.get("cancelled", False),
        "model": result.get("model", ""),
    }


def _bump_revision(state) -> None:
    """Nudge reactive surfaces (the credit pill) to re-read the balance."""
    try:
        state.credits_revision = getattr(state, "credits_revision", 0) + 1
    except Exception:
        logger.debug("Could not bump credits_revision", exc_info=True)


def credits_revision_of(state) -> int:
    return getattr(state, "credits_revision", 0)


async def refresh_balance(state, credits) -> int:
    """Read the balance for display, applying the daily reset."""
    if credits is None:
        return 0
    return await credits.get_balance(bool(getattr(state, "is_premium", False)))

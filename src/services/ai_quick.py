"""One-shot metered AI queries — the shared engine for in-context actions.

`cell_ai`, terminal explain and the command palette all need the same thing:
send one prompt, get one answer, spend one step, and surface the same gates.
Rather than copy the metering boilerplate four times, it lives here once.

Tool-free by design. These are prompts built from context the app already has
(the notebook, the scrollback), so a tool loop would only add round trips and
credits to something that needs one answer.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("ai_quick")


class CellAIDisabled(RuntimeError):
    """AI is off (or unavailable), so the action should not have been offered."""


class OutOfCredits(RuntimeError):
    """The balance is at zero and the action was blocked before any call."""


async def ask(
    *,
    action: str,
    state,
    credits,
    services,
    prompt: str,
    system: str = "",
) -> str:
    """Run one metered, tool-free turn and return the raw reply.

    Raises `OutOfCredits` when the gate blocks, `CellAIDisabled` when AI is off
    or the credit service is missing, and lets `AIUnavailable` propagate for the
    caller to surface as a notice.

    Callers never insert anything from here — that is deliberate, so a failure
    cannot leave half-written state behind in a notebook or a terminal.
    """
    from services import ai_credits, ai_service

    if credits is None:
        raise CellAIDisabled("Assistant credits are unavailable in this build")

    result = await ai_credits.run_metered_turn(
        state=state,
        credits=credits,
        model=getattr(state, "ai_model", "auto"),
        tools=[],
        messages=[{"role": "user", "content": prompt}],
        system=system,
    )

    if result.get("out_of_credits"):
        raise OutOfCredits(result.get("error") or "Out of assistant credits.")
    if not result.get("ok"):
        raise ai_service.AIUnavailable(
            result.get("error") or "Assistant unavailable"
        )
    return result.get("text", "")


def system_for(state) -> str:
    """The bundled SKILL.md. Always injected: there is no off switch."""
    from ai import skill_text

    return skill_text()

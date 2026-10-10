"""In-cell AI actions — Explain, Fix error, Suggest next, Suggest hardware.

These run *in context*, not in a chat, so they are deliberately tool-free: the
whole notebook is passed in the prompt and the model answers in one step. That
keeps an in-cell action to one credit and one round trip, which is what a
button next to a Run button should cost — a tool loop would spend a step per
tool and turn a two-second "explain this" into a wait.

The answer goes *into the notebook* as a new cell rather than a chat bubble:
the user asked for AI that works where the work is, and a cell they can edit,
re-run, or delete is a better answer than text in another screen. The
caller decides placement (`after_id`), so the answer lands directly under the
cell it is about.

Metering goes through the same `ai_credits.run_metered_turn` as the chat, so
the zero-balance gate, the per-step charge and the floor rule behave
identically.

`HARDWARE_OPTIONS` is read, not invented: the app's own accelerator vocabulary
(session_ops), so a suggestion names a shape the picker can actually select.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("cell_ai")

# What the app can actually pick, and what each one costs the user. Passed to
# the model verbatim so a recommendation maps onto a real choice rather than a
# plausible-sounding shape the picker does not offer.
HARDWARE_OPTIONS = (
    "CPU (no accelerator) — always available",
    "T4 (GPU) — free tier",
    "L4 (GPU) — paid",
    "G4 (GPU) — paid",
    "A100 (GPU) — paid",
    "H100 (GPU) — paid",
    "v5e1 / v6e1 (TPU) — free tier / paid",
    "High-RAM shape — needs Colab Pro or Pro+",
)

# The gates live in ai_quick (the shared engine), and are re-exported here so
# `except cell_ai.OutOfCredits` at a call site catches the class that is
# actually raised. Defining copies here would silently break every gate.
from services.ai_quick import CellAIDisabled, OutOfCredits  # noqa: F401

# Kept small on purpose: this rides in a prompt next to every cell.
_MAX_NOTEBOOK_CHARS = 6000
_MAX_OUTPUT_CHARS = 1500
_MAX_SOURCE_CHARS = 4000


def _cell_digest(cells: list, max_chars: int = _MAX_NOTEBOOK_CHARS) -> str:
    """A compact, jail-safe rendering of the notebook for the model.

    Numbered so the model can say "cell 3" and mean something, and truncated
    from the end so the earliest cells — usually the imports — survive.
    """
    lines: list[str] = []
    used = 0
    for index, cell in enumerate(cells or []):
        source = str(getattr(cell, "source", "") or "")
        if not source.strip():
            continue
        kind = getattr(cell, "type", "code")
        block = f"--- cell {index} ({kind}) ---\n{source}"
        if used + len(block) > max_chars:
            lines.append(f"--- ({index} remaining cells truncated) ---")
            break
        lines.append(block)
        used += len(block)
    return "\n".join(lines)


def _output_digest(cell, max_chars: int = _MAX_OUTPUT_CHARS) -> str:
    """The cell's output, text only — for Fix error this is the whole point."""
    outputs = getattr(cell, "outputs", None) or []
    parts: list[str] = []
    for out in outputs:
        text = getattr(out, "text", None) or getattr(out, "output", None)
        if text is None and isinstance(out, dict):
            text = out.get("text") or out.get("output")
        if text:
            parts.append(str(text))
    joined = "\n".join(parts).strip()
    return joined[:max_chars]


def _model_messages(
    action: str, *, source: str, digest: str, output: str, cell_type: str = "code"
) -> list[dict]:
    if action == "explain":
        ask = (
            "Explain this cell to the user. Say what it does and why, in plain "
            "language, then anything non-obvious or fragile about it. Be brief "
            "and specific — no preamble, no restating the code back."
        )
    elif action == "fix":
        ask = (
            "This cell failed. Diagnose the error from the output and give the "
            "corrected code. Reply with ONLY a Python code block containing the "
            "fixed cell — no explanation before or after it."
        )
    elif action == "hardware":
        ask = (
            "Recommend the runtime shape for THIS notebook. Reply in markdown "
            "with: the single recommendation on its own line first, exactly as "
            "it appears in the options list; then two or three sentences of "
            "why; then, if relevant, what would change your mind. Only "
            "recommend something the options list can select."
        )
    else:  # suggest
        ask = (
            "Suggest the single most useful next cell for this notebook. Reply "
            "with ONLY a Python code block containing it — no explanation "
            "before or after it. It should follow on from what is already here."
        )
    if action == "hardware":
        body = [
            "Notebook:",
            digest or "(empty)",
            "",
            "Available runtime shapes:",
            *[f"- {option}" for option in HARDWARE_OPTIONS],
            "",
            ask,
        ]
        return [{"role": "user", "content": "\n".join(body)}]
    body = [
        "Notebook:",
        digest or "(empty)",
        "",
        f"Cell under the cursor ({cell_type}):",
        source[:_MAX_SOURCE_CHARS],
    ]
    if action == "fix":
        body += ["", "Its output (the error):", output or "(no output captured)"]
    body += ["", ask]
    return [{"role": "user", "content": "\n".join(body)}]


def extract_code(text: str) -> str:
    """Pull the runnable code out of a model reply.

    Answers for fix/suggest are "only a code block" by instruction, but models
    hedge. Prefer the first fenced block; fall back to the whole reply with the
    fences stripped, and finally to the raw text. Returns "" for nothing
    usable — the caller must not insert an empty cell.
    """
    if not text:
        return ""
    stripped = text.strip()
    fence = "```"
    start = stripped.find(fence)
    if start != -1:
        tail = stripped[start + len(fence):]
        # Skip a language tag ("```python").
        newline = tail.find("\n")
        if newline != -1:
            tail = tail[newline + 1:]
        end = tail.find(fence)
        if end != -1:
            return tail[:end].strip()
        return tail.strip()
    return stripped


def looks_like_error(output: str) -> bool:
    """Whether an output reads as a failure, for the Fix-error affordance."""
    if not output:
        return False
    lowered = output.lower()
    return any(
        marker in lowered
        for marker in ("traceback", "error:", "exception", "errno", "syntaxerror")
    )


async def run_cell_action(
    *,
    action: str,
    state,
    credits,
    services,
    source: str,
    notebook_cells: list,
    output: str = "",
    cell=None,
) -> str:
    """Run one in-cell action and return the model's raw reply.

    Raises `OutOfCredits` when the gate blocks, `CellAIDisabled` when AI is
    off, and lets `AIUnavailable` propagate for the caller to surface as a
    notice. Never inserts anything itself — that is the caller's job, so a
    failure cannot leave a half-written cell behind.
    """
    from services import ai_quick

    body = _model_messages(
        action,
        source=source,
        digest=_cell_digest(notebook_cells),
        output=output,
        cell_type=getattr(cell, "type", "code") if cell is not None else "code",
    )
    return await ai_quick.ask(
        action=action,
        state=state,
        credits=credits,
        services=services,
        prompt=body[0]["content"],
        system=ai_quick.system_for(state),
    )

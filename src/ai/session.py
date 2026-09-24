"""AI chat state — one conversation, shared by the panel, the FAB, and settings.

`@ft.observable` so any control that reads these fields inside a component
re-renders when a token lands — no manual update() calls. The chat lives
here, not in the panel, so minimizing the sheet keeps the reply streaming
in the notebook or terminal underneath.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

import flet as ft

from ai.credits import COST_PER_TURN, CreditsLedger
from ai.router import DEFAULT_MODEL, AiModel, KiriRouter, RouterBusy, RouterUnavailable
from ai.system_prompt import build_system_prompt
from ai.tools import CONFIRM, TIERS, ToolBox, label_for, schemas_for
from core import constants

logger = logging.getLogger("ai.session")

MAX_HISTORY = 40
# Guards mirror DDGS's agent loop: a runaway task cannot drain the day.
MAX_STEPS = 6
MAX_TOOL_CALLS = 10
APPROVAL_TIMEOUT_SECONDS = 300
# Flet re-renders on every observable write; batching tokens keeps a fast
# model from flooding the Dart bridge with one update per token.
THROTTLE_SECONDS = 0.08


@ft.observable
class AiSession:
    def __init__(self):
        self.router = KiriRouter()
        self.ledger: CreditsLedger | None = None

        # ── User-visible state ────────────────────────────────────────────
        self.enabled: bool = True
        self.selected_model: str = DEFAULT_MODEL
        self.models: list[AiModel] = []
        self.credits_left: int = 0
        self.messages: list[dict] = []
        self.streaming: bool = False
        self.answer: str = ""
        self.reasoning: str = ""
        self.reasoning_open: bool = True
        self.answered_by: str = ""
        self.status: str = ""  # e.g. busy hints
        self.error: str = ""
        self.draft: str = ""  # lives here so minimizing keeps typed text
        self.steps_used: int = 0  # model calls this conversation, for the receipt
        self.timeline: list[dict] = []  # agent step rows
        self.approval: dict | None = None  # pending confirm-tier tool call
        self.tools_enabled: bool = True
        self.cell_focus: str = ""  # "cell 3" — the cell the user pointed at

        # ── Internals ────────────────────────────────────────────────────
        self._storage = None
        self._task: asyncio.Task | None = None
        self._send_lock = asyncio.Lock()
        self._toolbox: ToolBox | None = None
        self._notebook = None
        self._terminal = None
        self._approval_event: asyncio.Event | None = None
        self._approval_granted = False
        self._pending = ""
        self._pending_reasoning = ""
        self._last_push = 0.0
        self._produced = False
        self._refund_pending = False
        self._reasoning_started = 0.0

    # ── Wiring ─────────────────────────────────────────────────────────

    def attach_storage(self, storage) -> None:
        self._storage = storage
        self.ledger = CreditsLedger(storage)
        self._load_settings()

    def attach_colab(self, colab_service) -> None:
        """Give the Assistant a toolbox once the Colab service exists."""
        self._toolbox = ToolBox(colab_service)

    def attach_notebook(self, bridge) -> None:
        """Point the toolbox at the notebook currently on screen."""
        self._notebook = bridge
        if self._toolbox is not None:
            self._toolbox.set_notebook(bridge)

    def detach_notebook(self) -> None:
        """The view is gone; its cells are no longer reachable."""
        self._notebook = None
        if self._toolbox is not None:
            self._toolbox.set_notebook(None)

    def attach_terminal(self, bridge) -> None:
        """Point the toolbox at the terminal currently on screen."""
        self._terminal = bridge
        if self._toolbox is not None:
            self._toolbox.set_terminal(bridge)

    def detach_terminal(self) -> None:
        self._terminal = None
        if self._toolbox is not None:
            self._toolbox.set_terminal(None)

    def _load_settings(self) -> None:
        if self._storage is None:
            return

        async def _load():
            enabled = await self._storage.get(constants.STORAGE_AI_ENABLED)
            if enabled is not None:
                self.enabled = enabled == "true"
            tools_on = await self._storage.get(constants.STORAGE_AI_TOOLS_ENABLED)
            if tools_on is not None:
                self.tools_enabled = tools_on == "true"
            model = await self._storage.get(constants.STORAGE_AI_MODEL)
            if model:
                self.selected_model = model
            history = await self._storage.get(constants.STORAGE_AI_MESSAGES)
            if history:
                try:
                    loaded = json.loads(history)
                    if isinstance(loaded, list):
                        self.messages = [
                            m
                            for m in loaded
                            if isinstance(m, dict)
                            and m.get("role") in ("user", "assistant")
                        ][-MAX_HISTORY:]
                except (TypeError, ValueError):
                    logger.debug("stored AI history unreadable", exc_info=True)
            self.credits_left = await self.ledger.remaining()

        ft.context.page.run_task(_load)

    async def _persist(self) -> None:
        if self._storage is None:
            return
        try:
            await self._storage.set(
                constants.STORAGE_AI_MESSAGES, json.dumps(self.messages)
            )
        except Exception:
            logger.debug("AI history save failed", exc_info=True)

    def _trim_history(self) -> None:
        # The persisted blob is rewritten on every completed turn, so the list
        # must be bounded or storage grows without limit.
        if len(self.messages) > MAX_HISTORY:
            del self.messages[:-MAX_HISTORY]

    # ── Models ─────────────────────────────────────────────────────────

    async def refresh_models(self) -> None:
        try:
            self.models = await self.router.list_models()
        except RouterUnavailable:
            self.models = []
            return
        # A pinned model the router currently does not serve stays pinned in
        # storage; the picker just shows it unavailable, so coming back
        # online restores the choice.
        if self.selected_model not in {m.id for m in self.models}:
            self.status = (
                f"{self.selected_model} is not being served right now — "
                "auto will pick instead."
            )

    async def select_model(self, model_id: str) -> None:
        self.selected_model = model_id
        self.status = ""
        if self._storage is not None:
            await self._storage.set(constants.STORAGE_AI_MODEL, model_id)

    # ── Settings ───────────────────────────────────────────────────────

    async def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if self._storage is not None:
            await self._storage.set(
                constants.STORAGE_AI_ENABLED, "true" if enabled else "false"
            )

    async def set_tools_enabled(self, enabled: bool) -> None:
        self.tools_enabled = enabled
        if self._storage is not None:
            await self._storage.set(
                constants.STORAGE_AI_TOOLS_ENABLED, "true" if enabled else "false"
            )

    def resolve_approval(self, allow: bool) -> None:
        """The user tapped Allow or Deny on a confirm-tier tool call."""
        # Event.set() carries no payload — the answer rides on its own flag,
        # otherwise Deny would read as truthy and the action would run anyway.
        self._approval_granted = allow
        if self._approval_event is not None:
            self._approval_event.set()
        self.approval = None

    async def clear_history(self) -> None:
        self.messages.clear()
        self.answer = ""
        self.reasoning = ""
        self.error = ""
        self.status = ""
        self.steps_used = 0
        await self._persist()

    async def delete_message(self, index: int) -> None:
        """Long-press removes one message; the rest keep their order."""
        if 0 <= index < len(self.messages):
            del self.messages[index]
            await self._persist()

    # ── Chat loop ──────────────────────────────────────────────────────

    def _tool_schemas(self) -> list[dict] | None:
        if not (self.tools_enabled and self._toolbox is not None):
            return None
        return schemas_for(
            has_notebook=self._toolbox.has_notebook,
            has_terminal=self._toolbox.has_terminal,
        )

    def _context_messages(self) -> list[dict]:
        has_tools = bool(self._tool_schemas())
        prompt = build_system_prompt(
            tools_available=has_tools,
            notebook_available=bool(self._toolbox and self._toolbox.has_notebook),
            terminal_available=bool(self._toolbox and self._toolbox.has_terminal),
        )
        return [
            {"role": "system", "content": prompt},
            *self.messages[-MAX_HISTORY:],
        ]

    def _on_delta(self, text: str) -> None:
        self._pending += text
        self._flush()

    def _on_reasoning(self, text: str) -> None:
        if not self.reasoning:
            self._reasoning_started = time.monotonic()
            self.reasoning_open = True
        self._pending_reasoning += text
        self._flush()

    def _flush(self, force: bool = False) -> None:
        if not self._pending and not self._pending_reasoning:
            return
        now = time.monotonic()
        if not force and now - self._last_push < THROTTLE_SECONDS:
            return
        if self._pending:
            self.answer += self._pending
            self._pending = ""
            self._produced = True
        if self._pending_reasoning:
            self.reasoning += self._pending_reasoning
            self._pending_reasoning = ""
        self._last_push = now

    @property
    def reasoning_seconds(self) -> int:
        if not self._reasoning_started:
            return 0
        return int(max(time.monotonic() - self._reasoning_started, 0))

    async def _refund_if_unpaid(self) -> None:
        """A call that never produced tokens costs the user nothing."""
        if self._produced or self.ledger is None:
            return
        await self.ledger.refund(COST_PER_TURN)
        self.credits_left = await self.ledger.remaining()

    async def _execute_tool_call(self, call: dict) -> str:
        """Run one tool, asking the user first when it changes state."""
        name = call.get("name") or ""
        try:
            args = json.loads(call.get("arguments") or "{}")
        except (TypeError, ValueError):
            args = {}
        if not isinstance(args, dict):
            args = {}
        row = {"label": label_for(name, args), "status": "running", "preview": ""}
        self.timeline.append(row)
        # Flet copies an appended dict into an ObservableDict, so the local
        # handle is stale: later status writes must go through the stored row
        # or the panel keeps showing "running" forever.
        row = self.timeline[-1]

        if TIERS.get(name, CONFIRM) == CONFIRM:
            # Show the user the thing itself — the code that will run or
            # the source that will replace their cell — not a JSON blob.
            detail = str(
                args.get("source")
                or args.get("code")
                or args.get("command")
                or args.get("path")
                or args
            )[:220]
            self.approval = {"label": row["label"], "detail": detail}
            self._approval_granted = False
            self._approval_event = asyncio.Event()
            try:
                await asyncio.wait_for(
                    self._approval_event.wait(), APPROVAL_TIMEOUT_SECONDS
                )
            except TimeoutError:
                self._approval_granted = False
            finally:
                self.approval = None
                self._approval_event = None
            if not self._approval_granted:
                row["status"] = "denied"
                return (
                    "The user declined this action. Do not retry it — "
                    "ask what they would like instead."
                )

        if self._toolbox is None:
            row["status"] = "error"
            return "No Colab service is connected right now."
        result = await self._toolbox.run(name, args)
        row["preview"] = result.text[:140]
        lowered = result.text.lower()
        row["status"] = (
            "error"
            if "failed" in lowered[:24] or "timed out" in lowered[:24]
            else "done"
        )
        return result.text

    async def send(self, text: str) -> None:
        text = (text or "").strip()
        if not text or not self.enabled:
            if not self.enabled:
                self.error = "The Assistant is turned off in Settings."
            return
        # One send at a time: without this, two fast taps both pass the
        # streaming check, both charge, and both streams corrupt the shared
        # answer buffer while the first task becomes unstoppable.
        async with self._send_lock:
            if self.streaming:
                return
            if self._refund_pending:
                self._refund_pending = False
                await self._refund_if_unpaid()

            if self.ledger is not None and not await self.ledger.spend(COST_PER_TURN):
                self.credits_left = 0
                self.error = "No Assistant credits left today. They refill in 24 hours."
                return

            self.messages.append({"role": "user", "content": text})
            self._trim_history()
            self.steps_used += 1
            self.timeline.clear()
            self.streaming = True
            self.answer = ""
            self.reasoning = ""
            self.reasoning_open = True
            self.error = ""
            self.status = ""
            self.answered_by = ""
            self._pending = ""
            self._pending_reasoning = ""
            self._produced = False
            self._reasoning_started = 0.0
            self._last_push = 0.0
            self.credits_left = await self.ledger.remaining() if self.ledger else 0
            self._task = asyncio.current_task()
            tool_calls_run = 0
            try:
                for step in range(MAX_STEPS):
                    if step:
                        # Every model call after a tool result is its own
                        # turn and its own charge.
                        if self.ledger is not None and not await self.ledger.spend(
                            COST_PER_TURN
                        ):
                            self.status = (
                                "Out of credits — the task stops here with "
                                "what it has done."
                            )
                            break
                        self.steps_used += 1
                        self.answer = ""
                        self.reasoning = ""
                        self._pending = ""
                        self._pending_reasoning = ""
                        self._last_push = 0.0
                        self.credits_left = (
                            await self.ledger.remaining() if self.ledger else 0
                        )
                    self.answered_by, calls = await self.router.stream_chat(
                        self._context_messages(),
                        model=self.selected_model,
                        on_delta=self._on_delta,
                        on_reasoning=self._on_reasoning,
                        tools=self._tool_schemas(),
                    )
                    self._flush(force=True)
                    if not calls:
                        break
                    self.messages.append(
                        {
                            "role": "assistant",
                            "content": self.answer or "",
                            "tool_calls": calls,
                        }
                    )
                    for call in calls:
                        if tool_calls_run >= MAX_TOOL_CALLS:
                            self.status = "Stopped — too many tool calls in one task."
                            return
                        tool_calls_run += 1
                        result = await self._execute_tool_call(call)
                        self.messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.get("id", ""),
                                "content": result,
                            }
                        )
                else:
                    self.status = "Reached the step limit for one task."
            except RouterBusy as e:
                self.error = str(e)
                self.status = (
                    "Kiri's free tier is busy — try again shortly, or pick "
                    "a specific model below."
                )
                await self._refund_if_unpaid()
            except RouterUnavailable as e:
                self.error = str(e)
                await self._refund_if_unpaid()
            except asyncio.CancelledError:
                # A stopped reply keeps whatever it said: persist the partial
                # answer so a killed stream never silently vanishes.
                self._flush(force=True)
                if self.answer:
                    self.messages.append({"role": "assistant", "content": self.answer})
                self._trim_history()
                await self._persist()
                raise
            except Exception:
                logger.exception("AI request failed")
                self.error = "Something went wrong talking to Kiri."
                await self._refund_if_unpaid()
            else:
                self._flush(force=True)
                if self.answer:
                    self.messages.append({"role": "assistant", "content": self.answer})
                self._trim_history()
                await self._persist()
            finally:
                self.streaming = False
                self._task = None
                self.approval = None
                self._approval_event = None
                if self.ledger is not None:
                    self.credits_left = await self.ledger.remaining()

    def stop(self) -> None:
        """Stop the current reply. Charged if it already said anything."""
        if self._task is not None and self.streaming:
            if not self._produced:
                self._refund_pending = True
            self.approval = None
            if self._approval_event is not None:
                self._approval_event.set()
            self._task.cancel()


ai_session = AiSession()

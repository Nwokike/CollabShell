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
import uuid

import flet as ft

from ai import catalog
from ai.credits import COST_PER_TURN, CreditsLedger
from ai.router import DEFAULT_MODEL, AiModel, KiriRouter, RouterBusy, RouterUnavailable
from ai.system_prompt import build_system_prompt
from ai.tools import CONFIRM, TIERS, ToolBox, label_for, schemas_for
from core import constants

logger = logging.getLogger("ai.session")

MAX_HISTORY = 40
# Stored conversations. A user's own history, so it is generous — but
# bounded, because every chat is rewritten to disk on every completed turn
# and an unbounded list would grow forever on a phone.
MAX_CHATS = 20
_TITLE_CHARS = 42
# Guards mirror DDGS's agent loop: a runaway task cannot drain the day.
MAX_STEPS = 6
MAX_TOOL_CALLS = 10
APPROVAL_TIMEOUT_SECONDS = 300
# Flet re-renders on every observable write; batching tokens keeps a fast
# model from flooding the Dart bridge with one update per token.
THROTTLE_SECONDS = 0.08


def _clean_messages(raw) -> list[dict]:
    """Only user/assistant turns survive a round trip through storage."""
    if not raw:
        return []
    try:
        loaded = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return []
    if not isinstance(loaded, list):
        return []
    return [
        m
        for m in loaded
        if isinstance(m, dict) and m.get("role") in ("user", "assistant")
    ][-MAX_HISTORY:]


def _title_for(messages: list[dict]) -> str:
    """A chat is named by its first question, like every chat app.

    Empty stays empty — "New chat" is what the UI shows for a blank
    thread, and storing it here would make the real first question look
    like it was already named.
    """
    for m in messages:
        if m.get("role") == "user":
            text = " ".join(str(m.get("content") or "").split())
            return text[:_TITLE_CHARS] + ("…" if len(text) > _TITLE_CHARS else "")
    return ""


def _new_chat(messages: list[dict] | None = None) -> dict:
    messages = list(messages or [])
    return {
        "id": uuid.uuid4().hex[:12],
        "title": _title_for(messages),
        "messages": messages,
        "updated": time.time(),
    }


def _valid_chat(chat) -> bool:
    return (
        isinstance(chat, dict)
        and isinstance(chat.get("id"), str)
        and isinstance(chat.get("messages"), list)
    )


def _cap_chats(chats: list[dict]) -> list[dict]:
    """Keep the newest MAX_CHATS. Deleting the oldest is the user's limit
    being enforced, not a bug: nothing they can still open is dropped."""
    if len(chats) <= MAX_CHATS:
        return chats
    ordered = sorted(chats, key=lambda c: float(c.get("updated") or 0), reverse=True)
    return ordered[:MAX_CHATS]


@ft.observable
class AiSession:
    def __init__(self):
        self.router = KiriRouter()
        self.ledger: CreditsLedger | None = None

        # ── User-visible state ────────────────────────────────────────────
        self.enabled: bool = True
        self.selected_model: str = DEFAULT_MODEL
        self.models: list[AiModel] = []
        self.models_loading: bool = False  # first fetch in flight, nothing to show
        # Retries gave up and Kiri could not be reached. A picker that
        # says "Starting…" forever is lying; this is how it stops.
        self.models_unreachable: bool = False
        self.models_stale: bool = False  # showing cache; the live list failed
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
        self.chats: list[dict] = []  # stored conversations, newest first
        self.active_chat_id: str = ""

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
        # Model calls charged for the current turn, and whether the
        # empty-reply retry has already been spent.
        self._calls_this_turn = 0
        self._empty_retried = False
        # Which chat to reopen on the next restart.
        self._restore_active = ""

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
            await self._load_chats()
            self.credits_left = await self.ledger.remaining()

        ft.context.page.run_task(_load)

    async def _load_chats(self) -> None:
        """Restore the chat list, carrying 2.3.0's single thread into it.

        A 2.3.0 user has one saved conversation under the old key. It
        becomes their first chat rather than being dropped on upgrade —
        losing someone's history to an upgrade is not acceptable.
        """
        raw = None
        if self._storage is not None:
            raw = await self._storage.get(constants.STORAGE_AI_CHATS)
        chats: list[dict] = []
        if raw:
            try:
                loaded = json.loads(raw)
                if isinstance(loaded, list):
                    chats = [c for c in loaded if _valid_chat(c)]
            except (TypeError, ValueError):
                logger.debug("stored AI chats unreadable", exc_info=True)

        if not chats and self._storage is not None:
            legacy = await self._storage.get(constants.STORAGE_AI_MESSAGES)
            messages = _clean_messages(legacy)
            if messages:
                chats = [_new_chat(messages)]
                await self._persist_chats(chats)

        chats = _cap_chats(chats)
        self.chats = chats
        active = self._restore_active
        self._restore_active = ""
        if not any(c["id"] == active for c in chats):
            active = chats[0]["id"] if chats else ""
        self.active_chat_id = active
        self._open_chat(active)

    def _open_chat(self, chat_id: str) -> None:
        """Make one chat the one on screen — and the one the next save
        writes to. Getting this wrong silently overwrites the wrong
        conversation, so the active id is set here, not at the call sites.
        """
        chat = next((c for c in self.chats if c["id"] == chat_id), None)
        self.active_chat_id = chat_id if chat is not None else ""
        self.messages = list(chat["messages"]) if chat else []
        self.answer = ""
        self.reasoning = ""
        self.error = ""
        self.status = ""
        self.answered_by = ""
        self.timeline.clear()
        self.steps_used = 0
        if chat is not None:
            chat["updated"] = time.time()

    def _sync_active(self) -> None:
        """Copy what is on screen back into its chat record."""
        chat = next((c for c in self.chats if c["id"] == self.active_chat_id), None)
        if chat is None:
            chat = _new_chat(list(self.messages))
            self.chats.insert(0, chat)
            self.active_chat_id = chat["id"]
            return
        chat["messages"] = list(self.messages)
        chat["updated"] = time.time()
        if not chat["title"]:
            chat["title"] = _title_for(self.messages)

    async def _persist_chats(self, chats: list[dict] | None = None) -> None:
        if self._storage is None:
            return
        try:
            await self._storage.set(
                constants.STORAGE_AI_CHATS,
                json.dumps(chats if chats is not None else self.chats),
            )
            await self._storage.set(
                constants.STORAGE_AI_ACTIVE_CHAT,
                self._restore_active or self.active_chat_id,
            )
        except Exception:
            logger.debug("AI chat save failed", exc_info=True)

    async def _persist(self) -> None:
        self._sync_active()
        await self._persist_chats()
        self.chats = _cap_chats(self.chats)

    def _trim_history(self) -> None:
        # The persisted blob is rewritten on every completed turn, so the list
        # must be bounded or storage grows without limit.
        if len(self.messages) > MAX_HISTORY:
            del self.messages[:-MAX_HISTORY]

    # ── Chats ──────────────────────────────────────────────────────────

    async def new_chat(self) -> None:
        """Start a fresh thread. The old one stays in the list."""
        self._sync_active()
        chat = _new_chat([])
        self.chats.insert(0, chat)
        self.chats = _cap_chats(self.chats)
        self._open_chat(chat["id"])
        await self._persist_chats()

    async def switch_chat(self, chat_id: str) -> None:
        if chat_id == self.active_chat_id:
            return
        if self.streaming:
            return  # switching mid-reply would strand the answer
        self._sync_active()
        self._open_chat(chat_id)
        self._restore_active = chat_id
        await self._persist_chats()

    async def delete_chat(self, chat_id: str) -> None:
        """Remove one chat. Deleting the last one leaves a clean sheet."""
        if self.streaming:
            return
        self.chats = [c for c in self.chats if c["id"] != chat_id]
        if self.active_chat_id == chat_id:
            self.active_chat_id = self.chats[0]["id"] if self.chats else ""
            self._open_chat(self.active_chat_id)
        await self._persist_chats()

    # ── Models ─────────────────────────────────────────────────────────

    async def refresh_models(self) -> None:
        """Show something immediately, then make it true.

        The cached catalog goes up first so the picker is never empty on a
        warm start, the live list replaces it a moment later, and a failure
        leaves the cached list in place with a quiet note instead of a
        blank dropdown.

        Three states, not two, because a retry loop that never gives up is
        its own lie: after the last attempt the picker says it cannot reach
        Kiri rather than sitting on "Starting…" forever.
        """
        if not self.models and not self.models_loading:
            cached = catalog.read_models()
            if cached:
                self.models = cached
        self.models_loading = not self.models
        self.models_unreachable = False
        try:
            models = await self.router.list_models()
        except RouterUnavailable:
            if not self.models:
                # Keep the loading flag so the panel's retry loop runs again;
                # the loop clears it once it gives up.
                self.models_loading = True
                self.status = "Still starting Kiri — trying again…"
                return
            self.models_stale = True
            self.status = "Showing the last known models — Kiri is not answering."
            return
        self.models = models
        self.models_loading = False
        self.models_stale = False
        if self.selected_model not in {m.id for m in models}:
            # A pinned model Kiri no longer serves would leave the dropdown
            # pointing at an option that is not in its own list.
            self.status = (
                f"{self.selected_model} is not being served right now — "
                "auto will pick instead."
            )
            self.selected_model = DEFAULT_MODEL
            if self._storage is not None:
                await self._storage.set(constants.STORAGE_AI_MODEL, DEFAULT_MODEL)
        else:
            self.status = ""
        catalog.write_models(models)

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
        """Clear this conversation without destroying the others."""
        self.messages.clear()
        self.answer = ""
        self.reasoning = ""
        self.error = ""
        self.status = ""
        self.timeline.clear()
        self.steps_used = 0
        chat = next((c for c in self.chats if c["id"] == self.active_chat_id), None)
        if chat is not None:
            chat["messages"] = []
            chat["title"] = ""
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
        """Every call in a turn that produced nothing is refunded.

        A turn can make several model calls (tools, an empty-response
        retry). If the user ends up with no answer, they should not be
        charged for any of them — that is the promise, stated per call.
        """
        if self._produced or self.ledger is None:
            return
        unpaid = max(self._calls_this_turn, 1)
        for _ in range(unpaid):
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
            self._calls_this_turn = 1
            self._empty_retried = False
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
                        self._calls_this_turn += 1
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
                        # A reasoning model can spend its whole budget
                        # thinking and return no text at all. Retrying once
                        # is the difference between a blank bubble and an
                        # answer; it is charged like any other call and
                        # refunded in full if it delivers nothing either.
                        if (
                            not self.answer.strip()
                            and not self._empty_retried
                            and self.router.last_finish_reason == "length"
                        ):
                            self._empty_retried = True
                            self.status = "That model ran out of room — asking again."
                            self.messages.append(
                                {
                                    "role": "user",
                                    "content": (
                                        "Your last reply used up its length "
                                        "before any text appeared. Answer again, "
                                        "briefly."
                                    ),
                                }
                            )
                            continue
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
                # The router knows this model's cap and what else is
                # available; say that instead of a bare "busy".
                self.status = self.router.advice_for_rate_limit(
                    self.answered_by or self.selected_model
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
                else:
                    # Two calls, nothing to show. Say so plainly and give
                    # the credits back — a silent blank is the worst
                    # possible outcome and the most expensive one.
                    self.error = (
                        f"{self.answered_by or self.selected_model} returned an "
                        "empty reply. Nothing was charged — try another model, "
                        "or ask again."
                    )
                    self.status = ""
                    await self._refund_if_unpaid()
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

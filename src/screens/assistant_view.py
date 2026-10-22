"""Assistant — the app-wide chat surface.

An imperative `ChatSession` rather than a component, for one reason: streaming
repaints at up to 5Hz and the transcript is the state. A component would
reconcile the whole tree per token; this rebuilds one list and pushes it.

Ported from DDGS's chat_screen with the parts that matter. The lifecycle is the
important half: the session object is retained on the page, so minimizing pops
the view without destroying the conversation or cancelling a running turn, and
the FAB brings back the exact same transcript, scroll position and pending
approval.

Metering runs through `services.ai_credits.run_metered_turn`, so the gate, the
per-step charge and the "delivered work is worth one step" floor rule come
from one place.

Two throttle clocks — text and thought — stay independent. Sharing one meant a
text flush reset the thought throttle and vice versa, so thinking could
silently starve for 500ms every time a text token landed. State mutates on
*every* event; only the repaint is throttled.
"""

from __future__ import annotations

import asyncio
import logging
import time

import flet as ft

from components.model_pill import build_model_pill
from core import tokens
from core.styles import tip_text
from core.theme import AppColors, brand_color

logger = logging.getLogger("assistant")

_CHAT_ICON = tokens.ASSISTANT_ICON
_THOUGHT_CAP = 8000

TEXT_FLUSH_SEC = 0.2
THOUGHT_FLUSH_SEC = 0.5
APPROVAL_TIMEOUT_SEC = 120

# Only these events refresh the credit chip: the balance can move on a stop,
# a failure or a rate limit, not only on success.
_TERMINAL_EVENTS = ("text_final", "error", "stopped")


def _starter_rows():
    """Suggestion rows for the welcome state, from the app's real tools.

    Kept here so what the starters promise is always what the tools do.
    """
    # Every capability gets a sample, the way DDGS's "What I can do" list works:
    # one row per thing the assistant can do, so nothing it is able to do is
    # discoverable only by guessing. A row is a full sentence a user would say,
    # not a tool name — the tool is the model's business, not theirs.
    return [
        # ── sessions ──
        (ft.Icons.DNS_ROUNDED, "What sessions do I have?", "List my Colab sessions"),
        (ft.Icons.ADD_BOX_ROUNDED, "Create a session", "Create a new session named 'my-lab'"),
        # ── running code ──
        (ft.Icons.PLAY_ARROW_ROUNDED, "Run code on my session", "Run this and tell me what happened: print(1+1)"),
        (ft.Icons.MEMORY_ROUNDED, "What variables are in my kernel?", "What variables are in my kernel right now?"),
        (ft.Icons.TABLE_CHART_ROUNDED, "Install a package", "Install pandas and confirm it worked"),
        (ft.Icons.RESTART_ALT_ROUNDED, "Restart the kernel", "Restart the kernel — my memory is full"),
        # ── the notebook ──
        (ft.Icons.DESCRIPTION_ROUNDED, "Explain my notebook", "Read my active notebook and explain what it does, cell by cell"),
        (ft.Icons.BUG_REPORT_ROUNDED, "Fix the error", "Read my active notebook, find the last error, and fix it"),
        (ft.Icons.EDIT_NOTE_ROUNDED, "Write a cell for me", "Write a cell that loads my data and cleans it"),
        (ft.Icons.TAB_ROUNDED, "What notebook tabs are open?", "List the notebook tabs I have open"),
        # ── files ──
        (ft.Icons.FOLDER_OPEN_ROUNDED, "What files are on my session?", "List the files in my session"),
        (ft.Icons.DOWNLOAD_ROUNDED, "Read a file for me", "Read /content/data.csv and show me the first few rows"),
        (ft.Icons.UPLOAD_FILE_ROUNDED, "Upload a file to my session", "Upload ~/data.csv to my session as /content/data.csv"),
        (ft.Icons.TERMINAL_ROUNDED, "Check the terminal", "Show me the recent terminal output and flag anything concerning"),
        (ft.Icons.DELETE_OUTLINE_ROUNDED, "Delete a file", "Delete /content/old.csv from my session"),
        # ── the account ──
        (ft.Icons.SPEED_ROUNDED, "How many compute units are left?", "How many compute units do I have left?"),
        (ft.Icons.HISTORY_ROUNDED, "What has the session been doing?", "Show me the session activity log"),
        # ── teardown ──
        (ft.Icons.POWER_SETTINGS_NEW_ROUNDED, "Stop the session", "Stop my session when you're done"),
    ]


def _empty_turn() -> dict:
    return {
        "role": "assistant",
        "text": "",
        "thought": "",
        # When the reasoning began, for the "Thought for Ns" receipt, and
        # whether the block is expanded. `None` means it never reasoned.
        "thought_started_at": None,
        "thought_seconds": 0,
        "thought_open": True,
        "steps_rows": [],
        "partial": True,
        "error": None,
        "error_message": "",
        "stopped": False,
        "cost": 0,
        "steps": 0,
        "model": "",
    }


_CELL_REF_PREFIX = "Cells: "

# A step row's consequence, kept short: the renderer appends it to the label,
# and a tool that printed 2 KB must not become a 2 KB label. DDGS shows a
# short outcome or a count instead.
_OUTCOME_CAP = 120

# A user-legible label per tool, verb first, the way DDGS renders step rows
# (chat_agent.py:210-246). The renderer shows these verbatim, so there is no
# decoration for it to strip back off later.
_TOOL_LABELS = {
    "_exec": "Running code",
    "read_notebook": "Reading the notebook",
    "read_terminal": "Reading the terminal",
    "install_package": "Installing a package",
    "list_variables": "Listing variables",
    "read_file": "Reading a file",
    "list_files": "Listing files",
    "upload_file": "Uploading a file",
    "write_cells": "Writing cells",
    "list_notebook_tabs": "Listing notebook tabs",
    "get_usage": "Checking resource usage",
    "get_log": "Reading the session log",
    "restart_kernel": "Restarting the kernel",
    "stop_session": "Stopping the session",
    "delete_file": "Deleting a file",
}


def _clip_outcome(text) -> str:
    """A step row's consequence, one line and bounded."""
    flat = " ".join(str(text or "").split())
    if len(flat) <= _OUTCOME_CAP:
        return flat
    return flat[: _OUTCOME_CAP - 1].rstrip() + "…"


_step_seq = 0


def _unique_step_id(name: str) -> str:
    """A row id that cannot collide, for a call with no id of its own.

    kani's ``tool_call_id`` is the right key, but a call that somehow arrives
    without one must not be re-keyed by tool name — that is the collision the
    id exists to prevent.
    """
    global _step_seq
    _step_seq += 1
    return f"{name}#{_step_seq}"


def _running_step_id(turn: dict | None) -> str:
    """The oldest step row still waiting, for a done event with no id.

    This is the path where a tool finished but its identity was lost, so the
    row that opened is the row that closes.
    """
    if not turn:
        return ""
    for row in turn.get("steps_rows") or []:
        if row.get("state") == "running":
            return str(row.get("id") or "")
    return ""


def _pretty_label(name: str, args: dict | None = None) -> str:
    """The step row's label: a verb phrase, and the thing it acts on when short."""
    label = _TOOL_LABELS.get(name, f"Running {name}")
    args = args or {}
    detail = str(args.get("path") or args.get("package") or args.get("target") or "")
    detail = " ".join(detail.split())
    if detail and len(detail) <= 60:
        return f"{label}: {detail}"
    return label


def _cell_refs(step: dict) -> list[str]:
    """Pull the cell ids a `write_cells` step reported.

    The tool reports them in a fixed "Cells: <id>, <id>" tail so the model can
    name them too; this reads that tail back. Anything else returns [] and the
    step row stays inert.
    """
    if step.get("name") != "write_cells":
        return []
    text = str(step.get("result") or "")
    if _CELL_REF_PREFIX not in text:
        return []
    tail = text.rsplit(_CELL_REF_PREFIX, 1)[1].strip()
    return [part.strip() for part in tail.split(",") if part.strip()]


def _notice(message: str, color: str) -> ft.Control:
    return ft.Container(
        content=ft.Text(message, size=tokens.FONT_SM, color=color),
        padding=ft.Padding.all(tokens.SPACE_SM),
        border_radius=tokens.RADIUS_MD,
        bgcolor=ft.Colors.with_opacity(0.12, color),
    )


def _turns_from_messages(messages: list[dict]) -> list[dict]:
    """Rebuild renderable turns from a saved conversation.

    Saved messages are the flat role/content pairs the agent consumes, so the
    visual extras (step rows, cards, receipts) are not in them — an reopened
    chat renders the conversation itself rather than inventing tool detail.
    """
    turns: list[dict] = []
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        text = str(message.get("content") or "")
        if role == "user":
            turns.append({"role": "user", "text": text})
        elif role == "assistant":
            turn = _empty_turn()
            turn["text"] = text
            turn["partial"] = False
            turns.append(turn)
    return turns


class ChatSession:
    """Owns one conversation: transcript, rendering, and the agent turn."""

    def __init__(self, page: ft.Page, state, services, controller=None):
        from services import conversation_service as conversations

        self.page = page
        self.state = state
        self.services = services
        self.controller = controller
        self._conversations = conversations

        self.conversation_id = conversations.ensure_active()
        saved = conversations.load_conversation(self.conversation_id) or {}
        self._turns = _turns_from_messages(saved.get("messages") or [])

        self._current: dict | None = None
        self._busy = False
        self._task: asyncio.Task | None = None
        self._cancel = asyncio.Event()
        self._last_text_flush = 0.0
        self._last_thought_flush = 0.0
        # Set once teardown starts; every UI touch afterwards is a no-op.
        self._closing = False
        self._confirm: tuple[asyncio.Event, dict] | None = None
        self._credits_value = 0

        self._build_controls()

    # ── widget tree ─────────────────────────────────────────────────────────

    def _build_controls(self) -> None:
        self._list = ft.ListView(
            controls=[],
            spacing=tokens.SPACE_LG,
            expand=True,
            auto_scroll=True,
            padding=ft.Padding.symmetric(horizontal=tokens.SPACE_MD),
        )

        self.field = ft.TextField(
            hint_text="Ask anything",
            expand=True,
            dense=True,
            multiline=True,
            min_lines=1,
            max_lines=5,
            shift_enter=True,
            fill_color=ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE),
            content_padding=ft.Padding.all(tokens.SPACE_MD),
            border=ft.OutlineInputBorder(border_radius=tokens.RADIUS_LG),
        )
        # Enter sends; shift_enter adds the newline.
        self.field.on_submit = lambda e: self._send_from_field()

        # One circular button, two faces: send when idle, stop when busy.
        self.send_btn = ft.IconButton(
            icon=ft.Icons.SEND_ROUNDED,
            icon_color=ft.Colors.WHITE,
            tooltip="Send",
            style=ft.ButtonStyle(shape=ft.CircleBorder(), bgcolor=self._brand()),
            on_click=lambda e: self._on_composer_button(),
        )

        self._credits_text = ft.Text("…", size=tokens.FONT_XS, weight=ft.FontWeight.W_600)

        # The balance is a control, not a readout: tapping it opens the wallet
        # (balance, cost table, ad top-up) exactly as DDGS's chip does. A
        # number nobody can act on is just decoration.
        self.credits_chip = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(_CHAT_ICON, size=tokens.ICON_SM, color=self._credit_color()),
                    self._credits_text,
                ],
                spacing=2,
                tight=True,
            ),
            # Same geometry as the model pill so the two read as one family;
            # the colour stays because it carries the balance signal.
            padding=ft.Padding.symmetric(horizontal=7, vertical=3),
            border_radius=tokens.RADIUS_PILL,
            bgcolor=ft.Colors.with_opacity(0.1, self._credit_color()),
            ink=True,
            tooltip="Assistant credits, tap for details",
            on_click=lambda e: self._open_wallet(),
        )

        # Model selector: an actual dropdown menu (LM Router's pattern), not
        # the modal list DDGS uses — you keep the transcript in view.
        self.model_chip = build_model_pill(
            self.page, on_pick=self._pick_model
        )

        # Sherlock's header shape (via DDGS): ONE row, left group and right
        # group, SPACE_BETWEEN, and scroll on the whole row so oversized
        # controls scroll instead of clipping on narrow screens. An ft.AppBar
        # cannot do this — its actions get unbounded width and the wide pills
        # push the + off and paint over the title.
        header = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Row(
                        [
                            ft.IconButton(
                                icon=ft.Icons.ARROW_BACK_ROUNDED,
                                tooltip="Minimize assistant",
                                on_click=lambda e: self.close(),
                            ),
                            ft.Icon(_CHAT_ICON, size=20, color=self._brand()),
                            ft.Text(
                                "Assistant",
                                size=tokens.FONT_MD,
                                weight=ft.FontWeight.W_700,
                                font_family="Outfit",
                            ),
                        ],
                        spacing=6,
                        tight=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    # Right controls: creation, history, the readouts, then the
                    # model selector. Plus and history carry tight padding so
                    # they read as one pair.
                    ft.Row(
                        [
                            ft.IconButton(
                                icon=ft.Icons.ADD_ROUNDED,
                                icon_size=18,
                                icon_color=self._brand(),
                                tooltip="New chat",
                                style=ft.ButtonStyle(
                                    padding=ft.Padding(2, 6, 2, 6)
                                ),
                                on_click=lambda e: self.new_conversation(),
                            ),
                            ft.IconButton(
                                icon=ft.Icons.HISTORY_ROUNDED,
                                icon_size=18,
                                icon_color=self._brand(),
                                tooltip="Past chats",
                                style=ft.ButtonStyle(
                                    padding=ft.Padding(2, 6, 2, 6)
                                ),
                                on_click=lambda e: self._show_history(),
                            ),
                            self.credits_chip,
                            self.model_chip,
                        ],
                        spacing=4,
                        tight=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                scroll=ft.ScrollMode.AUTO,
            ),
            padding=ft.Padding(tokens.SPACE_SM, tokens.SPACE_SM, tokens.SPACE_LG, tokens.SPACE_SM),
        )

        composer = ft.Container(
            content=ft.Row(
                [self.field, self.send_btn],
                vertical_alignment=ft.CrossAxisAlignment.END,
                spacing=tokens.SPACE_NANO,
            ),
            padding=ft.Padding(tokens.SPACE_MD, tokens.SPACE_SM, tokens.SPACE_MD, tokens.SPACE_MD),
        )

        self.view = ft.View(
            route="/assistant",
            controls=[
                ft.SafeArea(
                    expand=True,
                    content=ft.Container(
                        content=ft.Column(
                            [header, ft.Container(self._list, expand=True), composer],
                            spacing=0,
                            expand=True,
                        ),
                        expand=True,
                        bgcolor=ft.Colors.SURFACE,
                    ),
                )
            ],
            padding=0,
            spacing=0,
        )
        self._render()
        self._refresh_credits()

    def _brand(self) -> str:
        """The live brand colour. Shared with the FAB and the model pill so the
        three can never disagree, and read from the theme so a light/dark flip
        is followed rather than pinned."""
        return brand_color(self.page)

    def _credit_color(self) -> str:
        """The balance's band colour: green comfortable, amber near the wall,
        red at it."""
        from components.credit_pill import credit_color

        return credit_color(self._credits_value)

    def _open_wallet(self) -> None:
        """Open the wallet dialog (balance, cost table, ad top-up)."""
        try:
            from components.wallet_dialog import show_wallet_dialog

            show_wallet_dialog(self.page, self.state, self.services)
        except Exception:
            logger.debug("wallet open failed", exc_info=True)

    def _pick_model(self, model_id: str) -> None:
        """Persist a model choice made from the header dropdown."""
        from services import model_catalog

        async def _save() -> None:
            self.state.ai_model = model_id
            storage = getattr(self.services, "storage", None)
            if storage is not None:
                try:
                    from core.constants import STORAGE_AI_MODEL

                    await storage.set(STORAGE_AI_MODEL, model_id)
                except Exception:
                    logger.debug("model save failed", exc_info=True)
            try:
                # The live port when the app attached to one, the override when
                # the user set one. Passing `state.ai_router_url` raw sent an
                # empty string whenever the router auto-started, which is the
                # "Request URL is missing an 'http://'… protocol" failure in the
                # log: every model pick logged it and then refreshed nothing.
                await model_catalog.refresh_catalog(
                    model_catalog.router_url_for_read()
                )
            except Exception:
                pass
            # Rebuild the pill so its label matches the new choice.
            self._rebuild_header_controls()

        try:
            self.page.run_task(_save)
        except Exception:
            logger.debug("model pick failed", exc_info=True)

    def refresh_model_chip(self) -> None:
        """Rebuild the header pill, but only when it actually changed.

        The pill is a static control inside an imperative View, so nothing
        re-renders it when the router's status moves. Rebuilding it per token
        would construct a whole control tree for a label that almost never
        moves, so this short-circuits on a signature first.

        The signature is computed by `model_pill.pill_signature`, not here:
        two copies of the "what does the pill depend on" question is exactly
        how the two drift apart.

        Ported from DDGS's `chat_screen.py` refresh_model_chip, widened because
        the pill bakes in a menu where DDGS's dialog re-read live state on open.
        """
        from components.model_pill import build_model_pill, pill_signature

        try:
            signature = pill_signature()
            if signature == getattr(self, "_pill_signature", None):
                return
            self._pill_signature = signature
            new_chip = build_model_pill(self.page, on_pick=self._pick_model)
            self.model_chip.content = new_chip.content
            self.model_chip.bgcolor = new_chip.bgcolor
            self.model_chip.items = new_chip.items
            self.model_chip.tooltip = new_chip.tooltip
            self.model_chip.update()
        except Exception:
            logger.debug("model chip refresh failed", exc_info=True)

    def _rebuild_header_controls(self) -> None:
        """Swap the credits chip and model pill for freshly-built ones.

        The pill's label is derived from the router's status, so after a pick
        (or a status change) it has to be rebuilt rather than mutated in place.
        """
        self.refresh_model_chip()
        try:
            self.credits_chip.bgcolor = ft.Colors.with_opacity(
                0.1, self._credit_color()
            )
            self.credits_chip.content.controls[0].color = self._credit_color()
            self.credits_chip.update()
        except Exception:
            logger.debug("credit chip refresh failed", exc_info=True)

    # ── lifecycle ──────────────────────────────────────────────────────────

    def restore(self) -> None:
        """Re-attach this retained session to the view stack.

        Append-if-absent: the session can be re-opened from more than one
        place (FAB, history, a step→cell tap), and stacking the same view twice
        would mean a back press only closes a duplicate.
        """
        if self.view not in self.page.views:
            self.page.views.append(self.view)
        self.state.assistant_open = True
        self.state.assistant_minimized = False
        try:
            self.page.update()
        except Exception:
            logger.debug("assistant restore: update failed")

    def close(self) -> None:
        """Minimize.

        The session is retained, and a running turn is deliberately NOT
        cancelled — minimizing puts the conversation away, not the work. A
        pending approval also survives, so re-opening mid-gate lands on the same
        card rather than a fresh one.
        """
        self._persist_history()
        try:
            if self.page.views and self.page.views[-1] is self.view:
                self.page.views.pop()
            self.state.assistant_open = False
            self.state.assistant_minimized = True
            self.page.update()
        except Exception:
            self.state.assistant_open = False
            self.state.assistant_minimized = True

    def shutdown(self) -> None:
        """Tear the session down before Flet releases the page."""
        if self._closing:
            return
        self._closing = True
        self._cancel.set()
        if self._task is not None and not self._task.done():
            self._task.cancel()
        try:
            self._persist_history()
        except Exception:
            logger.debug("persist on shutdown failed", exc_info=True)

    def new_conversation(self) -> None:
        """Start a fresh chat. Saves the current one first."""
        self._persist_history()
        self.conversation_id = self._conversations.new_conversation_id()
        self.state.active_assistant_conversation = self.conversation_id
        self._turns = []
        self._current = None
        self._busy = False
        self._cancel = asyncio.Event()
        self._set_busy_ui(False)
        self._render()

    def _show_history(self) -> None:
        from services import conversation_service as conversations

        rows = conversations.refresh_state()
        handler = getattr(self.controller, "open_assistant_history", None)
        if callable(handler):
            handler(rows)
            return
        logger.debug("no open_assistant_history handler; %d chats", len(rows))

    def load_conversation(self, conversation_id: str) -> bool:
        """Replace the transcript with a saved chat.

        Returns False if the chat cannot be read, leaving the current one open
        — a failed switch must not blank the view the user is looking at.
        """
        payload = self._conversations.load_conversation(conversation_id)
        if payload is None:
            return False
        self._persist_history()
        self.conversation_id = conversation_id
        self.state.active_assistant_conversation = conversation_id
        self._turns = _turns_from_messages(payload.get("messages") or [])
        self._current = None
        self._render()
        return True

    # ── send / run ─────────────────────────────────────────────────────────

    def _send_from_field(self) -> None:
        text = (self.field.value or "").strip()
        if not text or self._busy:
            return
        self.field.value = ""
        try:
            self.field.update()
        except Exception:
            pass
        self.send(text)

    def _on_composer_button(self) -> None:
        if self._busy:
            self.stop()
        else:
            self._send_from_field()

    def send(self, text: str) -> None:
        """Queue one turn.

        Refuses while busy, so a double-tap never doubles the spend, and
        refuses blank text, so a stray tap cannot start a metered turn that
        sends nothing to the model. Callers include the starter rows, so the
        strip belongs here rather than only in the composer.
        """
        text = (text or "").strip()
        if not text or self._busy or self._closing:
            return
        self._busy = True
        self._cancel = asyncio.Event()
        self._set_busy_ui(True)

        self._turns.append({"role": "user", "text": text})
        self._current = _empty_turn()
        self._turns.append(self._current)
        self._render()

        self._task = asyncio.ensure_future(self._run_turn(text))
        self._task.add_done_callback(self._on_turn_done)

    async def _run_turn(self, text: str) -> None:
        from services import ai_credits

        result = await ai_credits.run_metered_turn(
            state=self.state,
            credits=getattr(self.services, "credits", None),
            model=getattr(self.state, "ai_model", "auto"),
            tools=self._build_tools(),
            messages=self._model_history() + [{"role": "user", "content": text}],
            system=self._system_prompt(),
            on_token=self._on_token,
            on_thought=self._on_thought,
            on_tool_start=self._on_tool_start,
            on_tool_done=self._on_tool_done,
            should_stop=self._cancel.is_set,
        )

        if not result.get("ok"):
            kind = "credits" if result.get("out_of_credits") else "unavailable"
            self._emit("error", {"kind": kind, "message": result.get("error", "")})
            return

        if result.get("cancelled"):
            # One terminal event only: a stopped turn must not also render a
            # finished answer with a cost line.
            self._emit(
                "stopped",
                {
                    "text": result.get("text", ""),
                    "cost": result.get("cost", 0),
                    "steps": result.get("model_steps", 0),
                },
            )
            return
        self._emit(
            "text_final",
            {
                "text": result.get("text", ""),
                "model": result.get("model", ""),
                "cost": result.get("cost", 0),
            },
        )

    def _on_token(self, token: str) -> None:
        self._emit("text_partial", {"text": token})

    def _on_thought(self, text: str) -> None:
        """The model's reasoning, straight off the tapped SSE stream.

        kani discards these deltas (`services/reasoning.py` explains how the
        bytes are teed instead). Without this the user watches an answer appear
        from nowhere, which is the whole reason both reference apps surface it.
        """
        self._emit("thought", {"text": text})

    def _on_tool_start(self, name: str, payload: dict) -> None:
        args = payload.get("args") or {}
        # A tool call means a new model round is about to start. Anything this
        # round already said before the call ("let me check that…") is a
        # preamble, not the answer, so it is dropped — the same thing DDGS does
        # in its on_round_reset.
        if self._current is not None:
            self._current["text"] = ""
        # The row is keyed by the tool_call_id, not the name: the same tool can
        # be called twice in one turn and both rows must close on their own.
        # A missing id would re-key the row by name and reintroduce the
        # collision, so it is made unique instead.
        row_id = str(payload.get("id") or "") or _unique_step_id(name)
        self._emit(
            "step_start",
            {
                "label": _pretty_label(name, args),
                "id": row_id,
                "name": name,
                "args": dict(args),
            },
        )

    def _on_tool_done(self, name: str, payload: dict) -> None:
        result = payload.get("result", "")
        error = payload.get("error")
        args = payload.get("args") or {}
        data = {
            # The same id the row was opened with. A missing one cannot fall
            # back to the name (that is the collision the id exists to stop),
            # so the row that is still spinning is the one being closed.
            "id": str(payload.get("id") or "") or _running_step_id(self._current),
            "name": name,
            "label": _pretty_label(name, args),
            "result": result,
            # write_cells echoes the ids it inserted so this row can point
            # back at the cells and hand them over to the user.
            "refs": _cell_refs({"name": name, "result": result}),
        }
        self._emit("step_error" if error else "step_done", {**data, "error": error})

    def _build_tools(self) -> list:
        from services.ai_tools import build_tools

        return build_tools(
            getattr(self.state, "active_session_name", "") or "",
            self.services,
            self.state,
            ask_confirm=self.ask_confirm,
        )

    def _system_prompt(self) -> str:
        from ai import skill_text

        return skill_text()

    def _model_history(self) -> list[dict]:
        from services.conversation_service import flat_from_turns

        return flat_from_turns(self._turns)[-30:]

    def _on_turn_done(self, task) -> None:
        self._busy = False
        self._task = None
        self._set_busy_ui(False)
        if self._closing:
            return
        if task.cancelled():
            # A hard cancel (the fallback path in stop(), or a teardown): the
            # turn never got to emit its own terminal event, so the user would
            # otherwise see a half-rendered bubble and a stuck spinner.
            self._close_running_rows()
            self._emit("stopped", {"text": "", "cost": 0, "steps": 0})
            self._persist_history()
            self._render()
            return
        exc = task.exception()
        if exc is not None:
            logger.warning("Assistant turn crashed: %s", exc)
            self._emit(
                "error",
                {"kind": "unavailable", "message": "The assistant stopped unexpectedly."},
            )
        self._persist_history()
        self._render()

    def stop(self) -> None:
        """Stop now: raise the flag the turn polls between tokens.

        The floor rule means work already shown is still billed, so stopping
        never finishes as a free model call. The hard cancel is a fallback for
        a model that stopped emitting and therefore stopped polling — without a
        deadline the Stop button could hang the session.
        """
        self._cancel.set()
        if self._task is not None and not self._task.done():
            # Give the turn one round of streaming (and the token poll that
            # goes with it) to notice the flag and end itself gracefully. The
            # deadline only matters for a model that stopped emitting and so
            # stopped polling — without it the Stop button could hang.
            from core.constants import TURN_STOP_GRACE_S

            deadline = time.monotonic() + TURN_STOP_GRACE_S

            async def _backstop() -> None:
                if self._task is None or self._task.done():
                    return
                if time.monotonic() < deadline:
                    return
                self._task.cancel()

            # Called, not referenced: the coroutine is what is scheduled, so
            # the deadline inside it is the only thing that can cancel.
            self.page.run_task(_backstop())

    def _set_busy_ui(self, busy: bool) -> None:
        self.send_btn.icon = ft.Icons.STOP_ROUNDED if busy else ft.Icons.SEND_ROUNDED
        self.send_btn.tooltip = "Stop" if busy else "Send"
        self.send_btn.style = ft.ButtonStyle(
            shape=ft.CircleBorder(),
            bgcolor=ft.Colors.ERROR if busy else self._brand(),
        )
        try:
            self.send_btn.update()
        except Exception:
            pass

    # ── approval gate ──────────────────────────────────────────────────────

    async def ask_confirm(self, label: str, detail: str = "") -> bool:
        """Approve/deny gate for destructive tools. Times out to deny."""
        event = asyncio.Event()
        self._confirm = (event, {"label": label, "detail": detail, "decision": None})
        self._render()
        try:
            await asyncio.wait_for(event.wait(), timeout=APPROVAL_TIMEOUT_SEC)
            decision = self._confirm[1]["decision"] if self._confirm else None
            return decision == "allow"
        except (TimeoutError, asyncio.CancelledError):
            return False
        finally:
            self._confirm = None
            if not self._closing:
                self._render()

    def _confirm_decision(self, decision: str) -> None:
        # First answer wins: a second tap on a settled gate is a no-op rather
        # than a race against the tool that already resumed.
        if self._confirm and self._confirm[1].get("decision") is None:
            self._confirm[1]["decision"] = decision
            self._confirm[0].set()

    def _toggle_thought(self, turn: dict) -> None:
        """Expand or collapse one turn's reasoning, and repaint.

        The state lives on the turn so a reopened chat and a re-render both
        agree, rather than on a widget the renderer throws away.
        """
        turn["thought_open"] = not turn.get("thought_open", False)
        self._render()

    def _close_running_rows(self) -> None:
        """Settle any step row still spinning, so no row is stuck forever.

        A tool can open a row and then the turn ends before it closes — the
        router dies, the user stops, the turn is cancelled. Leaving those
        running is a ProgressRing the user waits on for nothing.
        """
        if self._current is None:
            return
        for row in self._current["steps_rows"]:
            if row.get("state") == "running":
                row["state"] = "error"
                row["error"] = "did not finish"

    def _reveal_cell(self, cell_id: str) -> None:
        """Hand an assistant-written cell over to the user.

        The controller owns how a session is reached (route, view stack), so
        the chat only says which cell — the shell decides the rest.
        """
        handler = getattr(self.controller, "reveal_cell", None)
        if not callable(handler):
            return
        try:
            handler(getattr(self.state, "active_session_name", "") or "", cell_id)
        except Exception:
            logger.debug("reveal_cell failed", exc_info=True)

    # ── emit ───────────────────────────────────────────────────────────────

    def _emit(self, event: str, data: dict) -> None:
        if self._closing:
            return
        now = time.monotonic()
        force = True

        if event == "text_partial" and self._current is not None:
            self._current["text"] += str(data.get("text", ""))
            force = False
            if now - self._last_text_flush < TEXT_FLUSH_SEC:
                return
            self._last_text_flush = now
        elif event == "thought" and self._current is not None:
            buf = (self._current.get("thought") or "") + data.get("text", "")
            self._current["thought"] = buf[-_THOUGHT_CAP:]
            force = False
            if now - self._last_thought_flush < THOUGHT_FLUSH_SEC:
                return
            self._last_thought_flush = now
        elif event == "step_start" and self._current is not None:
            self._current["steps_rows"].append(
                {
                    "id": data.get("id", ""),
                    "label": data.get("label", ""),
                    "name": data.get("name", ""),
                    "state": "running",
                    "outcome": "",
                    "error": None,
                    "refs": [],
                }
            )
        elif event in ("step_done", "step_error") and self._current is not None:
            rows = self._current["steps_rows"]
            for row in rows:
                if row["id"] == data.get("id"):
                    row["state"] = "error" if event == "step_error" else "done"
                    row["outcome"] = _clip_outcome(data.get("result") or "")
                    row["error"] = data.get("error")
                    if data.get("refs"):
                        row["refs"] = list(data["refs"])
                    break
            else:
                # An id with no row for it. That is a wiring fault, not a row to
                # invent: appending a second row would hide the bug behind a
                # duplicate while the real one kept spinning. The row closer
                # settles whatever was left running.
                logger.debug(
                    "step event for unknown id %r (tool %s)",
                    data.get("id"),
                    data.get("name", ""),
                )
        elif event == "thought" and self._current is not None:
            if self._current.get("thought_started_at") is None:
                self._current["thought_started_at"] = now
            buf = (self._current.get("thought") or "") + data.get("text", "")
            self._current["thought"] = buf[-_THOUGHT_CAP:]
            force = False
            if now - self._last_thought_flush < THOUGHT_FLUSH_SEC:
                return
            self._last_thought_flush = now
        elif event == "text_final" and self._current is not None:
            self._current["text"] = data.get("text", "") or self._current["text"]
            self._current["model"] = data.get("model", "")
            self._current["cost"] = data.get("cost", 0)
            self._current["partial"] = False
            # Freeze the receipt: how long it thought, and collapse the block
            # now that the answer is here. Both references do exactly this
            # (`thinking.py:41-45`) — the reasoning stops being the subject the
            # moment there is an answer.
            if self._current.get("thought"):
                started = self._current.get("thought_started_at")
                if started is not None:
                    self._current["thought_seconds"] = max(1, int(now - started))
                self._current["thought_open"] = False
            self._close_running_rows()
            self._persist_history()
        elif event == "stopped" and self._current is not None:
            self._current["stopped"] = True
            self._current["partial"] = False
            # The work before the stop was still billed, so the turn carries
            # its cost and step count instead of looking unanswered.
            if data.get("text"):
                self._current["text"] = str(data["text"])
            self._current["cost"] = data.get("cost", 0)
            self._current["steps"] = data.get("steps", 0)
            self._close_running_rows()
        elif event == "error" and self._current is not None:
            self._current["error"] = data.get("kind", "unavailable")
            self._current["error_message"] = str(data.get("message") or "")
            self._current["partial"] = False
            self._close_running_rows()

        if event in _TERMINAL_EVENTS:
            self._refresh_credits()
        self._render(force=force)

    # ── rendering ──────────────────────────────────────────────────────────

    def _render(self, force: bool = True) -> None:
        """Rebuild the transcript list wholesale, then push only that list.

        Never `page.update()` here: a full-page push mid-stream costs a round
        trip per token, and anything reconciling the app shell at the same time
        tears the chat's own widgets.
        """
        if self._closing:
            return
        controls: list[ft.Control] = []
        if not self._turns:
            controls.append(self._welcome())
        for turn in self._turns:
            if turn.get("role") == "user":
                controls.append(self._render_user(turn))
            else:
                controls.append(self._render_assistant(turn))
        self._list.controls = controls
        try:
            self._list.update()
        except Exception:
            logger.debug("assistant render: list update failed")

    def _render_user(self, turn: dict) -> ft.Control:
        return ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.END,
            controls=[
                ft.Container(
                    content=ft.Text(
                        turn.get("text", ""),
                        size=tokens.FONT_SM,
                        color=ft.Colors.WHITE,
                        selectable=True,
                    ),
                    padding=ft.Padding.all(tokens.SPACE_MD),
                    border_radius=ft.BorderRadius(
                        tokens.RADIUS_XL, tokens.RADIUS_XL, tokens.RADIUS_XS, tokens.RADIUS_XL
                    ),
                    bgcolor=ft.Colors.PRIMARY,
                    width=min(320, (self.page.width or 320) * 0.8),
                )
            ],
        )

    def _render_assistant(self, turn: dict) -> ft.Control:
        kids: list[ft.Control] = []

        thought = str(turn.get("thought") or "").strip()
        if thought:
            # Open while it streams so the user watches the model think, then
            # collapsed to a one-line receipt. DDGS and lm-router both land on
            # exactly this: "Thinking…" while it runs, "Thought for Ns" after
            # (`chat_screen.py:1998-2059` and `components/thinking.py:32-45`).
            still_thinking = bool(turn.get("partial")) and not turn.get("text")
            open_ = bool(turn.get("thought_open", still_thinking))
            if still_thinking:
                header = "Thinking…"
            elif turn.get("thought_seconds"):
                header = f"Thought for {turn['thought_seconds']}s"
            else:
                header = "Thought it through"
            body: list[ft.Control] = []
            if open_:
                body.append(
                    ft.Container(
                        content=ft.Text(
                            thought,
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                            selectable=True,
                        ),
                        padding=ft.Padding.only(
                            left=tokens.SPACE_MD, top=tokens.SPACE_XS
                        ),
                        border=ft.Border(
                            left=ft.BorderSide(2, ft.Colors.with_opacity(
                                0.3, ft.Colors.ON_SURFACE_VARIANT
                            ))
                        ),
                    )
                )
            kids.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Icon(
                                        ft.Icons.PSYCHOLOGY_OUTLINED,
                                        size=tokens.ICON_SM,
                                        color=ft.Colors.ON_SURFACE_VARIANT,
                                    ),
                                    ft.Text(
                                        header,
                                        size=tokens.FONT_XS,
                                        color=ft.Colors.ON_SURFACE_VARIANT,
                                    ),
                                    ft.Icon(
                                        ft.Icons.EXPAND_LESS_ROUNDED
                                        if open_
                                        else ft.Icons.EXPAND_MORE_ROUNDED,
                                        size=12,
                                        color=ft.Colors.ON_SURFACE_VARIANT,
                                    ),
                                ],
                                spacing=tokens.SPACE_SM,
                                tight=True,
                            ),
                            *body,
                        ],
                        spacing=tokens.SPACE_XS,
                        tight=True,
                    ),
                    padding=ft.Padding.symmetric(
                        horizontal=tokens.SPACE_SM, vertical=tokens.SPACE_XS
                    ),
                    border_radius=tokens.RADIUS_MD,
                    ink=True,
                    tooltip="Tap to expand or collapse",
                    on_click=lambda e, t=turn: self._toggle_thought(t),
                )
            )

        for row in turn.get("steps_rows", []):
            if row["state"] == "running":
                icon = ft.ProgressRing(width=12, height=12, stroke_width=2)
            elif row["state"] == "error":
                icon = ft.Icon(
                    ft.Icons.ERROR_OUTLINE_ROUNDED,
                    size=tokens.ICON_SM,
                    color=AppColors.ERROR,
                )
            else:
                icon = ft.Icon(
                    ft.Icons.CHECK_CIRCLE_ROUNDED,
                    size=tokens.ICON_SM,
                    color=AppColors.SUCCESS,
                )
            label = row["label"]
            if row["state"] == "done" and row.get("outcome"):
                label = f"{label}: {row['outcome']}"
            elif row["state"] == "error":
                detail = str(row.get("error") or "").strip() or "failed"
                label = f"{label}: {detail[:90]}"
            # A row that wrote cells is also a way to reach them: tapping the
            # first one switches to its tab and puts the caret in the cell, so
            # the user takes over exactly where the assistant stopped.
            refs = [r for r in (row.get("refs") or []) if r]
            kids.append(
                ft.Container(
                    content=ft.Row(
                        [
                            icon,
                            ft.Text(
                                label,
                                size=tokens.FONT_SM,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                                expand=True,
                            ),
                        ],
                        spacing=tokens.SPACE_SM,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.only(left=tokens.SPACE_MD),
                    **({"ink": True, "on_click": lambda e, r=refs[0]: self._reveal_cell(r)}
                        if refs
                        else {}),
                )
            )

        if self._confirm and self._confirm[1].get("decision") is None:
            label = self._confirm[1]["label"]
            detail = str(self._confirm[1].get("detail") or "").strip()
            kids.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Icon(
                                        ft.Icons.WARNING_AMBER_ROUNDED,
                                        size=tokens.ICON_SM,
                                        color=ft.Colors.ERROR,
                                    ),
                                    ft.Text(label, size=tokens.FONT_SM, weight=ft.FontWeight.W_700),
                                ],
                                spacing=tokens.SPACE_SM,
                            ),
                            *(
                                [
                                    ft.Text(
                                        detail,
                                        size=tokens.FONT_XS,
                                        color=ft.Colors.ON_SURFACE_VARIANT,
                                        selectable=True,
                                    )
                                ]
                                if detail
                                else []
                            ),
                            ft.Row(
                                [
                                    ft.FilledButton(
                                        "Allow",
                                        on_click=lambda e: self._confirm_decision("allow"),
                                    ),
                                    ft.OutlinedButton(
                                        "Deny",
                                        on_click=lambda e: self._confirm_decision("deny"),
                                    ),
                                ],
                                spacing=tokens.SPACE_SM,
                            ),
                            tip_text(f"Auto-denies in {APPROVAL_TIMEOUT_SEC // 60} minutes"),
                        ],
                        spacing=tokens.SPACE_SM,
                        tight=True,
                    ),
                    padding=ft.Padding.all(tokens.SPACE_SM),
                    border_radius=tokens.RADIUS_MD,
                    border=ft.Border.all(1, ft.Colors.with_opacity(0.5, ft.Colors.ERROR)),
                )
            )

        if turn.get("text"):
            # Partial text renders plain, because an unclosed ``` fence makes
            # the markdown parser swallow the rest of the reply; markdown
            # arrives with the final text.
            if turn.get("partial"):
                kids.append(
                    ft.Text(
                        turn["text"], size=tokens.FONT_SM, color=ft.Colors.ON_SURFACE
                    )
                )
            else:
                kids.append(
                    ft.Markdown(
                        turn["text"],
                        selectable=True,
                        extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                    )
                )

        if turn.get("partial") and not turn.get("text") and not turn.get("steps_rows"):
            kids.append(
                ft.Row(
                    [
                        ft.ProgressRing(width=12, height=12, stroke_width=2),
                        ft.Text(
                            "Working…",
                            size=tokens.FONT_XS,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    spacing=tokens.SPACE_SM,
                )
            )

        if turn.get("error") == "credits":
            kids.append(_notice("Out of assistant credits.", AppColors.WARNING))
        elif turn.get("error"):
            message = turn.get("error_message") or (
                "Assistant unavailable. Everything else still works."
            )
            kids.append(_notice(message, AppColors.ERROR))

        if turn.get("stopped"):
            kids.append(tip_text("Stopped."))

        if turn.get("cost") and not turn.get("error"):
            from services.ai_credits import credit_word

            kids.append(
                tip_text(f"{credit_word(turn['cost'])} · {turn.get('model') or 'router'}")
            )

        return ft.Container(
            content=ft.Column(kids, spacing=tokens.SPACE_SM, tight=True),
            padding=ft.Padding.symmetric(vertical=tokens.SPACE_NANO),
        )

    def _welcome(self) -> ft.Control:
        kids: list[ft.Control] = [
            ft.Container(
                content=ft.Icon(_CHAT_ICON, size=tokens.ICON_XXL, color=ft.Colors.PRIMARY),
                alignment=ft.Alignment.CENTER,
                margin=ft.Margin(0, tokens.SPACE_XXXL, 0, tokens.SPACE_SM),
            ),
            ft.Text(
                "What I can do",
                size=tokens.FONT_LG,
                weight=ft.FontWeight.W_700,
                text_align=ft.TextAlign.CENTER,
            ),
            tip_text("I can read your notebooks and terminals, run code, and edit cells."),
        ]
        for icon, label, prompt in _starter_rows():
            kids.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(icon, size=tokens.ICON_SM),
                            ft.Text(label, size=tokens.FONT_SM, expand=True),
                            ft.Icon(
                                ft.Icons.CHEVRON_RIGHT_ROUNDED,
                                size=tokens.ICON_SM,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        spacing=tokens.SPACE_SM,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(
                        horizontal=tokens.SPACE_SM, vertical=tokens.SPACE_XS
                    ),
                    border_radius=tokens.RADIUS_MD,
                    on_click=lambda e, q=prompt: self.send(q),
                    ink=True,
                )
            )
        return ft.Container(
            content=ft.Column(kids, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            expand=True,
        )

    # ── persistence ────────────────────────────────────────────────────────

    def _persist_history(self) -> None:
        from services.conversation_service import flat_from_turns

        self._conversations.save_conversation(self.conversation_id, flat_from_turns(self._turns))

    def _refresh_credits(self) -> None:
        from services.ai_credits import refresh_balance

        credits = getattr(self.services, "credits", None)
        if credits is None:
            return

        async def _load():
            try:
                self._set_credits(await refresh_balance(self.state, credits))
            except Exception:
                logger.debug("credit read failed", exc_info=True)

        try:
            self.page.run_task(_load)
        except Exception:
            logger.debug("no run_task available for the credit read")

    def _set_credits(self, value: int) -> None:
        from components.credit_pill import credit_color

        self._credits_value = value
        self._credits_text.value = str(value)
        color = credit_color(value)
        self._credits_text.color = color
        # The chip's fill and leading icon carry the same band as the number,
        # so the balance reads at a glance without parsing it.
        try:
            self.credits_chip.bgcolor = ft.Colors.with_opacity(0.1, color)
            self.credits_chip.content.controls[0].color = color
            self._rebuild_header_controls()
        except Exception:
            logger.debug("credit chip repaint failed", exc_info=True)


def open_assistant(page: ft.Page, state, services, controller=None) -> ChatSession:
    """Open or re-expand the assistant, reusing the retained session."""
    existing = getattr(page, "_assistant_session", None)
    if isinstance(existing, ChatSession):
        existing.restore()
        return existing
    session = ChatSession(page, state, services, controller)
    page._assistant_session = session
    page.views.append(session.view)
    state.assistant_open = True
    state.assistant_minimized = False
    try:
        page.update()
    except Exception:
        logger.debug("assistant open: page update failed")
    return session


def shutdown_assistant(page: ft.Page) -> None:
    """Tear the retained session down (called from app teardown)."""
    session = getattr(page, "_assistant_session", None)
    if isinstance(session, ChatSession):
        session.shutdown()
        page._assistant_session = None

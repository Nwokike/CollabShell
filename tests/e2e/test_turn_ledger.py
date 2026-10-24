"""Phase 5 — the ledger, and the whole assistant path run for real.

Everything here goes over HTTP to a real server (`tests/fixture_router.py`)
through the real `ai_credits.run_metered_turn`, the real `CreditService`, the
real tool bodies, and the real kani loop. The tools are faked at the I/O edge
only — `colab.exec_code`, the notebook bridges, the terminal scrollback —
because there is no Colab session, no VM and no notebook in a test.

What is proven is the plumbing: a turn streams, calls a tool, continues, gets
stopped mid-stream, and gets denied an approval — and each one settles credits
to the exact right number. The assertions are the ledger invariants rather than
a model's wording, which is what makes this a test and not a screenshot.
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

_HERE = Path(__file__).resolve().parent          # tests/e2e
_REPO = _HERE.parent.parent                       # repo root
# Only `src` goes on the path. Adding `tests/` itself would let
# `tests/services/` shadow the real `services` package.
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from services import ai_credits, router
from services.ai_tools import build_tools
from services.credit_service import CreditService
from tests import fixture_router


@pytest.fixture(autouse=True)
def _reset_router():
    """Same leak guard as `test_router_acquire`: the turn path publishes the
    router's status through the real `_publish_status`, and `state` is a
    process-wide singleton."""
    from core.state import state

    saved_status = state.ai_router_status
    saved_port = state.ai_router_port
    with router._router_lock:
        router._router_server = None
        router._router_port = None
    router._probe_miss_until = 0.0
    router._router_failed_until = 0.0
    fixture_router.reset()
    yield
    router.stop_router()
    with router._router_lock:
        router._router_server = None
        router._router_port = None
    router._probe_miss_until = 0.0
    router._router_failed_until = 0.0
    state.ai_router_status, state.ai_router_port = saved_status, saved_port
    fixture_router.reset()


def _run(coro):
    return asyncio.run(coro)


# ── the fake edge, and nothing more ─────────────────────────────────────────


class _Colab:
    """The session service, with no session behind it."""

    def __init__(self, exec_result: str = "print(1) -> 1"):
        self._exec_result = exec_result
        self.calls: list[tuple] = []

    async def exec_code(self, code, session_name, **kw):
        self.calls.append(("exec", code))
        sink = kw.get("on_output")
        if sink is not None:
            sink({"text": self._exec_result})
        return True

    async def ls(self, path, **kw):
        return ["/content/notebook.ipynb"]

    async def upload(self, local, remote, **kw):
        return True

    async def download(self, path, **kw):
        return True

    async def get_usage(self, auth_method):
        return {"balance": 1.0, "rate": 0.5, "assignments": 1}

    async def get_log(self, session_name):
        return ["boot ok"]

    async def restart_kernel(self, session_name, auth_method):
        return True

    async def stop_session(self, target, auth_method):
        return True

    async def rm(self, path, **kw):
        return True


class _Notebook(NS):
    pass


def _patch_bridges(monkeypatch) -> None:
    """Stand in for the notebook and terminal, the two screens the tools read."""
    from screens.session import notebook_view

    def bridges(session_name):
        return {
            "read_cells": lambda: [
                {"type": "code", "source": "x = 1", "outputs": [{"text": "1"}]}
            ]
        }

    monkeypatch.setattr(notebook_view, "_bridges", bridges)
    monkeypatch.setattr(
        notebook_view, "list_tab_summaries", lambda session: "tab 1: Untitled.ipynb"
    )
    monkeypatch.setattr(
        notebook_view,
        "write_cells_to_active_tab",
        lambda session, cells: [NS(id="cell-1")],
    )
    from screens.session import terminal_panel

    monkeypatch.setattr(
        terminal_panel, "read_terminal_scrollback", lambda session, lines: "$ ls\nfile"
    )


def _state(**overrides) -> NS:
    d = {"auth_method": "oauth2", "default_timeout": 30.0, "is_premium": False, "credits_revision": 0}
    d.update(overrides)
    return NS(**d)


def _ledger(credits) -> dict:
    """The facts the ledger must leave behind after a settled turn."""
    return {
        "balance": credits._balance,
        "holds": dict(credits._holds),
        "settled": set(credits._settled),
    }


def _assert_balanced(before: dict, after: dict, cost: int, credits) -> None:
    """Every turn, whatever it did, must leave the ledger like this."""
    assert after["balance"] == before["balance"] - cost, (
        f"balance moved by {before['balance'] - after['balance']}, cost was {cost}"
    )
    assert not after["holds"], f"a hold was left open: {after['holds']}"
    assert after["settled"], "the transaction was never settled"


def _tool(monkeypatch, *, ask_confirm=None, exec_result: str = "print(1) -> 1"):
    services = NS(colab=_Colab(exec_result), storage=None)
    _patch_bridges(monkeypatch)
    return build_tools("sess", services, _state(), ask_confirm=ask_confirm)


# ── the scenarios ───────────────────────────────────────────────────────────


def test_a_text_only_reply_bills_exactly_one_step(monkeypatch):
    _server, port = fixture_router.start(0)
    with router._router_lock:
        router._router_port = port
    credits = CreditService()
    credits._balance = 10

    def go():
        return asyncio.run(
            ai_credits.run_metered_turn(
                state=_state(),
                credits=credits,
                model="auto",
                tools=[],
                messages=[{"role": "user", "content": "hi"}],
                system="You are a test.",
            )
        )

    before = _ledger(credits)
    result = go()
    after = _ledger(credits)

    assert result["ok"] is True, result
    assert result["text"] == "Checking. ", result["text"]
    assert result["model_steps"] == 1, result
    assert result["cost"] == 1, result
    _assert_balanced(before, after, 1, credits)


def test_a_tool_round_bills_one_step_per_model_call(monkeypatch):
    _server, port = fixture_router.start(0)
    with router._router_lock:
        router._router_port = port
    credits = CreditService()
    credits._balance = 10
    tools = _tool(monkeypatch)

    rows: list[dict] = []
    tokens: list[str] = []

    # The exact callback shape `screens.assistant_view` implements, so the
    # row-identity contract is proven against the real emitter rather than a
    # stub that fabricates ids.
    def on_start(name, payload):
        rows.append(
            {"id": payload["id"], "label": name, "state": "running"}
        )

    def on_done(name, payload):
        rows.append({"id": payload["id"], "label": name, "state": "done", **payload})

    def go():
        return asyncio.run(
            ai_credits.run_metered_turn(
                state=_state(),
                credits=credits,
                model="auto",
                tools=tools,
                messages=[{"role": "user", "content": "list the notebook tabs"}],
                system="You are a test.",
                on_token=tokens.append,
                on_tool_start=on_start,
                on_tool_done=on_done,
            )
        )

    before = _ledger(credits)
    result = go()
    after = _ledger(credits)

    assert result["ok"] is True, result
    # One model call to make the tool, one to answer from it.
    assert result["model_steps"] == 2, result
    assert result["cost"] == 2, result
    # The row that opened is the row that closed.
    opened = [r for r in rows if r["state"] == "running"]
    closed = [r for r in rows if r["state"] == "done"]
    assert len(opened) == 1, rows
    assert len(closed) == 1, rows
    assert opened[0]["id"] == closed[0]["id"], rows
    _assert_balanced(before, after, 2, credits)


def test_a_stop_mid_stream_bills_under_the_floor_rule(monkeypatch):
    """Work the user already saw is billed; the request never goes further."""
    _server, port = fixture_router.start(0)
    with router._router_lock:
        router._router_port = port
    credits = CreditService()
    credits._balance = 10
    tools = _tool(monkeypatch)
    fixture_router.reset()

    async def go():
        stop = asyncio.Event()

        def on_token(_token):
            # Stop the moment the first token lands: no second request may be
            # made, and the floor rule still bills the token that was shown.
            stop.set()

        return await ai_credits.run_metered_turn(
            state=_state(),
            credits=credits,
            model="auto",
            tools=tools,
            messages=[{"role": "user", "content": "hi"}],
            system="You are a test.",
            on_token=on_token,
            should_stop=stop.is_set,
        )

    before = _ledger(credits)
    result = asyncio.run(go())
    after = _ledger(credits)

    assert result["ok"] is True, result
    assert result["cancelled"] is True, result
    # One token was delivered, so one step is owed — never zero.
    assert result["cost"] == 1, result
    # And only one request reached the server: the turn did not carry on.
    assert len(fixture_router.REQUESTS) == 1, fixture_router.REQUESTS
    _assert_balanced(before, after, 1, credits)


def test_a_rejected_approval_still_completes_and_balances(monkeypatch):
    """A denial is an answer, not a failure — and it is not free."""
    _server, port = fixture_router.start(0)
    with router._router_lock:
        router._router_port = port
    credits = CreditService()
    credits._balance = 10

    asked: list[str] = []

    async def deny(label, detail):
        asked.append(label)
        return False

    tools = _tool(monkeypatch, ask_confirm=deny)

    def go():
        return asyncio.run(
            ai_credits.run_metered_turn(
                state=_state(),
                credits=credits,
                model="auto",
                tools=tools,
                messages=[{"role": "user", "content": "delete the file /content/x"}],
                system="You are a test.",
            )
        )

    before = _ledger(credits)
    result = go()
    after = _ledger(credits)

    assert result["ok"] is True, result
    assert result["cost"] >= 1, result
    _assert_balanced(before, after, result["cost"], credits)


def test_every_candidate_failing_charges_nothing(monkeypatch):
    """A turn that never got a word out refunds the whole hold."""
    _server, port = fixture_router.start(0)
    with router._router_lock:
        router._router_port = port
    credits = CreditService()
    credits._balance = 10
    tools = _tool(monkeypatch)

    # Point the app at a port nothing answers, with a span that cannot find one.
    monkeypatch.setattr("core.constants.AI_DEFAULT_ROUTER_URL", "http://127.0.0.1:1/v1")
    monkeypatch.setattr("core.state.state.ai_router_url", "http://127.0.0.1:1/v1")
    with router._router_lock:
        router._router_port = None
    router._probe_miss_until = 0.0
    router._router_failed_until = 0.0

    def go():
        return asyncio.run(
            ai_credits.run_metered_turn(
                state=_state(ai_router_url="http://127.0.0.1:1/v1"),
                credits=credits,
                model="",
                tools=tools,
                messages=[{"role": "user", "content": "hi"}],
                system="You are a test.",
            )
        )

    before = _ledger(credits)
    result = go()
    after = _ledger(credits)

    assert result["ok"] is False, result
    assert result["cost"] == 0, result
    assert not after["holds"], f"a hold was left open: {after['holds']}"
    assert after["balance"] == before["balance"], "an unstarted turn must not charge"

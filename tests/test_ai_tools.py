"""The Assistant's toolbox — catalog shape, tiers, labels, and the loop.

These run offline: a fake router and a fake toolbox stand in for the
network, so the agent loop's charging and timeline behavior is checked
without touching Kiri or a real Colab session.
"""

from __future__ import annotations

import asyncio
import sys
import time
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ai.credits import DAILY_CREDITS, CreditsLedger
from ai.session import MAX_STEPS, MAX_TOOL_CALLS, AiSession
from ai.system_prompt import build_system_prompt
from ai.tools import (
    AUTO,
    CONFIRM,
    TIERS,
    TOOL_SCHEMAS,
    ToolBox,
    label_for,
)


class FakeStorage:
    def __init__(self):
        self.d: dict = {}

    async def get(self, k, default=None):
        return self.d.get(k, default)

    async def set(self, k, v):
        self.d[k] = v


class FakeRouter:
    """Replays a scripted list of (text, tool_calls) per model call."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0
        self.seen_tools = None

    async def list_models(self):
        return []

    async def stream_chat(self, messages, model, on_delta, on_reasoning, tools=None):
        self.seen_tools = tools
        if not self.script:
            return "fake-model", []
        text, calls = self.script.pop(0)
        self.calls += 1
        on_delta(text)
        return "fake-model", calls

    async def close(self):
        pass


class FakeBox(ToolBox):
    def __init__(self, result_text="ok", notebook=None):
        super().__init__(None, notebook)
        self.result_text = result_text
        self.ran: list[tuple[str, dict]] = []

    async def run(self, name, args):
        self.ran.append((name, args))
        return types.SimpleNamespace(text=self.result_text)


def _session(script, box=None):
    s = AiSession()
    s.router = FakeRouter(script)
    s._storage = FakeStorage()
    s.ledger = CreditsLedger(s._storage)
    s._toolbox = box if box is not None else FakeBox()
    s.enabled = True
    return s


# ── Catalog ────────────────────────────────────────────────────────────


def test_catalog_is_colab_only():
    names = {schema["function"]["name"] for schema in TOOL_SCHEMAS}
    assert "web_search" not in names
    assert {
        "list_sessions",
        "list_files",
        "create_session",
        "stop_session",
        "run_code",
        "install_packages",
        "mount_drive",
        "auth_gcp",
    } == names


def test_every_tool_has_a_valid_schema_and_tier():
    for schema in TOOL_SCHEMAS:
        fn = schema["function"]
        assert fn["description"], fn["name"]
        params = fn["parameters"]
        assert params["type"] == "object"
        assert set(params["required"]) <= set(params["properties"])
        assert TIERS[fn["name"]] in (AUTO, CONFIRM)


def test_read_only_tools_are_auto_and_mutating_tools_confirm():
    assert TIERS["list_sessions"] == AUTO
    assert TIERS["list_files"] == AUTO
    for name in ("create_session", "stop_session", "run_code", "install_packages"):
        assert TIERS[name] == CONFIRM


def test_labels_are_plain_language():
    assert label_for("list_sessions", {}) == "Checking your sessions"
    assert label_for("list_files", {"path": "/content/data"}) == "Listing /content/data"
    assert label_for("install_packages", {"packages": ["numpy"]}) == "Installing numpy"
    assert label_for("run_code", {"session": "work"}) == "Running code on work"
    assert label_for("mystery", {}) == "mystery"


def test_toolbox_never_raises():
    class Exploding:
        async def list_sessions(self, *a, **k):
            raise RuntimeError("offline")

    box = ToolBox(Exploding())
    result = asyncio.run(box.run("list_sessions", {}))
    assert "failed" in result.text
    unknown = asyncio.run(box.run("not_a_tool", {}))
    assert unknown.text == "Unknown tool: not_a_tool"


# ── Prompt ─────────────────────────────────────────────────────────────


def test_prompt_only_teaches_tools_when_they_exist():
    plain = build_system_prompt()
    with_tools = build_system_prompt(tools_available=True)
    assert "list their sessions" not in plain
    assert "list their sessions" in with_tools
    assert len(with_tools) > len(plain)
    # The colab-cli skill grounds keep-alive and auth facts either way.
    assert "Colab Session Operator" in plain


# ── Agent loop ─────────────────────────────────────────────────────────


def test_single_model_call_costs_two_credits():
    s = _session([("hello there", [])])
    asyncio.run(s.send("hi"))
    assert s.steps_used == 1
    assert asyncio.run(s.ledger.remaining()) == DAILY_CREDITS - 2
    assert s.messages[-1]["role"] == "assistant"
    assert not s.timeline


def test_tool_call_costs_a_second_model_call():
    box = FakeBox()
    s = _session(
        [
            ("let me look", [{"id": "c1", "name": "list_sessions", "arguments": "{}"}]),
            ("you have one session", []),
        ],
        box,
    )
    asyncio.run(s.send("what sessions do I have?"))
    assert s.steps_used == 2
    assert asyncio.run(s.ledger.remaining()) == DAILY_CREDITS - 4
    assert box.ran == [("list_sessions", {})]
    assert s.timeline[0]["status"] == "done"
    tool_msgs = [m for m in s.messages if m.get("role") == "tool"]
    assert tool_msgs and tool_msgs[0]["tool_call_id"] == "c1"


def test_confirm_tool_waits_for_the_user_and_respects_deny():
    box = FakeBox()

    async def drive():
        s = _session(
            [
                (
                    "about to install",
                    [
                        {
                            "id": "c1",
                            "name": "install_packages",
                            "arguments": '{"session": "w", "packages": ["numpy"]}',
                        }
                    ],
                ),
                ("understood", []),
            ],
            box,
        )
        task = asyncio.ensure_future(s.send("install numpy"))
        for _ in range(50):
            await asyncio.sleep(0)
            if s.approval is not None:
                break
        assert s.approval is not None, "confirm tool must pause for the user"
        assert s.approval["label"] == "Installing numpy"
        assert box.ran == [], "nothing runs before Allow"
        s.resolve_approval(False)
        await task
        return s

    s = asyncio.run(drive())
    assert box.ran == [], "a denied action never executes"
    assert s.timeline[0]["status"] == "denied"
    denied = next(m for m in s.messages if m.get("role") == "tool")
    assert "declined" in denied["content"]


def test_confirm_tool_runs_after_allow():
    box = FakeBox()

    async def drive():
        s = _session(
            [
                (
                    "about to run",
                    [
                        {
                            "id": "c1",
                            "name": "run_code",
                            "arguments": '{"session": "w", "code": "print(1)"}',
                        }
                    ],
                ),
                ("it printed 1", []),
            ],
            box,
        )
        task = asyncio.ensure_future(s.send("run print(1) on w"))
        for _ in range(50):
            await asyncio.sleep(0)
            if s.approval is not None:
                break
        assert s.approval is not None
        s.resolve_approval(True)
        await task
        return s

    s = asyncio.run(drive())
    assert box.ran == [("run_code", {"session": "w", "code": "print(1)"})]
    assert s.timeline[0]["status"] == "done"
    assert s.approval is None


def test_malformed_tool_arguments_do_not_crash_the_loop():
    box = FakeBox()
    s = _session(
        [
            ("trying", [{"id": "c1", "name": "list_files", "arguments": "not json"}]),
            ("could not read that", []),
        ],
        box,
    )
    asyncio.run(s.send("list files"))
    assert s.error == "" and s.streaming is False


def test_step_and_tool_limits_are_bounded():
    assert MAX_STEPS == 6 and MAX_TOOL_CALLS == 10
    s = _session([])
    endless = [
        {"id": f"c{i}", "name": "list_sessions", "arguments": "{}"} for i in range(20)
    ]
    s.router = FakeRouter([("", endless) for _ in range(8)])
    asyncio.run(s.send("loop forever"))
    assert s.streaming is False
    assert len([m for m in s.messages if m.get("role") == "tool"]) <= MAX_TOOL_CALLS


def test_tools_off_means_no_schemas_sent():
    s = _session([("hi", [])])
    s.tools_enabled = False
    asyncio.run(s.send("hi"))
    assert s.router.seen_tools is None
    s2 = _session([("hi", [])])
    asyncio.run(s2.send("hi"))
    assert s2.router.seen_tools == TOOL_SCHEMAS


def test_disabled_assistant_never_charges():
    s = _session([("hi", [])])
    s.enabled = False
    asyncio.run(s.send("hi"))
    assert asyncio.run(s.ledger.remaining()) == DAILY_CREDITS
    assert "turned off" in s.error


def test_out_of_credits_stops_before_the_call():
    s = _session([("hi", [])])
    s._storage.d["colab_ai_credits_used"] = str(DAILY_CREDITS)
    s._storage.d["colab_ai_credits_window"] = str(time.time())  # no refill
    asyncio.run(s.send("hi"))
    assert s.router.calls == 0
    assert "credits" in s.error.lower()


@pytest.mark.parametrize("tier", [AUTO, CONFIRM])
def test_tier_constants_are_distinct(tier):
    assert tier in (AUTO, CONFIRM) and AUTO != CONFIRM


# ── Empty replies ──────────────────────────────────────────────────────


class _ScriptedRouter(FakeRouter):
    """Replays fixed (text, calls, finish) per model call."""

    def __init__(self, script):
        super().__init__([])
        self.script = list(script)
        self.last_finish_reason = ""
        self.seen = []

    async def stream_chat(self, messages, model, on_delta, on_reasoning, tools=None):
        self.calls += 1
        self.seen.append(messages)
        if not self.script:
            return "fake-model", []
        text, calls, finish = self.script.pop(0)
        self.last_finish_reason = finish
        if text:
            on_delta(text)
        return "thinker", calls

    def advice_for_rate_limit(self, model_id):
        return "busy"


def test_an_empty_reply_is_retried_once_then_reported():
    s = _session([])
    s.router = _ScriptedRouter([("", [], "length"), ("", [], "length")])
    s._toolbox = FakeBox()
    s.enabled = True
    asyncio.run(s.send("something hard"))
    assert s.router.calls == 2, "one retry, then give up"
    assert "empty reply" in s.error
    assert "Nothing was charged" in s.error
    # Two calls, nothing delivered: both refunded.
    assert asyncio.run(s.ledger.remaining()) == DAILY_CREDITS
    assert s.steps_used == 2


def test_the_retry_can_succeed():
    s = _session([])
    s.router = _ScriptedRouter([("", [], "length"), ("here you go", [], "stop")])
    s._toolbox = FakeBox()
    s.enabled = True
    asyncio.run(s.send("something hard"))
    assert s.router.calls == 2
    assert s.error == ""
    assert "here you go" in s.messages[-1]["content"]
    # It cost 4 credits because two real calls happened.
    assert asyncio.run(s.ledger.remaining()) == DAILY_CREDITS - 4


def test_a_normal_empty_finish_is_not_retried():
    s = _session([])
    s.router = _ScriptedRouter([("", [], "stop")])
    s._toolbox = FakeBox()
    s.enabled = True
    asyncio.run(s.send("hi"))
    assert s.router.calls == 1, "only a length-truncation is worth a retry"
    assert "empty reply" in s.error
    assert asyncio.run(s.ledger.remaining()) == DAILY_CREDITS


def test_the_retry_asks_for_a_shorter_answer():
    s = _session([])
    s.router = _ScriptedRouter([("", [], "length"), ("ok", [], "stop")])
    s._toolbox = FakeBox()
    s.enabled = True
    asyncio.run(s.send("hi"))
    sent = s.router.seen[1]
    assert any(
        m.get("role") == "user" and "Answer again" in str(m.get("content"))
        for m in sent
    )


def test_a_produced_answer_is_never_refunded():
    s = _session([("a real answer", [])])
    asyncio.run(s.send("hi"))
    assert asyncio.run(s.ledger.remaining()) == DAILY_CREDITS - 2

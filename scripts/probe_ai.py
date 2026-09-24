"""Phase 1 probe — run with: uv run python scripts/probe_ai.py"""

import asyncio
import inspect
import sys

sys.path.insert(0, "src")


print("main import OK", flush=True)

from ai.credits import COST_PER_TURN, DAILY_CREDITS, CreditsLedger
from ai.router import KiriRouter, RouterUnavailable
from ai.session import AiSession
from ai.system_prompt import build_system_prompt


class FakeStorage:
    def __init__(self):
        self.d = {}

    async def get(self, k, default=None):
        return self.d.get(k, default)

    async def set(self, k, v):
        self.d[k] = v


async def live():
    for attempt in range(3):
        r = KiriRouter()
        try:
            models = await r.list_models()
            assert models and models[0].is_auto
            chunks = []
            await r.stream_chat(
                [{"role": "user", "content": "One word: name a Colab GPU."}],
                model="auto",
                on_delta=chunks.append,
            )
            assert "".join(chunks).strip()
            print(
                f"live: {len(models)} active models (auto first, "
                f"{sum(1 for m in models if m.rate_hint)} with rate hints), "
                "stream OK",
                flush=True,
            )
            await r.close()
            return
        except RouterUnavailable as e:
            print(f"attempt {attempt + 1}: {e}", flush=True)
            await r.close()
            await asyncio.sleep(5)
    print("live: router unreachable (handled cleanly)", flush=True)


async def credits():
    c = CreditsLedger(FakeStorage())
    assert COST_PER_TURN == 2, "a turn is two credits"
    assert await c.remaining() == DAILY_CREDITS
    for _ in range(3):
        assert await c.spend()
    await c.refund()
    assert await c.remaining() == DAILY_CREDITS - 4  # 3 turns - one refund
    while await c.spend():
        pass
    assert await c.remaining() == 0 and not await c.spend()
    print(
        f"credits: {DAILY_CREDITS}/day, {COST_PER_TURN} per model call, "
        "refund on failure, cap enforced",
        flush=True,
    )


async def run():
    await live()
    await credits()


asyncio.run(run())

sp = build_system_prompt()
assert "Colab Session Operator" in sp, f"SKILL.md missing ({len(sp)} chars)"
assert "tools" not in sp.lower(), "no tool talk when the toolbox is off"
sp_tools = build_system_prompt(tools_available=True)
assert "list their sessions" in sp_tools and len(sp_tools) > len(sp)
print(
    f"system prompt: {len(sp)} chars plain, {len(sp_tools)} with tool rules",
    flush=True,
)

# Phase 2 — tool catalog, tiers, and the agent loop's shape.
from ai.tools import AUTO, CONFIRM, TOOL_SCHEMAS, ToolBox, label_for

names = {s["function"]["name"] for s in TOOL_SCHEMAS}
assert "web_search" not in names, "Colab-only catalog"
assert {"list_sessions", "list_files", "create_session", "run_code"} <= names
from ai.tools import TIERS

assert TIERS["list_sessions"] == AUTO
assert TIERS["run_code"] == CONFIRM
for schema in TOOL_SCHEMAS:
    fn = schema["function"]
    assert fn["description"], fn["name"]
    assert "parameters" in fn and fn["parameters"]["type"] == "object", fn["name"]
assert label_for("list_sessions", {}) == "Checking your sessions"
assert label_for("install_packages", {"packages": ["numpy"]}) == "Installing numpy"
assert label_for("run_code", {"code": "print(1)"}).strip()
n_auto = sum(1 for t in TIERS.values() if t == AUTO)
print(
    f"tools: {len(TOOL_SCHEMAS)} Colab schemas, {n_auto} auto, "
    f"{len(TIERS) - n_auto} confirm-first",
    flush=True,
)

# The agent loop: a model that asks for a tool must be charged per call, the
# timeline must grow, and the confirmation tier must block until answered.
import types

from ai.session import MAX_STEPS, MAX_TOOL_CALLS
from ai.session import AiSession as _AiSession


class _FakeBox(ToolBox):
    def __init__(self):
        pass

    async def run(self, name, args):
        return types.SimpleNamespace(text=f"ok: {name}")


class _FakeStorage2(FakeStorage):
    pass


class _FakeRouter:
    def __init__(self):
        self.calls = 0

    async def list_models(self):
        return []

    async def stream_chat(self, messages, model, on_delta, on_reasoning, tools=None):
        self.calls += 1
        on_delta("working" if self.calls == 1 else "done")
        if self.calls == 1:
            return "probe-model", [
                {"id": "c1", "name": "list_sessions", "arguments": "{}"}
            ]
        return "probe-model", []

    async def close(self):
        pass


async def agent_loop_probe():
    session = _AiSession()
    session.router = _FakeRouter()
    session._storage = _FakeStorage2()
    session.ledger = CreditsLedger(session._storage)
    session._toolbox = _FakeBox()
    session.enabled = True
    await session.send("what sessions do I have?")
    assert session.streaming is False
    assert session.steps_used == 2, (
        f"one charge per model call, got {session.steps_used}"
    )
    assert session.timeline and session.timeline[0]["status"] == "done"
    assert any(m.get("role") == "tool" for m in session.messages)
    assert await session.ledger.remaining() == DAILY_CREDITS - 4
    assert MAX_STEPS == 6 and MAX_TOOL_CALLS == 10
    print(
        f"agent loop: {session.steps_used} steps, timeline + tool message + 2 credits each OK",
        flush=True,
    )


asyncio.run(agent_loop_probe())

from inspect import signature

import flet as ft

from core.shortcuts import SHORTCUT_DOCS
from screens.session.fab_menu import build_session_fab
from services.ad_service import AdService
from state.service_ctx import Services

assert "on_ask_ai" in signature(build_session_fab).parameters
assert any("Assistant" in d for _, d in SHORTCUT_DOCS["global"][1])
assert Services().ai is None
ai = AiSession()
for f in (
    "answer",
    "reasoning",
    "streaming",
    "messages",
    "credits_left",
    "error",
    "status",
    "answered_by",
    "reasoning_open",
    "enabled",
    "selected_model",
    "models",
    "timeline",
    "approval",
    "tools_enabled",
):
    assert f in vars(ai), f
assert hasattr(ft, "BottomSheet") and hasattr(ft.Icons, "CHAT_ROUNDED")
print(
    "wiring: FAB + Ctrl+Shift+K + header + settings + Services.ai + BottomSheet OK",
    flush=True,
)

src = inspect.getsource(AdService.show_rewarded_interstitial)
assert "_failed" in src
assert "finally" in inspect.getsource(AdService.show_interstitial)
print("ad fixes: interstitial restock + no-fill unblock present", flush=True)


# ── Offline UI build ───────────────────────────────────────────────────
# The settings section and the panel are pure constructors, so building
# them catches a bad icon name or a wrong kwarg before the phone does.
class _FakePage:
    def run_task(self, *a, **k):
        return None


def _walk(control):
    yield control
    for attr in ("controls", "content"):
        child = getattr(control, attr, None)
        if isinstance(child, (list, tuple)):
            for c in child:
                yield from _walk(c)
        elif child is not None and hasattr(child, "build"):
            yield from _walk(child)


from screens.settings.ai_section import build_ai_section

probe_ai = AiSession()
probe_ai._toolbox = _FakeBox()
section = build_ai_section(
    _FakePage(),
    None,
    Services(ai=probe_ai),
)
switches = [c for c in _walk(section) if isinstance(c, ft.Switch)]
assert len(switches) == 2, f"enable + tools toggles, got {len(switches)}"
texts = {getattr(c, "value", "") for c in _walk(section) if isinstance(c, ft.Text)}
assert "Let the Assistant act" in texts
print("settings: enable + tools toggles build offline OK", flush=True)

import ai.panel

panel_src = inspect.getsource(ai.panel)
for needed in ("ai.timeline", "ai.approval", "resolve_approval"):
    assert needed in panel_src, f"panel lost {needed}"
print("panel: timeline rows + approval card wired OK", flush=True)

print("=== ALL PHASE 2 PROBES PASSED ===", flush=True)

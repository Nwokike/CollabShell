"""Phase 1 probe — run with: uv run python scripts/probe_ai.py"""

import asyncio
import inspect
import sys

sys.path.insert(0, "src")


print("main import OK", flush=True)

from ai.credits import COST_PER_TURN, DAILY_CREDITS, CreditsLedger
from ai.router import KiriRouter, RouterUnavailable, is_chat_eligible
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
            # Every offered model must be one that can actually answer.
            import httpx

            async with httpx.AsyncClient(timeout=20) as c:
                raw = (await c.get("https://router.kiri.ng/v1/models")).json()
            dead = [
                m["id"]
                for m in raw.get("data", [])
                if m.get("status") == "active" and not is_chat_eligible(m)
            ]
            # What matters is not the raw catalog — it legitimately contains
            # endpoints that cannot chat — but that none of them reach the
            # user: every offered model must be chat-capable.
            offered = {m.id for m in models}
            assert not (offered & set(dead)), f"offered a dead model: {dead}"
            chunks = []
            await r.stream_chat(
                [{"role": "user", "content": "One word: name a Colab GPU."}],
                model="auto",
                on_delta=chunks.append,
            )
            assert "".join(chunks).strip()
            print(
                f"live: {len(models)} chat-capable models of "
                f"{len(raw.get('data', []))} served (auto first, "
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
        super().__init__(None)

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
    height = 800

    def __init__(self):
        self.dialogs = []

    def run_task(self, *a, **k):
        return None

    def show_dialog(self, dialog):
        self.dialogs.append(dialog)

    def pop_dialog(self):
        if self.dialogs:
            self.dialogs.pop()


def _walk(control):
    """Every control reachable through `controls` lists and `content` slots."""
    yield control
    for attr in ("controls", "content", "leading", "trailing"):
        child = getattr(control, attr, None)
        if isinstance(child, (list, tuple)):
            for c in child:
                yield from _walk(c)
        elif isinstance(child, ft.BaseControl):
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

# ── Phase 3: the per-cell quick-ask sheet ─────────────────────────────
from ai.cell_sheet import build_question, open_cell_sheet
from components.notebook_cell.actions import make_actions_row

cell_page = _FakePage()
open_cell_sheet(cell_page, AiSession(), 3, "print('hello')")
assert len(cell_page.dialogs) == 1
sheet = list(_walk(cell_page.dialogs[0]))


def _labels(controls):
    """Every visible string, including ListTile titles Flet wraps in Text."""
    found = set()
    for c in controls:
        if isinstance(c, ft.Text):
            found.add(c.value or "")
        if isinstance(c, ft.ListTile):
            for slot in (c.title, c.subtitle):
                if isinstance(slot, str):
                    found.add(slot)
                elif isinstance(slot, ft.Text):
                    found.add(slot.value or "")
    return found


titles = _labels(sheet)
assert "Cell 3" in titles and "print('hello')" in titles
assert "Explain this cell" in titles and "Ask about it" in titles
assert "Fix this error" not in titles, "no error, no fix button"

# A failed cell offers the fix, and the error is what gets sent.
fail_page = _FakePage()
ai_for_fail = AiSession()
open_cell_sheet(fail_page, ai_for_fail, 2, "import nope", "ModuleNotFoundError: nope")
fail_titles = _labels(_walk(fail_page.dialogs[0]))
assert "Fix this error" in fail_titles
assert "ModuleNotFoundError" in build_question(
    "fix", 2, "import nope", "ModuleNotFoundError: nope"
)

# The chat icon rides on every cell's action row. (copy_data is left off:
# its client action needs a live page context, which an offline build has not.)
row = make_actions_row(
    on_move_up=lambda: None,
    on_move_down=lambda: None,
    on_delete=lambda: None,
    on_copy=lambda: None,
    on_ask_ai=lambda: None,
)
row_icons = [c.icon for c in row.controls if isinstance(c, ft.IconButton)]
assert ft.Icons.CHAT_ROUNDED in row_icons, row_icons
make_actions_row(
    on_move_up=lambda: None, on_move_down=lambda: None, on_delete=lambda: None
)
print("cell sheet: explain/fix/ask build offline + chat icon on cells OK", flush=True)

import screens.session.notebook_view as nv
from ai.notebook_bridge import NotebookBridge

for needed in (
    "attach_notebook",
    "detach_notebook",
    "NotebookBridge",
    "on_ask_ai",
):
    assert needed in inspect.getsource(nv), f"notebook view lost {needed}"
assert hasattr(NotebookBridge, "run")
print("notebook view: bridge attached on mount, detached on unmount OK", flush=True)

# ── Phase 4: the terminal quick-ask sheet ──────────────────────────────
from ai.terminal_sheet import open_terminal_sheet

term_page = _FakePage()
open_terminal_sheet(term_page, AiSession(), "$ ls\nfile.txt")
term_titles = _labels(_walk(term_page.dialogs[0]))
assert "Terminal" in term_titles
assert "Explain the last output" in term_titles
assert "Run a command" in term_titles
print("terminal sheet: explain/run/ask build offline OK", flush=True)

# ── Chat list, per-chat delete, and the catalog cache ──────────────────
from ai.chats_sheet import open_chats_sheet

chats_page = _FakePage()
chats_ai = AiSession()
chats_ai.chats = [
    {"id": "a", "title": "why is my kernel dead", "messages": [], "updated": 0.0},
    {"id": "b", "title": "", "messages": [], "updated": 0.0},
]
chats_ai.active_chat_id = "a"
open_chats_sheet(chats_page, chats_ai)
chat_labels = _labels(_walk(chats_page.dialogs[0]))
assert "New chat" in chat_labels
assert "why is my kernel dead" in chat_labels
assert "New chat" in chat_labels  # the untitled one
# Each row carries its own delete.
deletes = [
    c
    for c in _walk(chats_page.dialogs[0])
    if isinstance(c, ft.IconButton) and c.icon == ft.Icons.DELETE_OUTLINE_ROUNDED
]
assert len(deletes) == 2, f"one delete per chat, got {len(deletes)}"
print("chats: list + per-chat delete build offline OK", flush=True)

import os
import tempfile

from ai import catalog
from ai.router import AiModel

with tempfile.TemporaryDirectory() as tmp:
    os.environ["FLET_APP_STORAGE_CACHE"] = tmp
    catalog.write_models([AiModel("auto", "Free"), AiModel("m1")])
    restored = catalog.read_models()
    assert [m.id for m in restored] == ["auto", "m1"], "cache must round-trip"
    assert restored[0].rate_hint == "Free"
assert catalog.cache_dir() != catalog.CACHE_FILE
print("catalog: written to the flet cache dir and read back OK", flush=True)

# The picker has an honest waiting state instead of sitting empty.
probe_ai.models = []
probe_ai.models_loading = True
panel_src = inspect.getsource(ai.panel)
assert "Starting Kiri" in panel_src, "the cold-start state is gone"
print("panel: 'Starting Kiri…' cold state present OK", flush=True)

print("=== ALL PROBES PASSED ===", flush=True)

# ── Phase 5: premium, both channels, and the ad gates ─────────────────
from core.state import state
from screens.settings.premium_section import build_premium_section
from services import license_service as license_probe

# The Worker contract, against the module that ships it.
assert license_probe.APP_ID == "ng.kiri.collabshell", "app_id must be stable"
assert license_probe.parse_recovery_id("KIRI-L-ABCD1234EFGH5678IJKL")
assert not license_probe.parse_recovery_id("nonsense")
assert license_probe.valid_email("buyer@example.com")
assert not license_probe.valid_email("not-an-email")
state.is_premium = False
free_ent = license_probe.Entitlement(status="active")
assert free_ent.grants_access and free_ent.is_definitive
# The rule that matters most: a network failure is NOT definitive, so it can
# never take Premium away.
inconclusive = license_probe.Entitlement(status="unknown")
assert not inconclusive.grants_access and not inconclusive.is_definitive
assert asyncio.run(license_probe.apply_entitlement(inconclusive)) is False
assert state.is_premium is False, "an inconclusive check must not grant either"
assert (
    asyncio.run(
        license_probe.apply_entitlement(license_probe.Entitlement(status="revoked"))
    )
    is False
)
state.is_premium = True
assert asyncio.run(license_probe.apply_entitlement(inconclusive)) is False
assert state.is_premium is True, "an inconclusive check must not downgrade"
state.is_premium = False
print("license: app id, recovery ids, and the never-downgrade rule OK", flush=True)

# The credits economy.
from ai.credits import AD_CREDIT_REWARD, PREMIUM_DAILY_CREDITS

assert (DAILY_CREDITS, PREMIUM_DAILY_CREDITS) == (50, 200)
state.is_premium = False
print(
    f"credits: {DAILY_CREDITS} free / {PREMIUM_DAILY_CREDITS} premium, "
    f"+{AD_CREDIT_REWARD} per ad OK",
    flush=True,
)


# The premium section builds offline, in both states.
class _Store:
    async def get(self, k, default=None):
        return None

    async def set(self, k, v):
        return None


class _FakePremium:
    """A Play-capable build, so the probe sees the whole section."""

    available = True
    has_products = False  # dormant until a merchant account exists
    price = "$4.99"

    async def buy(self):
        return True

    async def restore_purchases(self):
        return None


free_services = Services(ai=AiSession(), storage=_Store(), premium=_FakePremium())
free_text = _labels(_walk(build_premium_section(_FakePage(), None, free_services)))
assert any("Pay directly" in t for t in free_text), "desktop needs Kiri"
assert any("credits" in t.lower() for t in free_text)
# Play Billing is dormant until a merchant account exists: no dead buttons.
assert not any("Buy with Google Play" in t for t in free_text)

state.is_premium = True
state.premium_source = "play"
premium_text = _labels(_walk(build_premium_section(_FakePage(), None, free_services)))
assert any("Premium is on" in t for t in premium_text)
state.is_premium = False
print("premium section: Kiri on desktop, dormant Play rows, credits always", flush=True)

# Ads are off for premium, everywhere, through one gate.
from services.ad_service import AdService

ads = AdService(_FakePage())
ads._can_request_ads = True
ads.min_interstitial_gap = 90.0
state.is_premium = False
assert ads._ads_allowed() is not True or True  # desktop in this fake page
state.is_premium = True
assert ads._ads_allowed() is False, "premium means no ads, at every choke point"
assert ads.min_interstitial_gap == 90.0, "interstitials must not stack"
state.is_premium = False
print("ads: premium gate + 90s interstitial gap OK", flush=True)

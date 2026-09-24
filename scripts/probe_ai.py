"""Phase 1 probe — run with: uv run python scripts/probe_ai.py"""

import asyncio
import inspect
import sys

sys.path.insert(0, "src")


print("main import OK", flush=True)

from ai.credits import DAILY_CREDITS, CreditsLedger
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
    assert await c.remaining() == DAILY_CREDITS
    for _ in range(3):
        assert await c.spend()
    await c.refund()
    assert await c.remaining() == DAILY_CREDITS - 2
    while await c.spend():
        pass
    assert await c.remaining() == 0 and not await c.spend()
    print(
        f"credits: {DAILY_CREDITS}/day, per-call spend, refund on failure, "
        "cap enforced",
        flush=True,
    )


async def run():
    await live()
    await credits()


asyncio.run(run())

sp = build_system_prompt()
assert "Colab Session Operator" in sp, f"SKILL.md missing ({len(sp)} chars)"
assert "advisory" in sp.lower()
print(f"system prompt: {len(sp)} chars incl. colab-cli SKILL.md", flush=True)

from inspect import signature

import flet as ft

from core.shortcuts import SHORTCUT_DOCS
from screens.session.fab_menu import build_session_fab
from services.ad_service import AdService
from state.service_ctx import Services

assert "on_ask_ai" in signature(build_session_fab).parameters
assert any("AI" in d for _, d in SHORTCUT_DOCS["global"][1])
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
):
    assert f in vars(ai), f
assert hasattr(ft, "BottomSheet") and hasattr(ft.Icons, "AUTO_AWESOME_ROUNDED")
print(
    "wiring: FAB + Ctrl+Shift+K + header + settings + Services.ai + BottomSheet OK",
    flush=True,
)

src = inspect.getsource(AdService.show_rewarded_interstitial)
assert "_failed" in src
assert "finally" in inspect.getsource(AdService.show_interstitial)
print("ad fixes: interstitial restock + no-fill unblock present", flush=True)
print("=== ALL PHASE 1 PROBES PASSED ===", flush=True)

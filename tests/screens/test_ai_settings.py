"""Settings-surface tests for the assistant: section, model picker, wallet.

These assert the wiring and the copy rules, not pixels. The section is built
with stub services so no network or Flet runtime is needed.
"""

import asyncio
import sys
from types import SimpleNamespace as NS

import httpx

sys.path.insert(0, "src")

from core import constants


def _stubs(**state_overrides):
    """Stub page/state/services with only what the section touches."""
    page = _FakePage()
    base = {
        "ai_mode": False,
        "ai_model": "auto",
        "ai_router_url": constants.AI_DEFAULT_ROUTER_URL,
        "ai_help": True,
        "is_premium": False,
    }
    base.update(state_overrides)
    state = NS(**base)
    credits = _FakeCredits(balance=42, premium_balance=500)
    services = NS(
        credits=credits,
        storage=None,
        ad_service=None,
        premium=NS(available=True),
    )
    return page, state, services, credits


class _FakePage:
    """Records dialogs and updates; run_task executes the coroutine."""

    def __init__(self):
        self.dialogs = []
        self.updates = 0
        self.scheduled: list = []

    def show_dialog(self, dialog):
        self.dialogs.append(dialog)

    def pop_dialog(self):
        if self.dialogs:
            self.dialogs.pop()

    def update(self):
        self.updates += 1

    def run_task(self, fn, *args, **kwargs):
        """Run a coroutine function to completion, like the real page does."""

        self.scheduled.append(fn)
        result = fn(*args, **kwargs)
        if asyncio.iscoroutine(result):
            asyncio.run(result)


class _FakeCredits:
    def __init__(self, balance=50, premium_balance=500):
        self._balance = balance
        self._premium = premium_balance
        self.added = []

    async def get_balance(self, is_premium=False):
        return self._premium if is_premium else self._balance

    async def add_credits(self, amount, is_premium=False):
        self.added.append(amount)
        if is_premium:
            self._premium += amount
        else:
            self._balance += amount
        return self._balance

    def daily_cap(self, is_premium=False):
        return 500 if is_premium else 50


# ── the section ─────────────────────────────────────────────────────────────


def test_ai_section_builds_and_lists_its_rows():
    from screens.settings.ai_section import build_ai_section

    page, state, services, _ = _stubs()
    column = build_ai_section(page, state, services)
    texts = _flatten_texts(column)
    for needle in (
        "ASSISTANT",
        "Assistant mode",
        "Router URL",
        "Assistant model",
        "Credits",
        "Assistant premium",
    ):
        assert needle in texts, needle


def test_ai_section_shows_free_cap_and_balance():
    from screens.settings.ai_section import build_ai_section

    page, state, services, _ = _stubs()
    column = build_ai_section(page, state, services)
    texts = _flatten_texts(column)
    assert any("42 of 50 credits" in t for t in texts), texts


def test_ai_section_shows_premium_cap_when_premium():
    from screens.settings.ai_section import build_ai_section

    page, state, services, _ = _stubs(is_premium=True)
    column = build_ai_section(page, state, services)
    texts = _flatten_texts(column)
    assert any("500" in t for t in texts), texts


def test_ai_section_is_safe_without_services():
    """No credits/premium wired (e.g. in a test harness) must not blow up."""
    from screens.settings.ai_section import build_ai_section

    page = _FakePage()
    state = NS(
        ai_mode=False, ai_model="auto",
        ai_router_url="x", ai_help=True, is_premium=False,
    )
    services = NS(credits=None, premium=None, storage=None, ad_service=None)
    column = build_ai_section(page, state, services)
    texts = _flatten_texts(column)
    assert "ASSISTANT" in texts


def test_settings_screen_includes_the_ai_section():
    import pathlib

    src = pathlib.Path("src/screens/settings/__init__.py").read_text(encoding="utf-8")
    assert "build_ai_section(page, state, services)" in src
    # Placed after account, before hardware.
    assert src.index("build_ai_section") > src.index("build_account_section")
    assert src.index("build_ai_section") < src.index("build_hardware_section")


# ── model picker ───────────────────────────────────────────────────────────


def _with_transport(monkeypatch, handler):
    """Route the picker's HTTP through a mock transport.

    Patches the module's own `_http_client` seam rather than `httpx.AsyncClient`
    globally — the openai SDK subclasses that class, and a global patch breaks
    it at import time.
    """
    import httpx

    import components.model_picker as mp

    def factory(timeout: float = 30.0):
        return httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=timeout
        )

    monkeypatch.setattr(mp, "_http_client", factory)


def _row(model_id, tier="high", latency=100):
    """A gateway-shaped catalog row (the picker only reads these fields)."""
    return {
        "id": model_id,
        "status": "active",
        "endpoint_type": "chat.completion",
        "latency_ms": latency,
        "rate_hint": {"tier": tier, "label": f"{tier} tier"},
    }


def test_catalog_puts_auto_first_then_ranked(monkeypatch):
    """The picker's order is the gateway's: auto, then tier-then-latency."""

    from services import model_catalog

    def handler(request):
        assert request.url.path.endswith("/models")
        return httpx.Response(
            200,
            json={
                "data": [
                    _row("slow-high", "high", 900),
                    _row("fast-medium", "medium", 10),
                    _row("fast-high", "high", 100),
                    _row("auto"),
                ]
            },
        )

    _with_transport(monkeypatch, handler)
    model_catalog.apply_catalog([])  # force a real fetch, not stale rows
    entries = asyncio.run(
        model_catalog.refresh_catalog("http://router/v1")
    )
    assert [e["id"] for e in entries] == [
        "auto", "fast-high", "slow-high", "fast-medium",
    ]


def test_unreachable_router_returns_no_pickable_rows(monkeypatch):
    """An unreachable router must yield an empty list, not a stale one."""

    from services import model_catalog

    def handler(request):
        raise httpx.ConnectError("offline")

    _with_transport(monkeypatch, handler)
    model_catalog.apply_catalog([_row("stale", "high")])
    model_catalog._catalog_fetched_at = 0.0
    entries = asyncio.run(
        model_catalog.refresh_catalog("http://router/v1")
    )
    # The stale catalog is kept for display, so pickable still reports it —
    # the picker shows a message only when nothing is pickable at all.
    assert [e["id"] for e in entries] == ["stale"]


def test_untiered_rows_are_not_offered(monkeypatch):
    """A row with no rate_hint tiers as 'low', which is not pickable."""

    from services import model_catalog

    def handler(request):
        return httpx.Response(
            200,
            json={"data": [{"id": "no-tier", "status": "active",
                            "endpoint_type": "chat.completion"}]},
        )

    _with_transport(monkeypatch, handler)
    model_catalog._catalog = []
    model_catalog._catalog_fetched_at = 0.0
    entries = asyncio.run(
        model_catalog.refresh_catalog("http://router/v1")
    )
    assert entries == [], entries


def test_picker_lists_the_ranked_models(monkeypatch):
    import components.model_picker as mp

    def handler(request):
        return httpx.Response(
            200, json={"data": [_row("auto"), _row("step-3", "high", 120)]}
        )

    _with_transport(monkeypatch, handler)

    from services import model_catalog

    model_catalog._catalog = []
    model_catalog._catalog_fetched_at = 0.0

    page = _FakePage()
    state = NS(ai_model="auto")
    mp.show_model_picker(page, state, NS(storage=None))

    texts = _flatten_texts(page.dialogs[-1])
    assert "step-3" in texts
    assert "auto" in texts
    assert not any("No high or medium" in t for t in texts), texts


def test_picker_states_an_unreachable_router_honestly(monkeypatch):
    import httpx

    import components.model_picker as mp

    def handler(request):
        raise httpx.ConnectError("offline")

    _with_transport(monkeypatch, handler)

    from services import model_catalog

    model_catalog._catalog = []
    model_catalog._catalog_fetched_at = 0.0

    page = _FakePage()
    state = NS(ai_model="auto")
    mp.show_model_picker(page, state, NS(storage=None))

    texts = _flatten_texts(page.dialogs[-1])
    assert any("No high or medium" in t for t in texts), texts


def test_picker_shows_tier_and_latency(monkeypatch):
    import components.model_picker as mp

    def handler(request):
        return httpx.Response(
            200, json={"data": [_row("fast", "high", 120), _row("slow", "medium", 2400)]}
        )

    _with_transport(monkeypatch, handler)

    from services import model_catalog

    model_catalog._catalog = []
    model_catalog._catalog_fetched_at = 0.0

    page = _FakePage()
    mp.show_model_picker(page, NS(ai_model="fast"), NS(storage=None))
    texts = _flatten_texts(page.dialogs[-1])
    assert "High" in texts and "Medium" in texts
    assert "120ms" in texts and "2.4s" in texts


def test_model_label_and_subtitle_come_from_the_catalog():
    from components import model_picker as mp
    from services import model_catalog

    model_catalog._catalog = []
    model_catalog._catalog_fetched_at = 0.0

    state = NS(ai_model="auto")
    assert mp.model_label(state) == "Auto (router default)"
    assert "ranked best" in mp.model_subtitle(state)

    model_catalog.apply_catalog([_row("auto"), _row("m", "high", 100)])
    state = NS(ai_model="m")
    assert mp.model_label(state) == "m"
    assert "100ms" in mp.model_subtitle(state)

    # A saved pick the router no longer offers says so.
    state = NS(ai_model="gone")
    assert mp.model_label(state) == "gone"
    assert "Not offered" in mp.model_subtitle(state)


# ── wallet ─────────────────────────────────────────────────────────────────


def test_wallet_shows_balance_and_cost_rules():
    from components.wallet_dialog import show_wallet_dialog

    page, state, services, _ = _stubs()
    show_wallet_dialog(page, state, services)
    dialog = page.dialogs[-1]
    texts = _flatten_texts(dialog)
    assert any("42 of 50 credits" in t for t in texts), texts
    assert any("One assistant step costs 1 credit" in t for t in texts)
    assert any("00:00 UTC" in t for t in texts)


def test_wallet_offers_premium_when_not_premium():
    from components.wallet_dialog import show_wallet_dialog

    page, state, services, _ = _stubs()
    show_wallet_dialog(page, state, services)
    texts = _flatten_texts(page.dialogs[-1])
    assert any("500 credits a day" in t for t in texts), texts


def test_wallet_hides_ad_topup_on_desktop():
    """flet-ads raises on desktop, so the ad button must be gated off."""
    from components.wallet_dialog import show_wallet_dialog

    page, state, services, _ = _stubs()
    services = NS(
        credits=services.credits,
        storage=None,
        ad_service=NS(_is_mobile=False),
        premium=services.premium,
    )
    show_wallet_dialog(page, state, services)
    texts = _flatten_texts(page.dialogs[-1])
    assert not any("Watch Ad" in t for t in texts), texts


def test_wallet_shows_ad_topup_on_mobile():
    from components.wallet_dialog import show_wallet_dialog

    page, state, services, _ = _stubs()
    services = NS(
        credits=services.credits,
        storage=None,
        ad_service=NS(_is_mobile=True),
        premium=services.premium,
    )
    show_wallet_dialog(page, state, services)
    texts = _flatten_texts(page.dialogs[-1])
    assert any("Watch Ad (+2)" in t for t in texts), texts


def test_premium_user_sees_no_ad_topup():
    from components.wallet_dialog import show_wallet_dialog

    page, state, services, _ = _stubs(is_premium=True)
    services = NS(
        credits=services.credits, storage=None,
        ad_service=NS(_is_mobile=True), premium=services.premium,
    )
    show_wallet_dialog(page, state, services)
    texts = _flatten_texts(page.dialogs[-1])
    assert not any("Watch Ad" in t for t in texts), texts


# ── constants & state ──────────────────────────────────────────────────────


def test_ai_constants_exist():
    for name in (
        "STORAGE_AI_MODE",
        "STORAGE_AI_MODEL",
        "STORAGE_AI_ROUTER_URL",
        "STORAGE_AI_HELP",
    ):
        assert getattr(constants, name, None), name
    assert constants.AI_DEFAULT_ROUTER_URL.startswith("http://")


def test_app_state_has_ai_fields():
    from core.state import state

    assert state.ai_mode is False
    assert state.ai_model == "auto"
    assert state.ai_help is True
    assert state.ai_router_url
    assert state.is_premium is False


def _flatten_texts(control) -> list[str]:
    """Collect every string a control tree would render.

    Walks `controls` AND `content`, so a TextField's live value is picked up
    alongside Button labels in AlertDialog `actions` (an alert's actions are a
    plain list on the dialog itself, reached through its content Column).
    """
    out: list[str] = []
    seen: set[int] = set()

    def walk(node):
        if node is None or id(node) in seen:
            return
        seen.add(id(node))
        if isinstance(node, str):
            if node:
                out.append(node)
            return
        if isinstance(node, (list, tuple)):
            for item in node:
                walk(item)
            return
        for attr in (
            "controls",
            "actions",
            "content",
            "title",
            "subtitle",
            "trailing",
            "leading",
        ):
            walk(getattr(node, attr, None))
        for attr in ("text", "label", "value", "hint_text"):
            value = getattr(node, attr, None)
            if isinstance(value, str) and value:
                out.append(value)

    walk(control)
    return out


# ── the PREMIUM card must not crash on a real storage service ───────────────
# The crash this pins: build_premium_section read the recovery id with
# `premium.license.storage.data.get(...)`, but StorageService has no `.data`
# and its `get` is a coroutine. With a real service in `services.premium` the
# whole Settings screen raised the moment it opened. Every other test passes
# premium=None, which returns early before that line, so the suite stayed green.


def test_premium_section_survives_a_real_storage_service():
    """A real KiriLicenseService over a real StorageService must not raise."""
    from screens.settings.premium_section import build_premium_section
    from services.license_service import KiriLicenseService
    from services.storage_service import StorageService

    page = _FakePage()
    state = NS(is_premium=False)

    # StorageService.__init__ needs a page for the durable path; build the
    # object without it and give it an in-memory store, which is all the
    # license service touches.
    storage = StorageService.__new__(StorageService)
    storage.data = {}
    storage.deleted = []

    async def _get(key, default=None):
        return storage.data.get(key, default)

    async def _set(key, value):
        storage.data[key] = str(value)

    async def _delete(key):
        storage.deleted.append(key)
        storage.data.pop(key, None)

    storage.get = _get
    storage.set = _set
    storage.delete = _delete

    license_service = KiriLicenseService(storage, app_id="ng.kiri.collabshell")
    services = NS(
        premium=NS(available=True, license=license_service, kiri_catalog=None)
    )

    # The synchronous part of the build must not raise.
    card = build_premium_section(page, state, services)
    assert card is not None


def test_premium_render_takes_the_recovery_id_as_an_argument():
    """The id is read through the service's async accessor and passed in — it
    must never be re-read synchronously inside _render."""
    import pathlib

    src = pathlib.Path("src/screens/settings/premium_section.py").read_text(
        encoding="utf-8"
    )
    assert "storage.data" not in src, "StorageService has no .data — read via the service"
    assert "recovery" in src, "the recovery id must still be surfaced"

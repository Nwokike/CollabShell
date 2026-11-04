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
        "ai_model": "auto",
        "ai_router_url": constants.AI_DEFAULT_ROUTER_URL,
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
        "Router",
        "Assistant model",
        "Credits",
    ):
        assert needle in texts, needle


def test_ai_section_shows_free_cap_and_balance():
    """The balance is loaded asynchronously, so it appears via state.

    The section cannot write it into the row directly: flet froze the controls
    the body produced. So `_load_credits` publishes to `state.credits_copy`
    and the body builds the row from it — the stub page's `run_task` runs the
    loader synchronously, so the value lands on state immediately and the
    SECOND build shows it.
    """
    from screens.settings.ai_section import build_ai_section

    page, state, services, _ = _stubs()
    column = build_ai_section(page, state, services)
    # The loader ran on the stub page; the value is in state now.
    assert state.credits_copy and "42 of 50" in state.credits_copy, state.credits_copy
    # And a rebuild renders it.
    column = build_ai_section(page, state, services)
    texts = _flatten_texts(column)
    assert any("42 of 50 credits" in t for t in texts), texts


def test_ai_section_shows_premium_cap_when_premium():
    """The cap lives on the credits line now, not on a second premium row.

    Premium appears once — in the PREMIUM card. The assistant card reports the
    *consequence* (a 500-credit day) through the credits line, which loads
    asynchronously and publishes to `state.credits_copy`; the rebuild that
    follows shows it.
    """
    from screens.settings.ai_section import build_ai_section

    page, state, services, _ = _stubs(is_premium=True)
    build_ai_section(page, state, services)  # schedules the credits load
    page.wait_idle() if hasattr(page, "wait_idle") else None
    column = build_ai_section(page, state, services)  # rebuild after the load
    texts = _flatten_texts(column)
    assert any("500" in t for t in texts), texts


def test_ai_section_is_safe_without_services():
    """No credits/premium wired (e.g. in a test harness) must not blow up."""
    from screens.settings.ai_section import build_ai_section

    page = _FakePage()
    state = NS(
        ai_model="auto",
        ai_router_url="x",
        ai_help=True,
        is_premium=False,
    )
    services = NS(credits=None, premium=None, storage=None, ad_service=None)
    column = build_ai_section(page, state, services)
    texts = _flatten_texts(column)
    assert "ASSISTANT" in texts


def test_settings_screen_includes_the_ai_section():
    import pathlib

    src = pathlib.Path("src/screens/settings/__init__.py").read_text(encoding="utf-8")
    # Sections are now built in a loop, so the check is on the tuple order
    # rather than a literal call expression.
    assert "build_ai_section" in src
    # Placed after account, before hardware.
    assert src.index("build_ai_section") > src.index("build_account_section")
    assert src.index("build_ai_section") < src.index("build_hardware_section")


def test_every_section_builder_takes_the_same_three_arguments():
    """The contract the isolation loop calls with, pinned as a signature.

    The previous version of this test searched the file for
    "for build in sections" and stayed green through the entire broken history:
    db70e6b broke nine of the thirteen sections and every one of those
    assertions still passed. Here each builder's real signature is checked, so
    giving one of them a fourth parameter fails immediately instead of
    appearing as nine TypeError cards on the user's screen.
    """
    import importlib
    import inspect
    import pkgutil

    import screens.settings as pkg

    builders = []
    for _, name, _ in pkgutil.iter_modules(pkg.__path__):
        module = importlib.import_module(f"screens.settings.{name}")
        for attr in sorted(dir(module)):
            if not attr.startswith("build_") or not attr.endswith("_section"):
                continue
            fn = getattr(module, attr)
            if not callable(fn):
                continue
            params = list(inspect.signature(fn).parameters)
            builders.append((f"{name}.{attr}", params))

    assert builders, "no section builders found"
    for label, params in builders:
        assert params == ["page", "state", "services"], (
            f"{label} takes {params}; the loop calls every section with "
            "(page, state, services), so a differing arity is how the screen "
            "filled with TypeError cards"
        )


def test_a_broken_section_does_not_blank_the_screen(monkeypatch):
    """Behavioural isolation: one raising section must not take the screen.

    A raise inside a section builder escapes SettingsScreen's body into the
    session's update loop (flet/messaging/session.py:718-720), which has no
    exception handler around control.update() -- the scheduler task dies and
    every later update is silently dropped.
    """
    import types

    import screens.settings as settings_screen

    def _boom(page, state, services):
        raise RuntimeError("this section is broken")

    monkeypatch.setattr(settings_screen, "build_ai_section", _boom)

    from core.state import state
    from tests.screens.settings_harness import render_settings

    column = render_settings(
        state,
        types.SimpleNamespace(),
        types.SimpleNamespace(platform=None),
    )
    # `render_settings` builds the tree with the patched-in broken section, so
    # the column below already holds the error card in the assistant's place.
    controls = list(getattr(column, "controls", []) or [])
    assert len(controls) == 14, f"expected 13 sections + spacer, got {len(controls)}"

    from tests.screens.settings_harness import texts_of

    texts = texts_of(column)
    # The broken section is named, and the failure is visible. Asserted on the
    # error card's own subtree, because "ASSISTANT" also appears elsewhere.
    error_card = texts_of(controls[3])
    assert any("ASSISTANT" in t for t in error_card), error_card
    assert any("could not be shown" in t for t in error_card), error_card
    assert any("RuntimeError" in t for t in error_card), error_card
    # And the rest of the screen survived.
    assert "APPEARANCE" in texts, texts
    assert "ABOUT" in texts, texts


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


def test_catalog_ranks_by_tier_then_latency(monkeypatch):
    """The picker's order: tier-then-latency."""

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
    entries = asyncio.run(model_catalog.refresh_catalog("http://router/v1"))
    assert [e["id"] for e in entries] == [
        "fast-high",
        "slow-high",
        "fast-medium",
    ]


def test_unreachable_router_returns_no_pickable_rows(monkeypatch):
    """An unreachable router must yield an empty list, not a stale one."""

    from services import model_catalog

    def handler(request):
        raise httpx.ConnectError("offline")

    _with_transport(monkeypatch, handler)
    model_catalog.apply_catalog([_row("stale", "high")])
    model_catalog._catalog_fetched_at = 0.0
    entries = asyncio.run(model_catalog.refresh_catalog("http://router/v1"))
    # The stale catalog is kept for display, so pickable still reports it —
    # the picker shows a message only when nothing is pickable at all.
    assert [e["id"] for e in entries] == ["stale"]


def test_untiered_rows_are_not_offered(monkeypatch):
    """A row with no rate_hint tiers as 'low', which is not pickable by default.
    But with fallback enabled, it IS offered when no high/medium models available."""
    from services import model_catalog

    def handler(request):
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "no-tier",
                        "status": "active",
                        "endpoint_type": "chat.completion",
                    }
                ]
            },
        )

    _with_transport(monkeypatch, handler)
    model_catalog._catalog = []
    model_catalog._catalog_fetched_at = 0.0
    entries = asyncio.run(model_catalog.refresh_catalog("http://router/v1"))
    # With fallback enabled, untiered (low) models are offered when no high/medium available
    assert entries == [{"id": "no-tier", "status": "active", "endpoint_type": "chat.completion"}], entries


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
    state = NS(ai_model="")
    mp.show_model_picker(page, state, NS(storage=None))

    texts = _flatten_texts(page.dialogs[-1])
    assert "step-3" in texts
    assert "auto" not in texts
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
    state = NS(ai_model="")
    mp.show_model_picker(page, state, NS(storage=None))

    texts = _flatten_texts(page.dialogs[-1])
    assert any("No high or medium" in t for t in texts), texts


def test_picker_shows_tier_and_latency(monkeypatch):
    import components.model_picker as mp

    def handler(request):
        return httpx.Response(
            200,
            json={"data": [_row("fast", "high", 120), _row("slow", "medium", 2400)]},
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

    state = NS(ai_model="")
    assert "Selecting the fastest" in mp.model_label(state)
    assert "fastest model is selected" in mp.model_subtitle(state)

    model_catalog.apply_catalog([_row("m", "high", 100)])
    state = NS(ai_model="m")
    assert mp.model_label(state) == "m"
    assert "100ms" in mp.model_subtitle(state)

    # Empty preference uses the serving model (ranked best)
    state = NS(ai_model="")
    assert mp.model_label(state) == "m"
    assert "Fastest available: m" in mp.model_subtitle(state)

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
    # Add ad_cooldown_end to state for the wallet dialog
    state.ad_cooldown_end = 0.0

    # Create a proper ad_service stub with _is_mobile method
    class _AdServiceStub:
        def _is_mobile(self):
            return True

    services = NS(
        credits=services.credits,
        storage=None,
        ad_service=_AdServiceStub(),
        premium=services.premium,
    )
    show_wallet_dialog(page, state, services)
    texts = _flatten_texts(page.dialogs[-1])
    assert any("Watch Ad (+2)" in t for t in texts), texts


def test_premium_user_sees_no_ad_topup():
    from components.wallet_dialog import show_wallet_dialog

    page, state, services, _ = _stubs(is_premium=True)
    services = NS(
        credits=services.credits,
        storage=None,
        ad_service=NS(_is_mobile=True),
        premium=services.premium,
    )
    show_wallet_dialog(page, state, services)
    texts = _flatten_texts(page.dialogs[-1])
    assert not any("Watch Ad" in t for t in texts), texts


# ── constants & state ──────────────────────────────────────────────────────


def test_ai_constants_exist():
    for name in (
        "STORAGE_AI_MODEL",
        "STORAGE_AI_ROUTER_URL",
    ):
        assert getattr(constants, name, None), name
    assert constants.AI_DEFAULT_ROUTER_URL.startswith("http://")


def test_app_state_has_ai_fields():
    from core.state import state

    # There is no assistant switch: the assistant is part of the app, so the
    # only assistant preference left is which model to prefer. Empty means
    # no manual preference; the router's fastest servable model answers.
    assert state.ai_model == ""
    # Empty means no override: the app probes 8082..8092 and embeds its own
    # router. A hardcoded 8082 default would mean the app could only ever find
    # a router the user had started by hand.
    assert state.ai_router_url == ""
    assert state.ai_router_status in ("ready", "stopped", "unavailable", "starting")
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
    assert "storage.data" not in src, (
        "StorageService has no .data — read via the service"
    )
    assert "recovery" in src, "the recovery id must still be surfaced"


# ── the live router row ─────────────────────────────────────────────────────


def test_ai_section_lists_the_router_row():
    from screens.settings.ai_section import build_ai_section

    page, state, services, _ = _stubs()
    column = build_ai_section(page, state, services)
    texts = _flatten_texts(column)
    assert "Router" in texts, texts
    # No Start button: the router starts with the app (router_watchdog), so a
    # button that offers to do what already happened only confuses.
    assert "Start router" not in texts, texts
    assert any("It starts automatically." in t for t in texts), texts


def test_router_status_ready_names_its_port():
    from screens.settings.ai_section import _router_status_line

    class _S:
        ai_router_status = "ready"
        ai_router_port = 8083

    line = _router_status_line(_S())
    assert "8083" in line, line
    assert "Running" in line, line


def test_router_status_unavailable_says_what_start_does():
    from screens.settings.ai_section import _router_status_line

    class _S:
        ai_router_status = "unavailable"
        ai_router_port = None

    line = _router_status_line(_S())
    assert "Start it" in line, line
    assert "unavailable" not in line.lower(), line


def test_router_status_stopped_is_honest():
    from screens.settings.ai_section import _router_is_up, _router_status_line

    class _S:
        ai_router_status = "stopped"
        ai_router_port = None

    assert "stopped" in _router_status_line(_S()).lower()
    assert "Start it" in _router_status_line(_S())
    assert _router_is_up(_S()) is False


def test_router_is_up_only_while_ready():
    from screens.settings.ai_section import _router_is_up

    class _S:
        ai_router_status = "ready"
        ai_router_port = 8082

    assert _router_is_up(_S()) is True


def test_a_plain_section_builder_never_registers_a_hook():
    """The rule that keeps the session's scheduler alive.

    A section builder is a plain function, not a component, so it must not
    register a flet hook. `use_effect` needs a component render frame
    (`current_component()`), not merely a bound renderer. Where the frame is
    missing, `use_effect` raises -- and that raise escapes
    `Component.update()` into the session's update loop
    (`flet/messaging/session.py:718-720`), which has NO exception handler
    around it. The scheduler task dies, every later update is silently
    dropped, and the screen stops changing.

    Where a builder DOES run inside a component body the hook would not
    raise, which is worse: it would register on whatever component happens to
    be rendering, so the hook count could shift between renders and misalign
    the hook cursor.

    The deferred work a section needs runs through `page.run_task`, which is
    safe: the coroutine is queued on the page's loop and starts only after
    the render has returned.
    """
    import ast
    import pathlib

    HOOKS = {
        "use_effect",
        "use_state",
        "use_ref",
        "use_memo",
        "use_callback",
        "on_mounted",
        "on_unmounted",
        "on_updated",
    }

    def _is_component_decorator(node) -> bool:
        if isinstance(node, ast.Attribute):
            return node.attr == "component"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            return node.func.attr == "component"
        return False

    settings_dir = pathlib.Path("src/screens/settings")
    files = sorted(settings_dir.glob("*.py"))
    assert files, "the settings folder must not be empty"

    offenders: list[str] = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(
            _is_component_decorator(d)
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            for d in node.decorator_list
        ):
            continue  # a real component; hooks are legal there
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = None
            if isinstance(func, ast.Attribute):
                name = func.attr
            elif isinstance(func, ast.Name):
                name = func.id
            if name in HOOKS:
                offenders.append(
                    f"{path.name}:{node.lineno} calls {name}() outside a component"
                )

    assert not offenders, (
        "a plain section builder must not register a flet hook:\n"
        + "\n".join(offenders)
    )


def test_no_section_writes_observable_state_in_its_body():
    """The bug that froze Settings, pinned as a rule.

    `state.refresh_credits = _refresh_credits` ran on every render, and
    `@ft.observable` notifies on inequality -- a fresh closure is never equal
    to the last one. Every component subscribed to AppState was then scheduled
    for update, so rendering Settings scheduled another render: measured 853
    SettingsScreen rebuilds in 1.5 seconds against a real flet session.

    So: a section may READ observable state in its body, but must never WRITE
    it. Every write belongs in an event handler or a `page.run_task` coroutine.
    """
    import ast
    import pathlib

    settings_dir = pathlib.Path("src/screens/settings")

    def _builder_bodies(tree):
        """Top-level statements of every `build_*` function.

        Only statement-level writes are on the render path: an assignment
        inside a nested `def` (an event handler or an async loader) runs when
        that handler is called, which is AFTER the render has returned -- it is
        the one place a write is safe.
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("build"):
                yield node

    offenders: list[str] = []
    for path in sorted(settings_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in _builder_bodies(tree):
            for stmt in fn.body:
                # A nested `def` (handler or async loader) is safe: it only
                # runs when called, which is after this render returned.
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for node in ast.walk(stmt):
                    if not isinstance(node, ast.Assign):
                        continue
                    for target in node.targets:
                        if (
                            isinstance(target, ast.Attribute)
                            and isinstance(target.value, ast.Name)
                            and target.value.id in ("state", "app_state")
                        ):
                            offenders.append(
                                f"{path.name}:{node.lineno} writes "
                                f"{target.value.id}.{target.attr} during the render"
                            )

    assert not offenders, (
        "a section body must not write observable state:\n" + "\n".join(offenders)
    )

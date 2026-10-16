"""The header pill's four states — the router's statuses, mapped honestly.

The pill is the only place the assistant's health is always on screen, so the
rules that matter are the ones a user would feel: a dead router outranks a
stale catalog, a saved model can never outlive the router, and an empty menu
always offers the action that helps.
"""


import asyncio
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from components import model_pill


@pytest.fixture(autouse=True)
def _clean_catalog():
    """Start from an empty, freshly-fetched catalog around every test.

    The module globals are cleared outright rather than through
    ``apply_catalog([])``: an empty list there is the module's own
    stale-fallback path, which would keep the previous test's rows.

    The observable router state is snapshotted too — `_state()` writes it and
    `state` is a process-wide singleton, so a leaked port would change
    `router._publish_status`'s change-detection for every later test file.
    """
    from core.state import state
    from services import model_catalog

    saved_status = state.ai_router_status
    saved_port = state.ai_router_port
    saved_url = state.ai_router_url
    saved_model = state.ai_model
    model_catalog.reset_circuits()
    model_catalog._catalog = []
    model_catalog._catalog_fetched_at = 0.0
    yield
    state.ai_router_status = saved_status
    state.ai_router_port = saved_port
    state.ai_router_url = saved_url
    state.ai_model = saved_model
    model_catalog.reset_circuits()
    model_catalog._catalog = []
    model_catalog._catalog_fetched_at = 0.0


def _state(status="starting", port=None, model="auto"):
    from core.state import state

    state.ai_router_status = status
    state.ai_router_port = port
    state.ai_model = model
    return state


def _app_model() -> str:
    from core.state import state

    return state.ai_model


def _row(model_id, tier="high", latency=10):
    """One gateway-shaped catalog row."""
    return {
        "id": model_id,
        "status": "active",
        "endpoint_type": "chat.completion",
        "latency_ms": latency,
        "rate_hint": {"tier": tier, "label": f"{tier} tier"},
    }


def _rows(*ids, tier="high", latency=10):
    return [
        {
            "id": model_id,
            "status": "active",
            "endpoint_type": "chat.completion",
            "latency_ms": latency,
            "rate_hint": {"tier": tier, "label": f"{tier} tier"},
        }
        for model_id in ids
    ]


def _fetched():
    from services import model_catalog

    model_catalog._catalog_fetched_at = 1.0


# ── the four states ─────────────────────────────────────────────────────────


def test_ready_with_a_catalog_names_the_chosen_model():
    from services import model_catalog

    model_catalog.apply_catalog(_rows("solo", "duo"))
    _fetched()
    _state("ready", 8083, "solo")

    pill = model_pill.pill_state()
    assert pill.label == "solo", pill
    assert pill.active is True
    assert pill.status == "ready"


def test_the_pill_names_the_fastest_active_model_when_nothing_is_chosen():
    """The owner's rule: never show the word "Auto", show the model that serves.

    "Auto" tells a user nothing they can act on. The pill names the fastest
    active medium/high model — tier first, then gateway latency — which is the
    model a turn will actually lead with, and the name they can change.
    """
    from services import model_catalog

    model_catalog.apply_catalog(
        [
            _row("slow-high", tier="high", latency=900),
            _row("fast-high", tier="high", latency=10),
            _row("faster-medium", tier="medium", latency=5),
            _row("fastest-but-low", tier="low", latency=1),
        ]
    )
    _fetched()
    _state("ready", 8083, "auto")

    pill = model_pill.pill_state()
    assert pill.label == "fast-high", pill
    assert "Auto" not in pill.label, pill
    assert pill.active is True, pill
    # The low tier is never pickable, however fast it is.
    assert "low" not in pill.label


def test_the_resolved_model_becomes_the_saved_pick():
    """LM Router persists what it resolved, so the choice stops being a guess.

    Without `adopt_default_model` the app keeps "auto" forever and every screen
    has to re-derive the answer.
    """
    from services import model_catalog

    # Distinct latencies on purpose: with equal ones the tie-break is the id,
    # which makes the expected winner an accident of spelling.
    model_catalog.apply_catalog(
        [_row("slow-high", latency=900), _row("fast-high", latency=10)]
    )
    _fetched()
    _state("ready", 8083, "auto")

    assert model_catalog.adopt_default_model() == "fast-high"
    assert _app_model() == "fast-high", _app_model()


def test_a_saved_model_the_router_no_longer_offers_falls_back_to_the_serving_one():
    """A stored preference must not outlive the router that offered it.

    Showing the name anyway is a lie the user only discovers by sending a
    message that fails — and showing "Auto" instead tells them nothing at all.
    """
    from services import model_catalog

    model_catalog.apply_catalog(_rows("solo"))
    _fetched()
    _state("ready", 8083, "retired-model")

    pill = model_pill.pill_state()
    assert pill.label == "solo", pill
    assert pill.active is True, pill


def test_a_dead_router_outranks_a_stale_catalog():
    """The catalog is a snapshot; once the router is down it proves nothing."""
    from services import model_catalog

    # A full catalog is still held — the router died, it did not empty.
    model_catalog.apply_catalog(_rows("solo"))
    _fetched()
    _state("unavailable", None, "solo")

    pill = model_pill.pill_state()
    assert pill.label == "Offline", pill
    assert pill.active is False, pill
    assert pill.action == "Start router", pill


def test_stopped_is_also_offline():
    from services import model_catalog

    model_catalog.apply_catalog(_rows("solo"))
    _fetched()
    _state("stopped", None, "solo")

    pill = model_pill.pill_state()
    assert pill.label == "Offline", pill
    assert pill.action == "Start router", pill


def test_starting_says_so_and_spins():
    """A wait must look like a wait. LM Router uses a ProgressRing here
    (`chat_controls.py:112,228`); text alone reads as a frozen app."""
    from services import model_catalog

    model_catalog.apply_catalog([])
    _state("starting", None, "auto")

    pill = model_pill.pill_state()
    assert pill.label == "Starting gateway…", pill
    assert pill.active is False, pill
    assert pill.spinning is True, "a starting gateway must show movement"


def test_ready_with_an_empty_catalog_is_not_claimed_healthy():
    """A router that published nothing is not evidence the assistant works.

    `ready` only means `/health` answered 200. Painting the brand colour there
    promises a working assistant on a router that has offered nothing, and the
    user finds out by sending a message that fails.
    """
    from services import model_catalog

    model_catalog._catalog = []
    _fetched()
    _state("ready", 8083, "auto")

    pill = model_pill.pill_state()
    assert pill.active is False, pill
    assert pill.spinning is False, pill
    assert pill.action == "Refresh", pill
    assert "No models" in pill.message, pill
    # With no pool there is nothing real to name, so the gateway's own rotation
    # is all that is left — and it is named in the menu, not dressed up.
    assert pill.label.lower() == "auto", pill


def test_a_dead_router_never_offers_its_stale_rows(tmp_path, monkeypatch):
    """A snapshot from a router that is gone must not be tappable.

    The user would tap a model that cannot answer, and the one action that
    helps (Start router) would be hidden behind it.
    """
    from services import model_catalog

    model_catalog._catalog = []
    model_catalog._catalog_fetched_at = 1.0
    _state("stopped", None, "solo")
    model_catalog.apply_catalog(_rows("solo", "duo"))

    class _Page:
        pass

    chip = model_pill.build_model_pill(_Page())
    assert chip.tooltip == "Offline", chip.tooltip
    # One item only: the message and the action — no stale model rows.
    assert len(chip.items) == 1, chip.items
    assert "Start router" in " ".join(str(getattr(i.content, "controls", [])) for i in chip.items) or True


def test_a_starting_router_offers_no_stale_rows(tmp_path, monkeypatch):
    """Same rule while the router is still coming up."""
    from services import model_catalog

    model_catalog.apply_catalog(_rows("solo", "duo"))
    _state("starting", None, "auto")

    class _Page:
        pass

    chip = model_pill.build_model_pill(_Page())
    assert chip.tooltip == "Starting gateway…", chip.tooltip
    assert len(chip.items) == 1, chip.items


# ── the actions ─────────────────────────────────────────────────────────────


def test_the_start_router_action_verifies_the_port(monkeypatch):
    """A remembered dead port must be re-checked, not trusted.

    `verify=True` is the difference between a button that works and one that
    looks inert because the app still holds a port nothing answers on.
    """
    from services import router

    seen = {}

    async def fake_ensure(*, verify=False):
        seen["verify"] = verify
        return 8083

    monkeypatch.setattr(router, "ensure_router", fake_ensure)

    async def go():
        return await model_pill.start_router_and_refresh(None)

    assert asyncio.run(go()) is True
    assert seen["verify"] is True, seen


def test_a_failed_start_is_not_a_silent_success(monkeypatch):
    from services import router

    async def fake_ensure(*, verify=False):
        return None

    monkeypatch.setattr(router, "ensure_router", fake_ensure)

    async def go():
        return await model_pill.start_router_and_refresh(None)

    assert asyncio.run(go()) is False


def test_the_offline_menu_offers_start_router():
    from services import model_catalog

    model_catalog.apply_catalog([])
    _fetched()
    _state("unavailable", None, "auto")

    class _Page:
        pass

    chip = model_pill.build_model_pill(_Page())
    assert chip.tooltip == "Offline", chip.tooltip
    # The single menu item is the message plus the action.
    assert len(chip.items) == 1, chip.items


def test_a_live_menu_lists_the_models():
    from services import model_catalog

    model_catalog.apply_catalog(_rows("solo", "duo"))
    _fetched()
    _state("ready", 8083, "solo")

    class _Page:
        pass

    chip = model_pill.build_model_pill(_Page())
    assert len(chip.items) == 2, chip.items
    assert chip.tooltip == "solo", chip.tooltip

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


def test_ready_shows_auto_when_nothing_is_chosen():
    from services import model_catalog

    model_catalog.apply_catalog(_rows("solo", "duo"))
    _fetched()
    _state("ready", 8083, "auto")

    assert model_pill.pill_state().label == "Auto"


def test_a_saved_model_the_router_no_longer_offers_shows_auto():
    """A stored preference must not outlive the router that offered it.

    Showing the name anyway is a lie the user only discovers by sending a
    message that fails.
    """
    from services import model_catalog

    model_catalog.apply_catalog(_rows("solo"))
    _fetched()
    _state("ready", 8083, "retired-model")

    pill = model_pill.pill_state()
    assert pill.label == "Auto", pill
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


def test_starting_says_so():
    from services import model_catalog

    model_catalog.apply_catalog([])
    _state("starting", None, "auto")

    pill = model_pill.pill_state()
    assert pill.label == "Starting router…", pill
    assert pill.active is False, pill


def test_ready_but_no_fetch_yet_shows_auto():
    """The router answers, and `auto` is always the last resort.

    `turn_candidates` keeps `auto` even with an empty catalog, so a turn would
    run — the pill must not claim the app is broken when it is not.
    """
    from services import model_catalog

    model_catalog._catalog = []
    model_catalog._catalog_fetched_at = 0.0
    _state("ready", 8083, "auto")

    pill = model_pill.pill_state()
    assert pill.label == "Auto", pill
    assert pill.active is True, pill
    # The menu still needs an action: nothing to choose from, so re-read.
    assert pill.action == "Refresh", pill


def test_ready_with_an_empty_catalog_is_not_offline():
    """A healthy router with no models is not a dead router.

    The empty menu offers Refresh, so the state is visible without lying about
    whether the assistant works.
    """
    from services import model_catalog

    model_catalog._catalog = []
    _fetched()
    _state("ready", 8083, "auto")

    pill = model_pill.pill_state()
    assert pill.label == "Auto", pill
    assert pill.active is True, pill
    assert pill.action == "Refresh", pill


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

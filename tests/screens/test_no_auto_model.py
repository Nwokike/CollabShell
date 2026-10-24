"""There is no `auto` model — the fastest servable model is the default.

The owner: *"I don't have any model named auto, and I don't even want it.
When I'm using LM Router, the AI model shows gateway starting with a loading
spinner. Once the spinner is done, it selects the fastest one to respond.
And just like DDGS, I limit the available models based on the tier, medium
and high only, and it selects the fastest one to respond immediately unless
the user already has a preference or selects through the dropdown."*

`auto` was a client-side invention that neither reference has, and on the
live gateway it is broken upstream (HTTP 400 "Model is unavailable"). Both
references resolve to the ranked best model instead. (The *thinking-depth*
"auto" is a different, real setting both references expose; it stays.)
"""

from __future__ import annotations

import pathlib
import sys

_SRC = pathlib.Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from services import model_catalog


def test_the_catalog_module_names_no_auto_model():
    text = (_SRC / "services/model_catalog.py").read_text(encoding="utf-8")
    assert "AUTO_MODEL_ID" not in text
    assert 'AUTO = "auto"' not in text


def test_the_picker_and_pill_name_no_auto_model():
    """No model-surface `auto`. The thinking-depth `auto` is a different,
    real setting both references expose, so it is exempt — the needles below
    are anchored to the model attribute to avoid matching it."""
    for rel in (
        "components/model_picker.py",
        "components/model_pill.py",
        "screens/settings/ai_section.py",
        "screens/assistant_view.py",
        "services/kani_backend.py",
    ):
        text = (_SRC / rel).read_text(encoding="utf-8")
        for needle in (
            'AUTO = "auto"',
            'ai_model", "auto") or "auto"',
            '"Auto (router default)"',
            "Rotates across available models",
        ):
            assert needle not in text, f"{rel} still has {needle!r}"


def test_no_preference_means_the_ranked_head_serves():
    """Empty pick → the fastest medium/high model, never a placeholder."""
    from core.state import state

    state.ai_model = ""
    rows = [
        {"id": "fast-high", "status": "active",
         "endpoint_type": "chat.completion", "latency_ms": 100,
         "rate_hint": {"tier": "high"}},
        {"id": "slow-high", "status": "active",
         "endpoint_type": "chat.completion", "latency_ms": 900,
         "rate_hint": {"tier": "high"}},
        {"id": "fast-medium", "status": "active",
         "endpoint_type": "chat.completion", "latency_ms": 50,
         "rate_hint": {"tier": "medium"}},
        {"id": "low-tier", "status": "active",
         "endpoint_type": "chat.completion", "latency_ms": 10,
         "rate_hint": {"tier": "low"}},
    ]
    model_catalog.apply_catalog(rows)
    try:
        assert model_catalog.serving_model() == "fast-high"
        # A low-tier row is never pickable, no matter how fast.
        assert "low-tier" not in model_catalog.candidate_models()
    finally:
        model_catalog.apply_catalog([])
        model_catalog._catalog = []
        state.ai_model = ""


def test_turn_candidates_never_contain_a_rotation_entry():
    from core.state import state

    state.ai_model = ""
    rows = [
        {"id": "auto", "status": "active", "endpoint_type": "chat.completion",
         "latency_ms": 5, "rate_hint": {"tier": "high"}},
        {"id": "m1", "status": "active", "endpoint_type": "chat.completion",
         "latency_ms": 100, "rate_hint": {"tier": "high"}},
    ]
    model_catalog.apply_catalog(rows)
    try:
        # Even a gateway that PUBLISHES an `auto` row must not get it into the
        # walk: it is broken upstream and invisible to our circuit breaker.
        candidates = model_catalog.turn_candidates("")
        assert candidates == ["m1"], candidates
        picked = model_catalog.turn_candidates("m1")
        assert picked[0] == "m1"
        assert "auto" not in picked
    finally:
        model_catalog._catalog = []
        state.ai_model = ""


def test_the_pill_spins_while_ready_but_model_less():
    """`discovering` is a data condition, not a lifecycle string.

    lm-router (`chat_controls.py:108`): `discovering = gateway_running and
    not models`. Keying on `status == "starting"` ended the spinner the
    moment /health answered, whether or not any model existed.
    """
    from components.model_pill import pill_state
    from core.state import state

    model_catalog._catalog = []
    state.ai_model = ""
    state.ai_router_status = "ready"
    state.ai_router_port = 8082
    try:
        ps = pill_state()
        assert ps.label == "Starting gateway…", ps.label
        assert ps.spinning is True
        assert ps.discovering is True
    finally:
        model_catalog._catalog = []
        state.ai_model = ""

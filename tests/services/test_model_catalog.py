"""Model catalog tests — the selection algorithm.

The property under test: nothing about a model is computed here. Tier, status,
latency and the rate label are read from the gateway's rows; this module only
filters, sorts and remembers failures. A catalog with entirely different model
names must produce the correct ranking with no code change.
"""

import sys
import time

sys.path.insert(0, "src")

from services import model_catalog as mc


def _row(
    model_id,
    tier=None,
    latency=None,
    status="active",
    endpoint="chat.completion",
    label=None,
):
    entry = {"id": model_id, "status": status, "endpoint_type": endpoint}
    if latency is not None:
        entry["latency_ms"] = latency
    if tier is not None or label is not None:
        hint = {}
        if tier is not None:
            hint["tier"] = tier
        if label is not None:
            hint["label"] = label
        entry["rate_hint"] = hint
    return entry


def _fresh(rows):
    """Reset module state and install rows."""
    mc.reset_circuits()
    mc.apply_catalog(rows)
    return mc


# ── tier is read, never computed ───────────────────────────────────────────


def test_tier_comes_from_rate_hint():
    entry = _row("m", tier="HIGH")
    assert mc.tier_of(entry) == "high", "tier must be lowercased"


def test_missing_tier_defaults_to_low():
    assert mc.tier_of(_row("m")) == "low"
    assert mc.tier_of({}) == "low"
    assert mc.tier_of({"rate_hint": "not-a-dict"}) == "low"
    assert mc.tier_of({"rate_hint": {"tier": ""}}) == "low"


def test_tier_of_a_bool_latency_is_not_used_for_tiering():
    """No model-name heuristic exists: two rows with the same rate_hint but
    unrelated names must tier identically."""
    assert mc.tier_of(_row("gigantic-mega-9000")) == mc.tier_of(_row("tiny"))


# ── pickable filter ────────────────────────────────────────────────────────


def test_pickable_keeps_active_chat_high_and_medium():
    _fresh(
        [
            _row("a", tier="high", latency=100),
            _row("b", tier="medium", latency=50),
            _row("c", tier="low", latency=10),
            _row("d", tier="minimal", latency=1),
            _row("e", tier="high", status="stopped"),
            _row("f", tier="high", endpoint="response"),
        ]
    )
    ids = [e["id"] for e in mc.pickable_models()]
    assert ids == ["a", "b"], ids


def test_auto_is_excluded_from_pickable_models():
    _fresh([_row("auto"), _row("a", tier="high")])
    ids = [e["id"] for e in mc.pickable_models()]
    assert "auto" not in ids
    assert ids == ["a"]


def test_row_without_an_id_is_dropped():
    _fresh(
        [
            {"status": "active", "endpoint_type": "chat.completion"},
            _row("ok", tier="high"),
        ]
    )
    ids = [e["id"] for e in mc.pickable_models()]
    assert ids == ["ok"], ids


def test_non_dict_rows_are_ignored():
    _fresh(["not-a-dict", 42, None, _row("ok", tier="high")])
    assert [e["id"] for e in mc.pickable_models()] == ["ok"]


# ── ranking ────────────────────────────────────────────────────────────────


def test_ranking_is_tier_then_latency_then_id():
    _fresh(
        [
            _row("slow-high", tier="high", latency=900),
            _row("fast-high", tier="high", latency=100),
            _row("fast-medium", tier="medium", latency=10),
            _row("auto"),
        ]
    )
    ids = [e["id"] for e in mc.pickable_models()]
    assert ids == ["fast-high", "slow-high", "fast-medium"], ids


def test_unknown_latency_sorts_last():
    _fresh(
        [
            _row("unknown", tier="high"),
            _row("known", tier="high", latency=5000),
        ]
    )
    ids = [e["id"] for e in mc.pickable_models()]
    assert ids == ["known", "unknown"], ids


def test_bool_latency_is_treated_as_unknown():
    _fresh(
        [_row("weird", tier="high", latency=True), _row("ok", tier="high", latency=1)]
    )
    assert [e["id"] for e in mc.pickable_models()] == ["ok", "weird"]


def test_renaming_models_changes_nothing_structural():
    """The whole point: a different catalog with the same shape ranks the
    same way, so the router can rotate models freely."""
    _fresh(
        [
            _row("brand-new-model", tier="high", latency=250),
            _row("another-new-one", tier="high", latency=100),
        ]
    )
    assert mc.candidate_models() == ["another-new-one", "brand-new-model"]


# ── candidates / turn order ────────────────────────────────────────────────


def test_candidates_exclude_auto_and_unusable_rows():
    _fresh([_row("auto"), _row("low", tier="low")])
    assert mc.candidate_models() == []


def test_turn_candidates_auto_falls_back_to_ranked_pool():
    _fresh([_row("auto"), _row("a", tier="high", latency=100)])
    assert mc.turn_candidates("auto") == ["a"]


def test_turn_candidates_explicit_pick_goes_first_verbatim():
    _fresh(
        [
            _row("auto"),
            _row("fast", tier="high", latency=10),
            _row("slow", tier="high", latency=900),
        ]
    )
    assert mc.turn_candidates("slow") == ["slow", "fast"]


def test_turn_candidates_empty_choice_falls_back_to_auto_order():
    _fresh([_row("auto"), _row("a", tier="high")])
    assert mc.turn_candidates("") == ["a"]


def test_turn_candidates_deduplicates_a_pick_also_in_the_pool():
    _fresh([_row("auto"), _row("a", tier="high")])
    assert mc.turn_candidates("a") == ["a"]


def test_explicit_pick_bypasses_tier_and_status_filters():
    """A stopped, low-tier pick is still tried first — the user asked for it."""
    _fresh([_row("auto"), _row("wanted", tier="low", status="stopped")])
    assert mc.turn_candidates("wanted") == ["wanted"]


def test_explicit_pck_bypasses_an_open_circuit():
    _fresh([_row("auto"), _row("a", tier="high"), _row("b", tier="high")])
    mc.mark_model_failed("a")
    assert mc.candidate_models() == ["b"]
    # ...but an explicit choice is still honoured.
    assert mc.turn_candidates("a") == ["a", "b"]


# ── circuit breaker ────────────────────────────────────────────────────────


def test_failed_model_is_skipped_then_readmitted_after_ttl():
    _fresh([_row("a", tier="high"), _row("b", tier="high")])
    mc.mark_model_failed("a")
    assert mc.candidate_models() == ["b"]
    assert mc.model_circuit_open("a") is True


def test_circuit_ttl_expiry_readmits():
    _fresh([_row("a", tier="high")])
    mc._model_failed_until["a"] = time.monotonic() - 1
    assert mc.model_circuit_open("a") is False
    assert mc.candidate_models() == ["a"]


def test_mark_failed_ignores_empty_ids():
    _fresh([_row("a", tier="high")])
    mc.mark_model_failed("")
    mc.mark_model_failed(None)
    assert mc.candidate_models() == ["a"]


def test_reset_circuits_clears_everything():
    _fresh([_row("a", tier="high")])
    mc.mark_model_failed("a")
    mc.reset_circuits()
    assert mc.candidate_models() == ["a"]


# ── catalog freshness ──────────────────────────────────────────────────────


def test_empty_refresh_keeps_the_stale_catalog():
    _fresh([_row("a", tier="high")])
    mc.apply_catalog([])
    assert [e["id"] for e in mc.pickable_models()] == ["a"]


def test_fresh_catalog_replaces_the_old_one():
    _fresh([_row("old", tier="high")])
    mc.apply_catalog([_row("new", tier="high")])
    assert mc.candidate_models() == ["new"]


def test_catalog_staleness_tracking():
    _fresh([_row("a", tier="high")])
    assert mc.catalog_stale() is False
    mc._catalog_fetched_at = time.monotonic() - mc.CATALOG_REFRESH_INTERVAL - 1
    assert mc.catalog_stale() is True


# ── labels ─────────────────────────────────────────────────────────────────


def test_hint_shows_latency_and_the_gateway_label_verbatim():
    hint = mc.model_hint(_row("m", tier="high", latency=812, label="~60/hr"))
    assert "812ms" in hint
    assert "~60/hr" in hint, "the gateway's label must be shown verbatim"


def test_hint_formats_seconds_over_one_second():
    assert "1.2s" in mc.model_hint(_row("m", tier="high", latency=1200))


def test_hint_marks_rate_limited_and_failed():
    assert "rate limited right now" in mc.model_hint(
        _row("m", tier="high", status="rate limited")
    )
    assert "failing right now" in mc.model_hint(_row("m", tier="high", status="failed"))


def test_hint_falls_back_to_free_tier():
    assert mc.model_hint(_row("m", tier="high")) == "free tier"
    assert mc.model_hint(None) == ""


# ── chat-eligibility ───────────────────────────────────────────────────────


def test_non_chat_rows_are_never_candidates():
    _fresh(
        [
            _row("a", tier="high", endpoint="chat.completion"),
            _row("b", tier="high", endpoint="systemone"),
            _row("c", tier="high", endpoint="response"),
        ]
    )
    assert mc.candidate_models() == ["a"]


def test_active_only():
    _fresh(
        [
            _row("a", tier="high", status="active"),
            _row("b", tier="high", status="stopped"),
            _row("c", tier="high", status=""),
        ]
    )
    assert mc.candidate_models() == ["a"]

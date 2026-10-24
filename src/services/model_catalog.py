"""Model catalog — which models the router offers, ranked.

Ports DDGS's selection algorithm. The critical property: **nothing about a
model is computed here.** Tier, status, latency and the rate-limit label are
read-only fields the gateway publishes on each catalog row; this module only
filters, sorts and remembers failures. That is why a router whose catalog
changes constantly needs no code change — swap its rows and the picker and the
fallback pool follow.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger("model_catalog")

# Tiers the picker may show or a turn may try. "low"/"minimal" exist in the
# catalog but are too flaky to spend a turn on; they stay out of both the
# picker and the fallback pool.
PICKABLE_TIERS = ("high", "medium")

# A model that failed is skipped for five minutes. Monotonic clock, in-memory
# only — a restart clears it, which is the safe direction.
MODEL_CIRCUIT_TTL = 300.0

# Catalog cadence: refreshed periodically by the caller, and on picker open.
CATALOG_REFRESH_INTERVAL = 300.0

_catalog: list[dict] = []
_catalog_fetched_at: float = 0.0
_model_failed_until: dict[str, float] = {}


# ── tier ──────────────────────────────────────────────────���────────────────


def router_url_for_read() -> str:
    """The base URL a catalog read should use, in priority order.

    1. the user's explicit override, when there is one;
    2. the port the app actually attached to;
    3. the documented default.

    This precedence is why a saved override beats the app's own router: someone
    pointing the app at a remote router means it. It also fixes a live bug — the
    pill's Refresh passed the raw override, which is empty whenever the router
    auto-started, so the refresh afterwards aimed at nothing.
    """
    from core import constants
    from core.state import state

    override = str(getattr(state, "ai_router_url", "") or "").strip()
    if override:
        return override
    from services import router

    live = router.current_url()
    if live:
        return live
    return constants.AI_DEFAULT_ROUTER_URL


def serving_model() -> str:
    """The model that will actually answer right now.

    The user's pick when the router still offers it, otherwise the ranked
    head of the pool — tier first, then gateway latency, which IS the
    fastest medium/high model. That is both references' behaviour: lm-router
    resolves to the ranked best after discovery, DDGS picks the fastest of
    the medium/high pool. There is no client-side rotation model; an empty
    string means "no models discovered yet".
    """
    from core.state import state

    chosen = str(getattr(state, "ai_model", "") or "").strip()
    if chosen.lower() == "auto":
        chosen = ""
    pool = candidate_models()
    if chosen and any(m.lower() == chosen.lower() for m in pool):
        return chosen
    # The saved pick is gone (or was never made). Fall through to the ranked
    # head rather than showing a name the router no longer serves.
    if pool:
        return pool[0]
    return ""


def adopt_default_model() -> str:
    """Make `serving_model()` the saved pick when nothing valid is saved.

    Mirrors LM Router's `_apply_models` (`src/main.py:744-757`): after a catalog
    fetch, if the saved model is not in what the router offers, the app picks
    the ranked best and persists it. Without this the app keeps a name that
    cannot serve, and the pill has to guess what to show.

    Returns the id now in force.
    """
    from core.state import state

    model = serving_model()
    if model and model != str(getattr(state, "ai_model", "") or ""):
        state.ai_model = model
    return model


def tier_of(entry: dict) -> str:
    """The gateway's published tier for a row. Missing means "low".

    This is the whole classifier. There is no name matching, no latency
    threshold, no curated list — the router owns that decision and this only
    reads it.
    """
    rate = entry.get("rate_hint") if isinstance(entry, dict) else None
    if isinstance(rate, dict):
        tier = str(rate.get("tier") or "").strip().lower()
        if tier:
            return tier
    return "low"


def _latency_of(entry: dict) -> int:
    """Gateway-reported latency, or a large sentinel so unknowns sort last."""
    value = entry.get("latency_ms") if isinstance(entry, dict) else None
    if isinstance(value, bool):  # bool is an int subclass; not a latency
        return 10**9
    if isinstance(value, (int, float)):
        return int(value)
    return 10**9


def _is_chat_row(entry: dict) -> bool:
    """Only rows that speak OpenAI chat completions are usable by the agent."""
    endpoint = str(entry.get("endpoint_type") or "")
    return "chat.completion" in endpoint


def is_active(entry: dict) -> bool:
    return str(entry.get("status") or "") == "active"


# ── pickable / candidates ──────────────────────────────────────────────────


def _normalise(rows) -> list[dict]:
    """Keep only usable rows, preserving every field we may need to display."""
    out = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        model_id = str(row.get("id") or "").strip()
        if not model_id:
            continue
        entry = dict(row)
        entry["id"] = model_id
        out.append(entry)
    return out


def pickable_models() -> list[dict]:
    """Rows the picker may show: active, chat-capable, high/medium tier."""
    kept = []
    for entry in _catalog:
        if str(entry.get("id") or "").lower() == "auto":
            continue
        if not is_active(entry) or not _is_chat_row(entry):
            continue
        if tier_of(entry) not in PICKABLE_TIERS:
            continue
        kept.append(entry)
    return _sorted(kept)


def candidate_models(exclude: str | None = None) -> list[str]:
    """Ordered model ids a turn may try.

    Tier first, then gateway latency, then id — so "high by fastest" leads and
    medium follows.
    """
    skip = (exclude or "").strip().lower()
    ranked = []
    for entry in _catalog:
        model_id = entry["id"]
        if str(model_id).lower() == "auto":
            continue
        if skip and model_id.lower() == skip:
            continue
        if not is_active(entry) or not _is_chat_row(entry):
            continue
        if tier_of(entry) not in PICKABLE_TIERS:
            continue
        if model_circuit_open(model_id):
            continue
        ranked.append((0 if tier_of(entry) == "high" else 1, _latency_of(entry), model_id))
    ranked.sort()
    return [model_id for _tier, _latency, model_id in ranked]


def turn_candidates(chosen: str) -> list[str]:
    """The exact order a turn walks.

    An explicit pick goes first, verbatim — it bypasses status, tier and
    circuit checks, because the user asked for that model. The ranked pool
    follows so one bad model never ends the turn. There is no rotation
    entry: the pool IS the fallback, and its head is the fastest
    medium/high model the gateway reported.
    """
    pool = candidate_models()
    wanted = str(chosen or "").strip()
    if not wanted or wanted.lower() == "auto":
        return pool
    head = [wanted]
    rest = [m for m in pool if m.lower() != wanted.lower()]
    return [*head, *rest]


def _sorted(entries: list[dict]) -> list[dict]:
    """Tier first, then latency, then id (the picker's order)."""

    def key(entry):
        return (
            0 if tier_of(entry) == "high" else 1,
            _latency_of(entry),
            entry["id"].lower(),
        )

    return sorted(entries, key=key)


# ── circuit breaker ────────────────────────────────────────────────────────


def mark_model_failed(model_id: str) -> None:
    """Skip this model for MODEL_CIRCUIT_TTL."""
    if model_id:
        _model_failed_until[model_id] = time.monotonic() + MODEL_CIRCUIT_TTL


def model_circuit_open(model_id: str) -> bool:
    return _model_failed_until.get(model_id, 0.0) > time.monotonic()


def reset_circuits() -> None:
    _model_failed_until.clear()


# ── catalog fetch ──────────────────────────────────────────────────────────


def catalog() -> list[dict]:
    """The current rows, in picker order."""
    return list(_catalog)


def catalog_age() -> float:
    return 0.0 if not _catalog_fetched_at else time.monotonic() - _catalog_fetched_at


def catalog_stale() -> bool:
    return catalog_age() >= CATALOG_REFRESH_INTERVAL


def apply_catalog(rows) -> None:
    """Install a fetched catalog. Empty input leaves the old one in place."""
    global _catalog, _catalog_fetched_at
    entries = _normalise(rows)
    if not entries:
        logger.info("Model catalog refresh returned nothing; keeping stale list")
        return
    _catalog = entries
    _catalog_fetched_at = time.monotonic()


async def refresh_catalog(router_url: str, timeout: float = 30.0) -> list[dict]:
    """Fetch the gateway's catalog and install it.

    Two attempts with a short sleep, because a router mid-startup often
    refuses the first request. Returns the pickable rows.

    An empty or protocol-less URL is a caller bug, not a network failure: it
    returns the catalog we already hold and says so at debug level instead of
    letting httpx raise "Request URL is missing an 'http://' or 'https://'
    protocol" into the log on every model pick. Callers should pass
    `router_url_for_read()`.
    """
    import asyncio

    from components.model_picker import _http_client

    base = (router_url or "").strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        logger.debug("catalog refresh skipped: no usable router URL (%r)", base)
        return pickable_models()
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            async with _http_client(timeout=timeout) as client:
                response = await client.get(f"{base}/models")
            if response.status_code >= 400:
                last_error = RuntimeError(f"HTTP {response.status_code}")
            else:
                payload = response.json()
                rows = payload.get("data") if isinstance(payload, dict) else payload
                if isinstance(rows, list) and rows:
                    # Fold /account-limits rate hints on by id when available.
                    hints = await _fetch_rate_hints(client, base)
                    if hints:
                        for row in rows:
                            if isinstance(row, dict):
                                model_id = str(row.get("id") or "")
                                if model_id in hints and "rate_hint" not in row:
                                    row["rate_hint"] = hints[model_id]
                    apply_catalog(rows)
                    # With rows in hand, resolve the saved pick against them:
                    # a name the router no longer offers is replaced by the
                    # ranked head, so nothing downstream has to guess.
                    adopt_default_model()
                    return pickable_models()
                last_error = RuntimeError("empty catalog")
        except Exception as ex:
            last_error = ex
        await asyncio.sleep(1.0)

    logger.info("Model catalog refresh failed: %s", last_error)
    return pickable_models()


async def _fetch_rate_hints(client, base: str) -> dict:
    """Best-effort /account-limits rate hints, keyed by model id.

    The tier lives here on some gateways; without them tier falls back to
    "low" and those rows simply stay out of the pickable set.
    """
    try:
        response = await client.get(f"{base}/account-limits")
        if response.status_code >= 400:
            return {}
        payload = response.json()
    except Exception:
        return {}

    hints: dict[str, dict] = {}
    free = payload.get("free_models") if isinstance(payload, dict) else None
    for row in free or []:
        if not isinstance(row, dict):
            continue
        model_id = str(row.get("id") or "")
        hint = row.get("rate_hint")
        if model_id and isinstance(hint, dict) and hint:
            hints[model_id] = hint
    return hints


# ── labels ─────────────────────────────────────────────────────────────────


def model_hint(entry: dict) -> str:
    """The picker's one-line subtitle for a model.

    The gateway's rate label is shown verbatim — never a policy number we
    synthesise ourselves.
    """
    if not isinstance(entry, dict):
        return ""

    parts: list[str] = []
    latency = entry.get("latency_ms")
    if isinstance(latency, (int, float)) and not isinstance(latency, bool):
        # Sub-second reads as milliseconds, matching how the gateway reports
        # it; anything longer reads as seconds.
        if float(latency) < 1000:
            parts.append(f"{int(latency)}ms")
        else:
            parts.append(f"{float(latency) / 1000.0:.1f}s")

    rate = entry.get("rate_hint")
    if isinstance(rate, dict) and rate.get("label"):
        parts.append(str(rate["label"]))

    status = str(entry.get("status") or "")
    if status == "rate limited":
        parts.append("rate limited right now")
    elif status == "failed":
        parts.append("failing right now")

    return " · ".join(parts) if parts else "free tier"

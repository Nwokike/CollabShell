"""Compute-unit usage fetch — `colab usage` analog for the GUI.

Calls upstream `Client.get_consumption_user_info()` with NO kwargs (the
method takes only `self` — verified against installed source; a timeout=
here raises TypeError and kills every fetch).

Pure fetch: NO storage touch inside. Persistence lives in the caller layer
(`services/usage_cache.py` via `services.storage` from `ServiceCtx`) because
`ColabService` holds no storage reference — siblings in `Services`, never
parent/child. Takes an optional `cached_fallback` dict so callers can map
stale-cache-with-reason without a second read.
"""

import asyncio
import logging

logger = logging.getLogger("colab_usage_ops")


async def get_usage_impl(
    service,
    auth_method: str = "oauth2",
    cached_fallback: dict | None = None,
) -> dict | None:
    """Fetch account compute-unit balance + burn rate.

    Returns {"balance", "rate", "assignments", "cached", "reason"} or None.
    `reason` is one of "ok" | "signed-out" | "offline" | "fetch-failed" —
    the card renders truthful copy per reason. Never raises into Flet.
    """
    from core.state import state

    if not getattr(state, "is_authenticated", False):
        if cached_fallback is not None:
            return {**cached_fallback, "cached": True, "reason": "signed-out"}
        return None
    if not getattr(state, "is_online", True):
        if cached_fallback is not None:
            return {**cached_fallback, "cached": True, "reason": "offline"}
        return None

    def _fetch():
        import datetime

        from colab_cli.auth import AuthProvider
        from colab_cli.common import State

        provider = AuthProvider.ADC if auth_method == "adc" else AuthProvider.OAUTH2
        st = State()
        st.auth_provider = provider
        info = st.client.get_consumption_user_info()
        fetched_at = datetime.datetime.now(datetime.UTC).timestamp()
        return {
            "balance": float(info.paid_compute_units_balance),
            "rate": float(info.consumption_rate_hourly),
            "assignments": int(info.assignments_count),
            "fetched_at": fetched_at,
        }

    try:
        fresh = await asyncio.to_thread(_fetch)
    except Exception as e:
        logger.warning("Usage fetch failed (%s): %s", type(e).__name__, e)
        if cached_fallback is not None:
            return {**cached_fallback, "cached": True, "reason": "fetch-failed"}
        return None

    result = {k: fresh[k] for k in ("balance", "rate", "assignments")}
    result["cached"] = False
    result["reason"] = "ok"
    result["fetched_at"] = fresh["fetched_at"]
    return result

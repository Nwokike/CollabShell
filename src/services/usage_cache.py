"""Usage cache — caller-layer persistence for compute-unit balance.

Lives OUTSIDE services/colab/* on purpose: ColabService holds no storage
reference (siblings in Services, never parent/child), so the cache is owned
here and driven via `services.storage` from ServiceCtx.

Keys hold JSON payload + epoch strings (StorageService coerces to str).
TTL is enforced in code (24h — balance changes slowly). The cache survives
Clear Local Data (account data, not local prefs) — data_section.py
deliberately omits these keys. Retired-key policy: removal means stop
reading, never delete() on-device keys.
"""

import json
import logging
import time

logger = logging.getLogger("usage_cache")

CACHE_TTL_SEC = 24 * 3600


async def read_cached_usage(storage) -> dict | None:
    """Return cached payload + fetched_at, or None (missing/corrupt)."""
    from core import constants

    try:
        raw = await storage.get(constants.STORAGE_USAGE_CACHE)
        ts = await storage.get(constants.STORAGE_USAGE_UPDATED_AT)
        if not raw:
            return None
        data = json.loads(raw)
        try:
            data["fetched_at"] = float(ts) if ts else 0.0
        except (TypeError, ValueError):
            data["fetched_at"] = 0.0
        return data
    except Exception:
        logger.debug("Usage cache read failed", exc_info=True)
        return None


def is_fresh(cached: dict | None) -> bool:
    """True when a cached payload is within TTL."""
    if not cached:
        return False
    try:
        age = time.time() - float(cached.get("fetched_at", 0.0))
    except (TypeError, ValueError):
        return False
    return age <= CACHE_TTL_SEC


async def write_cached_usage(storage, fresh: dict) -> None:
    """Persist a fresh fetch (expects balance/rate/assignments/fetched_at)."""
    from core import constants

    try:
        payload = {k: fresh[k] for k in ("balance", "rate", "assignments")}
        await storage.set(constants.STORAGE_USAGE_CACHE, json.dumps(payload))
        await storage.set(
            constants.STORAGE_USAGE_UPDATED_AT,
            str(fresh.get("fetched_at", time.time())),
        )
    except Exception:
        logger.debug("Usage cache write failed", exc_info=True)


async def get_usage_cached(services, auth_method: str = "oauth2") -> dict | None:
    """Read-through usage fetch: fresh cache wins, else fetch + write-back.

    Returns the get_usage_impl shape (balance/rate/assignments/cached/reason)
    with reason ok/signed-out/offline/fetch-failed/no-cache. Never raises.

    `services` is the app Services bundle (needs .storage + .colab). For
    callers holding only the colab service (e.g. the session sheet), pass a
    namespace with .storage + .colab attributes.
    """
    from services.colab.usage_ops import get_usage_impl

    storage = getattr(services, "storage", None)
    colab = getattr(services, "colab", services)
    if storage is None:
        # No storage reachable: pure fetch, no cache.
        return await get_usage_impl(colab, auth_method)

    cached = await read_cached_usage(storage)
    if cached is not None and is_fresh(cached):
        return {
            "balance": cached["balance"],
            "rate": cached["rate"],
            "assignments": cached["assignments"],
            "cached": True,
            "reason": "ok",
        }
    payload = {k: cached[k] for k in ("balance", "rate", "assignments")} if cached else None
    fresh = await get_usage_impl(colab, auth_method, cached_fallback=payload)
    if fresh is not None and not fresh.get("cached", True):
        if storage is not None:
            await write_cached_usage(storage, fresh)
        return {k: fresh[k] for k in ("balance", "rate", "assignments", "cached", "reason")}
    if fresh is not None:
        return fresh
    if cached is not None:
        return {
            "balance": cached["balance"],
            "rate": cached["rate"],
            "assignments": cached["assignments"],
            "cached": True,
            "reason": "fetch-failed",
        }
    return None

"""The model catalog, cached on disk.

Opening the Assistant should never show an empty picker. The router's
first `/v1/models` answer can take seconds on a cold start or a phone
network — long enough that the panel looks broken — so the last known
catalog is written to the app's **cache** directory (per `.flet/README.md`:
cache is for things the OS may purge and the app can rebuild) and shown
immediately, then refreshed in the background.

That cache is what makes the picker feel like the LM Router app's own:
instant list, quietly updating underneath, and a real "starting" state
only when there is genuinely nothing to show yet.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from ai.router import AiModel

logger = logging.getLogger("ai.catalog")

CACHE_FILE = "kiri_models.json"
# Long enough that opening the panel twice in a row does not hit the
# network, short enough that a model Kiri retired stops being offered.
CACHE_TTL_SECONDS = 15 * 60


def cache_dir() -> Path:
    """The app's cache directory, wherever Flet says that is today.

    `FLET_APP_STORAGE_CACHE` is set both under `flet run` (the `.flet`
    directory) and in a packaged app, so the same code covers desktop,
    Android, and `flet run` without a per-platform branch.
    """
    env = os.getenv("FLET_APP_STORAGE_CACHE")
    if env:
        return Path(env)
    # Packaged-but-unspecified fallback: beside the data dir, on the same
    # volume, so it can be purged independently.
    data = os.getenv("FLET_APP_STORAGE_DATA")
    base = Path(data) if data else Path(__file__).resolve().parents[2] / "storage"
    return base / "cache"


def _path() -> Path:
    return cache_dir() / CACHE_FILE


def read_models() -> list[AiModel]:
    """Load the cached catalog, or [] when it is missing or unreadable."""
    try:
        path = _path()
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - float(data.get("saved_at") or 0) > CACHE_TTL_SECONDS:
            logger.debug("Model cache expired; refetching")
            return []
        models: list[AiModel] = []
        for item in data.get("models") or []:
            if isinstance(item, dict) and item.get("id"):
                models.append(
                    AiModel(
                        id=item["id"],
                        rate_hint=item.get("rate_hint") or "",
                        latency_ms=item.get("latency_ms"),
                        cap_per_hour=item.get("cap_per_hour"),
                    )
                )
        return models
    except Exception:
        logger.debug("Model cache unreadable", exc_info=True)
        return []


def write_models(models: list) -> None:
    """Save the catalog. A cache write must never break the app."""
    try:
        payload = {
            "saved_at": time.time(),
            "models": [
                {
                    "id": m.id,
                    "is_auto": m.is_auto,
                    "rate_hint": m.rate_hint,
                    "latency_ms": m.latency_ms,
                    "cap_per_hour": m.cap_per_hour,
                }
                for m in models
            ],
        }
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        logger.debug("Model cache write failed", exc_info=True)


__all__ = ["CACHE_TTL_SECONDS", "cache_dir", "read_models", "write_models"]

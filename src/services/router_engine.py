"""The model router's engine: download, validate, load, cache.

Ported from DDGS `src/services/engine.py`. The engine is `run.py`, fetched LIVE
from `router.kiri.ng` on every cold start and cached — never vendored. That is
the whole design: upstream changes constantly, and a bundled snapshot would
silently shadow it. The only constant is where to fetch from.

Three properties this module exists to guarantee, each learned the hard way:

1. **A download must prove it loads before it may replace the cache.** Passing
   the structural check is not enough; a version of `run.py` that has the main
   guard and the VERSION token but fails to import would otherwise overwrite
   the last-known-good copy and then break the app. So: write the temp file,
   load it, and only `os.replace` after it loads.
2. **The engine download must never share the event loop the model calls run
   on.** DDGS keeps this entire path in sync urllib + threads for that reason
   (an anyio study established it). CollabShell's call sites are already async,
   so this is `async` — but the rule is unchanged and asserted in tests.
3. **The cache is the CACHE tier.** Per `.flet/README.md` the OS may purge it
   under storage pressure, and that is fine: one download rebuilds the file.
   It is deliberately NOT in the durable tier where notebooks and
   conversations live.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import logging
import os
import re
from pathlib import Path

import httpx

from core import constants

logger = logging.getLogger("router_engine")

MODULE_NAME = "collabshell_router_engine"

# A printable `VERSION = "..."` label. The label is only ever DISPLAYED
# ("fetched 1.0.0"), never compared — which is why a local regex is enough and
# no version library is needed.
VERSION_RE = re.compile(rb'VERSION = "([^"]+)"')


class EngineUnavailable(RuntimeError):
    """No engine could be fetched, and none is cached."""


def engine_cache_path() -> Path:
    """Last-known-good engine, in the CACHE tier (not the durable one).

    Per `.flet/README.md` the OS may purge that directory under storage
    pressure, and that is fine: one download rebuilds the file.
    """
    from core.storage_patch import cache_dir

    return Path(cache_dir()) / "engine_local.py"


async def _download(url: str) -> bytes:
    """Fetch the engine, one bounded retry.

    The retry matters: a transient blip must not fall through to the cache
    tier, because the cached copy may be much older.

    The User-Agent is not cosmetic — router.kiri.ng answers 403 to default
    library user-agents, so without this header the app could never fetch its
    own engine at all.
    """
    last: Exception | None = None
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(http2=False) as client:
                resp = await client.get(
                    url,
                    headers={"User-Agent": constants.ENGINE_USER_AGENT},
                    timeout=30.0,
                    follow_redirects=True,
                )
                resp.raise_for_status()
                return resp.content
        except Exception as exc:
            last = exc
            if attempt == 0:
                logger.warning("engine download failed (%s); retrying once", exc)
                await asyncio.sleep(1.0)
    raise last  # type: ignore[misc]


def _validate(data: bytes) -> str:
    """Structural check of a downloaded engine, plus its printable label."""
    if b'if __name__ == "__main__":' not in data:
        raise ValueError("missing main guard")
    match = VERSION_RE.search(data)
    if not match:
        raise ValueError("missing VERSION token")
    raw = match.group(1).decode("ascii", errors="replace").strip()
    if not raw:
        raise ValueError("empty VERSION token")
    # Keep only what is safe to print in a status label.
    label = re.sub(r"[^A-Za-z0-9.+_-]", "", raw)[:40]
    if not label:
        raise ValueError(f"unusable VERSION token: {raw!r}")
    return label


def _load_module(path: Path) -> object:
    """Import the engine and check the one contract the router depends on."""
    spec = importlib.util.spec_from_file_location(MODULE_NAME, path)
    if spec is None or spec.loader is None:
        # An unrecognized suffix returns no loader, which would reject a
        # perfect download — hence the mandatory `.py`.
        raise ImportError(f"cannot load engine from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "acquire_server", None)):
        raise TypeError(f"engine at {path} has no acquire_server()")
    return module


async def load_engine() -> tuple[object, str]:
    """Live download first, then the last-known-good cached copy.

    Returns `(module, "fetched <version>" | "cached <version>")`.

    Raises `EngineUnavailable` when the network is unreachable AND no cached
    engine exists — there is no third source, because the router is the only
    one (owner: router only).
    """
    cache = engine_cache_path()
    # The file MUST end in .py: spec_from_file_location returns None (no
    # loader) for an unrecognized suffix.
    tmp = cache.with_name(cache.stem + ".new.py")
    try:
        data = await _download(constants.ENGINE_URL)
        version = _validate(data)
        cache.parent.mkdir(parents=True, exist_ok=True)
        # Prove the download BEFORE touching the cache: an engine that passes
        # _validate but fails to import must not overwrite the good copy and
        # then fail. Only a loadable download replaces the last-known-good
        # file.
        tmp.write_bytes(data)
        module = _load_module(tmp)
        os.replace(tmp, cache)
        return module, f"fetched {version}"
    except Exception as exc:
        logger.warning("engine download unusable (%s); trying cached copy", exc)
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
    try:
        data = cache.read_bytes()
        version = _validate(data)
        return _load_module(cache), f"cached {version}"
    except Exception as exc:
        raise EngineUnavailable(
            f"Could not reach {constants.ENGINE_URL} and no cached engine is "
            f"available ({exc}). Connect to the internet and retry."
        ) from exc

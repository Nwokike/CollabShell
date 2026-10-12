"""Router-engine tests.

The properties that matter, each one a bug DDGS hit in the field:

* **A download must prove it loads before it may replace the cache.** Passing
  the structural check is not enough — a version with the main guard and the
  VERSION token that fails to import would otherwise overwrite the
  last-known-good copy and then break the app.
* **No network and no cache is a loud, named failure**, never a silent None.
* **The User-Agent is load-bearing**: router.kiri.ng answers 403 to default
  library user-agents, so the app could never fetch its own engine without it.
"""

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from services import router_engine


def _run(coro):
    import asyncio

    return asyncio.run(coro)


def _patch_sleep(monkeypatch):
    """Make the download retry's 1s backoff instant."""

    async def instant(_s):
        return None

    monkeypatch.setattr(router_engine.asyncio, "sleep", instant)


# Structurally valid AND loadable — the only kind that may be cached, because
# load_engine proves a download loads before it replaces the cache.
GOOD = (
    b'VERSION = "1.2.3"\nif __name__ == "__main__":\n    pass\n'
    b"def acquire_server(base, span):\n    return None, base\n"
)
BAD_GUARD = b'VERSION = "1.2.3"\nx = 1\n'
BAD_VERSION = b'if __name__ == "__main__":\n    pass\n'
# Passes both structural checks, but cannot produce a module with the one
# contract the router needs.
NO_ACQUIRE = b'VERSION = "9.9.9"\nif __name__ == "__main__":\n    pass\n'
SYNTAX_ERROR = b'VERSION = "1.0.0"\nif __name__ == "__main__":\n    def (\n'


def _cache(tmp_path, monkeypatch):
    monkeypatch.setattr(
        router_engine, "engine_cache_path", lambda: tmp_path / "engine_local.py"
    )
    return tmp_path / "engine_local.py"


# ── _validate ────────────────────────────────────────────────────────────────


def test_validate_returns_a_printable_label():
    assert router_engine._validate(GOOD) == "1.2.3"


def test_validate_rejects_a_missing_main_guard():
    with pytest.raises(ValueError, match="main guard"):
        router_engine._validate(BAD_GUARD)


def test_validate_rejects_a_missing_version_token():
    with pytest.raises(ValueError, match="VERSION"):
        router_engine._validate(BAD_VERSION)


def test_the_label_is_stripped_to_what_is_safe_to_print():
    label = router_engine._validate(
        b'VERSION = "1.0.0; DROP TABLE "\nif __name__ == "__main__":\n    pass\n'
    )
    assert ";" not in label
    assert " " not in label
    assert label == "1.0.0DROPTABLE", label


# ── _load_module ─────────────────────────────────────────────────────────────


def test_an_unloadable_file_raises(tmp_path):
    path = tmp_path / "engine_local.py"
    path.write_bytes(SYNTAX_ERROR)
    with pytest.raises(SyntaxError):
        router_engine._load_module(path)


def test_the_engine_file_must_end_in_py(tmp_path):
    """spec_from_file_location returns no loader for an unrecognized suffix,
    which would reject a perfect download."""
    path = tmp_path / "engine.txt"
    path.write_bytes(NO_ACQUIRE)
    with pytest.raises(ImportError):
        router_engine._load_module(path)


def test_a_good_engine_loads_and_satisfies_the_contract(tmp_path):
    path = tmp_path / "engine_local.py"
    path.write_bytes(
        b'VERSION = "1.2.3"\nif __name__ == "__main__":\n    pass\n'
        b"def acquire_server(base, span):\n    return None, base\n"
    )
    module = router_engine._load_module(path)
    assert callable(module.acquire_server)


# ── load_engine ──────────────────────────────────────────────────────────────


def _patch_download(monkeypatch, data, raises=None):
    attempts = {"n": 0}

    async def fake(url):
        attempts["n"] += 1
        if raises is not None:
            raise raises
        return data

    monkeypatch.setattr(router_engine, "_download", fake)
    return attempts


def test_a_good_download_is_cached(tmp_path, monkeypatch):
    cache = _cache(tmp_path, monkeypatch)
    _patch_download(monkeypatch, GOOD)
    _module, how = _run(router_engine.load_engine())
    assert how == "fetched 1.2.3"
    assert cache.exists(), "a good download must be cached"


def test_a_download_that_cannot_load_does_not_replace_the_cache(tmp_path, monkeypatch):
    """The property this module exists for: a structurally-valid download that
    fails to import must leave the last-known-good copy alone."""
    cache = _cache(tmp_path, monkeypatch)
    cache.write_bytes(GOOD)  # the last-known-good copy
    _patch_download(monkeypatch, NO_ACQUIRE)
    _module, how = _run(router_engine.load_engine())
    assert how == "cached 1.2.3"
    assert cache.read_bytes() == GOOD, "the good cache must survive a bad download"


def test_no_network_and_no_cache_names_the_url(tmp_path, monkeypatch):
    _cache(tmp_path, monkeypatch)
    _patch_download(monkeypatch, None, raises=OSError("no route to host"))
    with pytest.raises(router_engine.EngineUnavailable) as exc:
        _run(router_engine.load_engine())
    assert "router.kiri.ng" in str(exc.value)


def test_a_transient_failure_retries_once_before_falling_back(tmp_path, monkeypatch):
    """A single blip must not fall through to the cache tier.

    Patches at the HTTP layer, not `_download` itself: replacing `_download`
    would bypass the retry loop entirely and the test would prove nothing.
    """
    cache = _cache(tmp_path, monkeypatch)
    cache.write_bytes(GOOD)
    attempts = {"n": 0}

    class FlakyClient:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **kw):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise OSError("blip")

            class Resp:
                status_code = 200
                content = GOOD

                def raise_for_status(self):
                    pass

            return Resp()

    _patch_sleep(monkeypatch)
    monkeypatch.setattr(router_engine.httpx, "AsyncClient", FlakyClient)
    _module, how = _run(router_engine.load_engine())
    assert attempts["n"] >= 2, "a transient failure must be retried"
    assert how == "fetched 1.2.3"


def test_the_download_sends_a_user_agent(monkeypatch):
    """router.kiri.ng answers 403 to default library user-agents, so without
    this header the app could never fetch its own engine at all."""
    seen = {}

    class FakeResponse:
        status_code = 200
        content = GOOD

        def raise_for_status(self):
            pass

    class FakeClient:
        def __init__(self, **kw):
            seen.update(kw)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **kw):
            seen["url"] = url
            seen.update(kw)
            return FakeResponse()

    monkeypatch.setattr(router_engine.httpx, "AsyncClient", FakeClient)
    out = _run(router_engine._download("https://router.kiri.ng/run.py"))
    assert out == GOOD
    assert seen["headers"]["User-Agent"].startswith("CollabShell/"), seen
    assert seen.get("http2") is False, "http2 must be off for this endpoint"

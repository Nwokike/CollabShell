"""Tests for the terminal client's credential re-read on reconnect —
the long-lived-client half of the 2.1.1 token heal.

No network: State.store is faked and create_terminal_ws_url is patched
where the client calls it (module-level import in terminal_client).
"""

import asyncio
import sys
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

sys.path.insert(0, "src")

from services.colab.terminal_client import ColabTerminalClient


def _client(session_name="s1", token="tok-old", base_url="https://8080-m.example.dev"):
    return ColabTerminalClient(
        "wss://old",
        on_stdout=lambda s: None,
        base_url=base_url,
        token=token,
        term_name="1",
        session_name=session_name,
    )


def _store_with(session):
    store = MagicMock()
    store.get = MagicMock(return_value=session)
    st = MagicMock()
    st.store = store
    return st


def _session_record(token="tok-fresh", url="https://8080-m.example.dev"):
    return NS(token=token, url=url)


def test_refresh_credentials_picks_up_fresh_token():
    client = _client()
    st = _store_with(_session_record())

    with patch("colab_cli.common.State", side_effect=lambda: st):
        changed = asyncio.run(client._refresh_cached_credentials())

    assert changed is True
    assert client.token == "tok-fresh"
    assert client.base_url == "https://8080-m.example.dev"


def test_refresh_credentials_noop_when_unchanged():
    client = _client(token="tok-fresh")
    st = _store_with(_session_record(token="tok-fresh"))

    with patch("colab_cli.common.State", side_effect=lambda: st):
        changed = asyncio.run(client._refresh_cached_credentials())

    assert changed is False
    assert client.token == "tok-fresh"


def test_refresh_credentials_skipped_without_session_name():
    client = _client()
    client.session_name = None

    changed = asyncio.run(client._refresh_cached_credentials())
    assert changed is False
    assert client.token == "tok-old"


def test_refresh_credentials_swallows_store_errors():
    client = _client()
    store = MagicMock()
    store.get = MagicMock(side_effect=RuntimeError("boom"))
    st = MagicMock()
    st.store = store

    with patch("colab_cli.common.State", side_effect=lambda: st):
        changed = asyncio.run(client._refresh_cached_credentials())

    assert changed is False


def test_reconnect_rebuilds_ws_url_with_fresh_token():
    """reconnect() must re-read the store and build the WS URL from the
    fresh token — then attempt the socket connection (patched)."""
    client = _client()
    st = _store_with(_session_record(token="tok-fresh"))

    async def _fake_connect(initial_rows=24, initial_cols=80):
        client._running = True

    built = {}

    def _fake_ws_url(raw_url, token, term_name=None):
        built["url"] = raw_url
        built["token"] = token
        return f"wss://rebuilt?t={token}"

    with (
        patch("colab_cli.common.State", side_effect=lambda: st),
        patch(
            "services.colab.terminal_client.create_terminal_ws_url",
            side_effect=_fake_ws_url,
        ),
        patch.object(ColabTerminalClient, "connect", side_effect=_fake_connect),
    ):
        ok = asyncio.run(client.reconnect())

    assert ok is True
    # The WS URL was rebuilt from the re-read (fresh) credentials.
    assert built["token"] == "tok-fresh"
    assert client.ws_url == "wss://rebuilt?t=tok-fresh"

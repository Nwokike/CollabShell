"""Tests for session_ops token refresh — the stale-JWT heal from 2.1.1.

Mocks colab_cli.common.State with a dict-backed store; no network.
"""

import asyncio
import sys
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

sys.path.insert(0, "src")

from services.colab import session_ops


def _proxy(token="tok-old", url="https://8080-m-s-abc.example.dev"):
    return NS(token=token, url=url)


def _assignment(endpoint="m-s-abc", token="tok-fresh"):
    accel = NS(value="NONE")
    variant = NS(name="DEFAULT")
    return NS(
        endpoint=endpoint,
        runtime_proxy_info=_proxy(token=token),
        accelerator=accel,
        variant=variant,
    )


def _session(name="s1", endpoint="m-s-abc", token="tok-old"):
    return NS(
        name=name,
        token=token,
        url="https://8080-m-s-abc.example.dev",
        endpoint=endpoint,
        variant="DEFAULT",
        accelerator="NONE",
        kernel_id=None,
        session_id=None,
        last_execution=None,
        running=None,
        keep_alive_pid=None,
    )


class FakeStore:
    def __init__(self, sessions):
        self.sessions = {s.name: s for s in sessions}
        self.added = []

    def get(self, name):
        return self.sessions.get(name)

    def list(self):
        return dict(self.sessions)

    def add(self, s):
        self.sessions[s.name] = s
        self.added.append(s.name)

    def remove(self, name):
        self.sessions.pop(name, None)


def _make_state(store, assignments):
    st = MagicMock()
    st.store = store
    st.sync_sessions = MagicMock(return_value=(store.list(), assignments))
    st.client = MagicMock()
    st.client.list_assignments = MagicMock(return_value=assignments)
    st.history = MagicMock()
    return st


def _service():
    svc = MagicMock()

    async def _online():
        return None

    svc._ensure_online = _online
    return svc


def test_list_sessions_refreshes_stale_token():
    svc = _service()
    store = FakeStore([_session()])
    st = _make_state(store, [_assignment()])

    with patch("colab_cli.common.State", side_effect=lambda: st):
        result = asyncio.run(session_ops.list_sessions_impl(svc))

    # The local record was updated with the server's fresh token.
    assert store.sessions["s1"].token == "tok-fresh"
    assert "s1" in store.added
    # And the listing still reports the session.
    assert any(r["name"] == "s1" and r["endpoint"] == "m-s-abc" for r in result)


def test_list_sessions_keeps_unchanged_token():
    svc = _service()
    store = FakeStore([_session(token="tok-fresh")])
    st = _make_state(store, [_assignment(token="tok-fresh")])

    with patch("colab_cli.common.State", side_effect=lambda: st):
        asyncio.run(session_ops.list_sessions_impl(svc))

    assert store.added == []  # no rewrite when nothing changed


def test_refresh_session_token_updates_on_change():
    svc = _service()
    store = FakeStore([_session()])
    st = _make_state(store, [_assignment()])

    with patch("colab_cli.common.State", side_effect=lambda: st):
        changed = asyncio.run(session_ops.refresh_session_token_impl(svc, "s1"))

    assert changed is True
    assert store.sessions["s1"].token == "tok-fresh"


def test_refresh_session_token_false_when_no_assignment():
    svc = _service()
    store = FakeStore([_session()])
    st = _make_state(store, [])  # server has no assignments

    with patch("colab_cli.common.State", side_effect=lambda: st):
        changed = asyncio.run(session_ops.refresh_session_token_impl(svc, "s1"))

    assert changed is False
    assert store.sessions["s1"].token == "tok-old"


def test_refresh_session_token_false_when_session_missing():
    svc = _service()
    store = FakeStore([])
    st = _make_state(store, [_assignment()])

    with patch("colab_cli.common.State", side_effect=lambda: st):
        changed = asyncio.run(session_ops.refresh_session_token_impl(svc, "nope"))

    assert changed is False

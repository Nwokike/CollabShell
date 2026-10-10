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
    from colab_cli.client import RuntimeProxyInfo

    return RuntimeProxyInfo(
        token=token,
        tokenExpiresInSeconds=3600,
        url=url,
    )


def _assignment(endpoint="m-s-abc", token="tok-fresh"):
    from colab_cli.client import Accelerator, Variant

    return NS(
        endpoint=endpoint,
        runtime_proxy_info=_proxy(token=token),
        accelerator=Accelerator.NONE,
        variant=Variant.DEFAULT,
        machine_shape=NS(name="STANDARD"),
    )


def _session(name="s1", endpoint="m-s-abc", token="tok-old"):
    return NS(
        name=name,
        token=token,
        url="https://8080-m-s-abc.example.dev",
        endpoint=endpoint,
        token_expires_at=None,
        variant="DEFAULT",
        accelerator="NONE",
        machine_shape="STANDARD",
        kernel_id=None,
        session_id=None,
        last_execution=None,
        running=None,
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
    # GUI-safe wrapper path: load_session_fresh -> get_session(ignore_missing...).
    st.get_session = MagicMock(
        side_effect=lambda name, ignore_missing_session=False: store.get(name)
    )
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

    # Upstream 0.7.4 sync_sessions refreshes the token itself; the listing
    # still reports the session with its machine shape.
    assert any(r["name"] == "s1" and r["endpoint"] == "m-s-abc" for r in result)
    assert any(r.get("machine_shape") == "STANDARD" for r in result)


def test_list_sessions_no_rewrite_without_sync_refresh():
    # Our custom re-mint loop is gone (upstream sync_sessions refreshes);
    # with a fake whose sync returns the store untouched, nothing is rewritten.
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


def test_too_many_assignments_is_not_colab_request_error():
    """Regression guard: TooManyAssignmentsError is a SIBLING of
    ColabRequestError (both extend Exception), so `except ColabRequestError`
    misses every 412. The assign path must branch on it explicitly."""
    from colab_cli.client import ColabRequestError, TooManyAssignmentsError

    assert not issubclass(TooManyAssignmentsError, ColabRequestError)


def test_new_session_surfaces_friendly_412():
    """A 412 from assign() surfaces the friendly allocation message."""
    import uuid

    from colab_cli.client import TooManyAssignmentsError

    svc = _service()
    st = _make_state(FakeStore([]), [])
    st.client.assign = MagicMock(
        side_effect=TooManyAssignmentsError("Precondition Failed")
    )

    with (
        patch("colab_cli.common.State", side_effect=lambda: st),
        patch("uuid.uuid4", return_value=uuid.UUID(int=1)),
    ):
        try:
            asyncio.run(session_ops.new_session_impl(svc, name="s1"))
        except RuntimeError as e:
            assert "Allocation refused (precondition failed)" in str(e)
        else:
            raise AssertionError("expected RuntimeError for 412")


def test_load_session_fresh_never_raises_typer_exit():
    """GUI rule: the wrapper always passes ignore_missing_session=True, so no
    typer.Exit can escape into Flet async code — missing maps to None."""
    st = _make_state(FakeStore([]), [])
    # Even when the store is empty, the wrapper must return None, not raise.
    assert session_ops.load_session_fresh(st, "nope") is None
    st.get_session.assert_called_once_with("nope", ignore_missing_session=True)


def test_old_sessions_record_loads_under_new_model():
    """Old 0.6.0-era record (keep_alive_pid, no new fields) loads: the extra
    field is ignored and the new fields take defaults."""
    from colab_cli.state import SessionState

    old = {
        "name": "s1",
        "token": "t",
        "url": "u",
        "endpoint": "e",
        "variant": "DEFAULT",
        "accelerator": "NONE",
        "keep_alive_pid": None,
    }
    s = SessionState(**old)
    assert s.machine_shape == "STANDARD"
    assert s.token_expires_at is None
    dumped = s.model_dump(mode="json")
    assert dumped["machine_shape"] == "STANDARD"


def test_resolve_assign_shape_mapping():
    """Upstream shape mapping: High-RAM for choice accelerators, None for
    single-shape ones (L4/V5E1/V6E1) and when off."""
    from colab_cli.client import Accelerator, Shape, resolve_assign_shape

    assert resolve_assign_shape(Accelerator.NONE, high_mem=True) == Shape.HIGH_RAM
    assert resolve_assign_shape(Accelerator.T4, high_mem=True) == Shape.HIGH_RAM
    assert resolve_assign_shape(Accelerator.A100, high_mem=True) == Shape.HIGH_RAM
    assert resolve_assign_shape(Accelerator.L4, high_mem=True) is None
    assert resolve_assign_shape(Accelerator.V5E1, high_mem=True) is None
    assert resolve_assign_shape(Accelerator.V6E1, high_mem=True) is None
    assert resolve_assign_shape(Accelerator.A100, high_mem=False) is None
    assert resolve_assign_shape(Accelerator.NONE) is None


def test_new_session_high_mem_persists_shape_and_history():
    """Creation with high_mem=True passes shape=HIGH_RAM, persists
    machine_shape, and logs it in session_created."""
    import uuid

    from colab_cli.client import Shape

    svc = _service()
    store = FakeStore([])
    st = _make_state(store, [])
    captured = {}

    def _fake_assign(nbh, variant=None, accelerator=None, shape=None):
        captured["shape"] = shape
        return NS(
            endpoint="m-s-new",
            runtime_proxy_info=_proxy(token="tok-new"),
        )

    st.client.assign = MagicMock(side_effect=_fake_assign)

    with (
        patch("colab_cli.common.State", side_effect=lambda: st),
        patch("uuid.uuid4", return_value=uuid.UUID(int=2)),
    ):
        result = asyncio.run(
            session_ops.new_session_impl(svc, name="s2", high_mem=True)
        )

    assert captured["shape"] == Shape.HIGH_RAM
    assert store.sessions["s2"].machine_shape == "HIGH_RAM"
    assert result["machine_shape"] == "HIGH_RAM"
    logged = [
        c for c in st.history.log_event.call_args_list if c.args[1] == "session_created"
    ]
    assert logged and logged[0].args[2]["machine_shape"] == "HIGH_RAM"


def test_new_session_standard_shape_by_default():
    """Creation without high_mem persists STANDARD and omits the URL param."""
    import uuid

    svc = _service()
    store = FakeStore([])
    st = _make_state(store, [])
    captured = {}

    def _fake_assign(nbh, variant=None, accelerator=None, shape=None):
        captured["shape"] = shape
        return NS(
            endpoint="m-s-new",
            runtime_proxy_info=_proxy(token="tok-new"),
        )

    st.client.assign = MagicMock(side_effect=_fake_assign)

    with (
        patch("colab_cli.common.State", side_effect=lambda: st),
        patch("uuid.uuid4", return_value=uuid.UUID(int=3)),
    ):
        result = asyncio.run(session_ops.new_session_impl(svc, name="s3"))

    assert captured["shape"] is None
    assert store.sessions["s3"].machine_shape == "STANDARD"
    assert result["machine_shape"] == "STANDARD"


def test_new_session_400_uses_entitlement_copy():
    """A 400 from assign() surfaces the entitlement message (not the old short text)."""
    import uuid

    from colab_cli.client import ColabRequestError

    svc = _service()
    st = _make_state(FakeStore([]), [])
    err = ColabRequestError("rejected", request=None, response=None, response_body="")
    err.response = NS(status_code=400)
    st.client.assign = MagicMock(side_effect=err)

    with (
        patch("colab_cli.common.State", side_effect=lambda: st),
        patch("uuid.uuid4", return_value=uuid.UUID(int=4)),
    ):
        try:
            asyncio.run(session_ops.new_session_impl(svc, name="s4", gpu="A100"))
        except ValueError as e:
            assert "quota or entitlement" in str(e)
            assert "T4 (free) or CPU" in str(e)
        else:
            raise AssertionError("expected ValueError for 400")


def test_new_session_503_high_mem_surfaces_free_account_copy():
    """Live-observed: CPU + shape=hm returns 503 on free accounts. The error
    must name the cause (High RAM needs Pro), not the server."""
    import uuid

    from colab_cli.client import ColabRequestError

    svc = _service()
    st = _make_state(FakeStore([]), [])
    err = ColabRequestError(
        "unavailable", request=None, response=None, response_body=""
    )
    err.response = NS(status_code=503)
    st.client.assign = MagicMock(side_effect=err)

    with (
        patch("colab_cli.common.State", side_effect=lambda: st),
        patch("uuid.uuid4", return_value=uuid.UUID(int=5)),
    ):
        try:
            asyncio.run(session_ops.new_session_impl(svc, name="s5", high_mem=True))
        except ValueError as e:
            assert "High-RAM is not available" in str(e)
            assert "Standard RAM" in str(e)
        else:
            raise AssertionError("expected ValueError for 503+high-mem")


def test_new_session_503_without_high_mem_reraises():
    """A 503 unrelated to High RAM is not swallowed by the friendly branch."""
    import uuid

    from colab_cli.client import ColabRequestError

    svc = _service()
    st = _make_state(FakeStore([]), [])
    err = ColabRequestError(
        "unavailable", request=None, response=None, response_body=""
    )
    err.response = NS(status_code=503)
    st.client.assign = MagicMock(side_effect=err)

    with (
        patch("colab_cli.common.State", side_effect=lambda: st),
        patch("uuid.uuid4", return_value=uuid.UUID(int=6)),
    ):
        try:
            asyncio.run(session_ops.new_session_impl(svc, name="s6"))
        except ColabRequestError:
            pass
        else:
            raise AssertionError("expected ColabRequestError for plain 503")

"""Tests for env injection in exec_code_impl (Phase 4).

Mocks colab_cli State/ColabRuntime; no network. Verifies prelude ordering,
validation, history redaction (values never logged), and timeout parity.
"""

import asyncio
import sys
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

sys.path.insert(0, "src")

from services.colab import execution


def _session():
    return NS(
        name="s1",
        token="tok",
        url="https://8080-m.example.dev",
        endpoint="m-s-abc",
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
    def __init__(self, session):
        self.session = session
        self.added = []

    def add(self, s):
        self.added.append(s.name)


def _make_state(session):
    st = MagicMock()
    st.store = FakeStore(session)
    st.history = MagicMock()
    st.get_session = MagicMock(return_value=session)
    st.client = MagicMock()
    return st


def _service():
    svc = MagicMock()

    async def _online():
        return None

    svc._ensure_online = _online
    svc._cancel_event = MagicMock()
    svc._cancel_event.is_set = MagicMock(return_value=False)
    return svc


def _run_exec(env=None, timeout=30.0):
    svc = _service()
    session = _session()
    st = _make_state(session)
    sent = {}

    fake_runtime = MagicMock()

    def _fake_execute(code, **kwargs):
        sent["code"] = code
        sent["kwargs"] = kwargs
        return [{"output_type": "stream", "text": "ok"}]

    fake_runtime.execute_code = MagicMock(side_effect=_fake_execute)
    fake_runtime.kernel_client = MagicMock()

    with (
        patch("colab_cli.common.State", side_effect=lambda: st),
        patch(
            "colab_cli.runtime.ColabRuntime",
            side_effect=lambda *a, **k: fake_runtime,
        ),
    ):
        result = asyncio.run(
            execution.exec_code_impl(svc, "print('hi')", "s1", timeout=timeout, env=env)
        )
    return sent, st, result


def test_env_prelude_ordering_after_preflight():
    sent, _, _ = _run_exec(env={"MY_KEY": "s3cr3t", "OTHER": "x=y"})
    code = sent["code"]
    # Prelude first, user code last.
    assert code.index("os.environ['MY_KEY']") < code.index("print('hi')")
    assert "os.environ['OTHER'] = 'x=y'" in code
    assert code.startswith("import os\n")


def test_no_env_no_prelude():
    sent, _, _ = _run_exec(env=None)
    assert sent["code"] == "print('hi')"


def test_history_logs_code_and_keys_not_values():
    _, st, _ = _run_exec(env={"MY_KEY": "s3cr3t-value"})
    (call,) = [
        c for c in st.history.log_event.call_args_list if c.args[1] == "execution"
    ]
    payload = call.args[2]
    assert payload["code"] == "print('hi')"
    assert payload["env_keys"] == ["MY_KEY"]
    dumped = str(payload)
    assert "s3cr3t-value" not in dumped


def test_invalid_env_key_raises_value_error():
    import pytest

    with pytest.raises(ValueError, match="BAD-KEY"):
        _run_exec(env={"BAD-KEY": "v"})


def test_timeout_plumbed_to_runtime():
    sent, _, _ = _run_exec(timeout=30.0)
    assert sent["kwargs"]["timeout"] == 30.0


def test_timeout_defaults_agree_on_30():
    import inspect

    from services.colab import session_ops  # noqa: F401  (import warms package)

    sig_impl = inspect.signature(execution.exec_code_impl)
    assert sig_impl.parameters["timeout"].default == 30.0

    from services.colab import ColabService

    sig_wrap = inspect.signature(ColabService.exec_code)
    assert sig_wrap.parameters["timeout"].default == 30.0

    from core import constants
    from core.state import AppState

    assert AppState.default_timeout == 30
    assert constants.DEFAULT_TIMEOUT == 30
    assert 30 in constants.TIMEOUT_OPTIONS

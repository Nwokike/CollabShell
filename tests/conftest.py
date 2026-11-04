"""Shared test setup: the import path, the singleton restore, and one filter."""

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def pytest_collection_modifyitems(items):
    """Filter one Windows teardown artefact for every test.

    `WinError 10038` comes from a serve-forever thread parked in `select()` when
    its socket is closed underneath it by a test's teardown. The thread is a
    daemon and the test has already passed, so it is a platform artefact, not a
    fault. It has to be applied to every item because the exception surfaces in
    whichever test happens to be running when the stale thread wakes — usually a
    later file than the one that started the server, which is why a per-module
    filter misses it.
    """
    marker = pytest.mark.filterwarnings(
        "ignore:.*10038.*:pytest.PytestUnhandledThreadExceptionWarning"
    )
    for item in items:
        item.add_marker(marker)


@pytest.fixture(autouse=True)
def _restore_process_globals():
    """Snapshot and restore the singletons every test shares.

    `core.state.state`, `model_catalog`'s catalog and `router`'s module state
    are process-wide, and real code writes them: `ensure_router()` publishes a
    status, `refresh_catalog()` installs rows and adopts a default model, a turn
    marks a model's circuit. So one test's side effect changes the next test's
    starting point.

    That is not hypothetical: it has produced three separate failures that pass
    in isolation and fail in a full run — a leaked `ai_router_port` changing
    `_publish_status`'s change detection, a leaked router status flipping the
    model pill's label, and a leaked `ai_model` changing `turn_candidates`'
    order. Each was "fixed" by restoring state in the offending test file, which
    only holds until the next file writes it.

    Restoring here means a test may use the real code paths without every author
    having to remember the cleanup, and no file depends on being run alone.
    """
    from core.state import state

    saved_state = {
        field: getattr(state, field)
        for field in (
            "ai_model",
            "ai_thinking",
            "ai_router_url",
            "ai_router_status",
            "ai_router_port",
            "credits_revision",
        )
        if hasattr(state, field)
    }

    from services import model_catalog

    saved_catalog = list(model_catalog._catalog)
    saved_fetched_at = model_catalog._catalog_fetched_at

    from services import router

    with router._router_lock:
        saved_router = (router._router_server, router._router_port)
    saved_miss_until = router._probe_miss_until
    saved_failed_until = router._router_failed_until

    yield

    for field, value in saved_state.items():
        setattr(state, field, value)
    model_catalog._catalog = saved_catalog
    model_catalog._catalog_fetched_at = saved_fetched_at
    model_catalog.reset_circuits()
    with router._router_lock:
        router._router_server, router._router_port = saved_router
    router._probe_miss_until = saved_miss_until
    router._router_failed_until = saved_failed_until

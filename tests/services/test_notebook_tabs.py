"""M3 tests: multi-notebook tabs — storage isolation, legacy migration, cleanup."""

import sys

sys.path.insert(0, "src")


def _storage():
    import asyncio as _aio
    import tempfile
    from pathlib import Path

    from services.storage_service import StorageService

    svc = StorageService.__new__(StorageService)

    tmp = Path(tempfile.mkdtemp(prefix="nb_tabs_"))
    import services.storage_service as mod

    orig_dir = mod._STORAGE_DIR
    mod._STORAGE_DIR = tmp
    svc._data = {}

    svc._lock = _aio.Lock()
    svc._dirty = False
    svc._last_write = 0.0
    svc._pending_write_task = None
    return svc, mod, orig_dir


def test_per_tab_save_load_isolation():
    import asyncio

    svc, mod, orig = _storage()
    try:
        asyncio.run(svc.save_notebook("s1", [{"id": "a"}], "nb1"))
        asyncio.run(svc.save_notebook("s1", [{"id": "b"}], "nb2"))
        one = asyncio.run(svc.load_notebook("s1", "nb1"))
        two = asyncio.run(svc.load_notebook("s1", "nb2"))
        assert [c["id"] for c in one] == ["a"]
        assert [c["id"] for c in two] == ["b"]
    finally:
        mod._STORAGE_DIR = orig


def test_legacy_file_migrates_to_default_tab():
    import asyncio

    svc, mod, orig = _storage()
    try:
        asyncio.run(svc.save_notebook("s1", [{"id": "legacy"}]))
        loaded = asyncio.run(svc.load_notebook("s1", "nb1"))
        assert [c["id"] for c in loaded] == ["legacy"]
        # Migration persists the per-tab file too.
        again = asyncio.run(svc.load_notebook("s1", "nb1"))
        assert [c["id"] for c in again] == ["legacy"]
    finally:
        mod._STORAGE_DIR = orig


def test_list_notebooks_returns_tab_ids():
    import asyncio

    svc, mod, orig = _storage()
    try:
        asyncio.run(svc.save_notebook("s1", [{"id": "a"}], "nb1"))
        asyncio.run(svc.save_notebook("s1", [{"id": "b"}], "nb2"))
        asyncio.run(svc.save_notebook("other", [{"id": "x"}], "nb1"))
        ids = asyncio.run(svc.list_notebooks("s1"))
        assert sorted(ids) == ["nb1", "nb2"]
    finally:
        mod._STORAGE_DIR = orig


def test_orphan_cleanup_keeps_live_tab_files():
    import asyncio

    svc, mod, orig = _storage()
    try:
        asyncio.run(svc.save_notebook("s1", [{"id": "a"}], "nb1"))
        asyncio.run(svc.save_notebook("dead", [{"id": "z"}], "nb9"))
        asyncio.run(svc.cleanup_orphaned_notebooks(["s1"]))
        assert asyncio.run(svc.load_notebook("s1", "nb1")) != []
        assert asyncio.run(svc.load_notebook("dead", "nb9")) == []
    finally:
        mod._STORAGE_DIR = orig


def test_delete_notebook_removes_only_that_tab():
    import asyncio

    svc, mod, orig = _storage()
    try:
        asyncio.run(svc.save_notebook("s1", [{"id": "a"}], "nb1"))
        asyncio.run(svc.save_notebook("s1", [{"id": "b"}], "nb2"))
        asyncio.run(svc.delete_notebook("s1", "nb1"))
        assert asyncio.run(svc.load_notebook("s1", "nb1")) == []
        assert [c["id"] for c in asyncio.run(svc.load_notebook("s1", "nb2"))] == ["b"]
    finally:
        mod._STORAGE_DIR = orig

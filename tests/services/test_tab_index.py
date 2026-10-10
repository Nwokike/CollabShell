"""Phase 1 tests: tab identity — index sidecar, names/order, rename, migration.

Covers the storage side (save/load index, glob fallback, orphan cleanup) and
the CellData AI-readiness fields (origin/tool_call_id omitted at defaults).
"""

import sys

sys.path.insert(0, "src")


def _storage():
    import asyncio as _aio
    import tempfile
    from pathlib import Path

    from services.storage_service import StorageService

    svc = StorageService.__new__(StorageService)

    tmp = Path(tempfile.mkdtemp(prefix="tab_index_"))
    import services.storage_service as mod

    orig_dir = mod._STORAGE_DIR
    mod._STORAGE_DIR = tmp
    svc._data = {}

    svc._lock = _aio.Lock()
    svc._dirty = False
    svc._last_write = 0.0
    svc._pending_write_task = None
    return svc, mod, orig_dir


# ── Index sidecar ───────────────────────────────────────────────────────────


def test_index_roundtrip_preserves_order_names_and_view():
    import asyncio

    svc, mod, orig = _storage()
    try:
        tabs = [
            {"id": "nb2", "name": "Lesson 2", "view": "script"},
            {"id": "nb1", "name": "Lesson 1", "view": "notebook"},
        ]
        asyncio.run(svc.save_tab_index("s1", tabs))
        loaded = asyncio.run(svc.load_tab_index("s1"))
        assert loaded is not None
        assert [t["id"] for t in loaded] == ["nb2", "nb1"]
        assert loaded[0]["name"] == "Lesson 2"
        assert loaded[0]["view"] == "script"
        # Missing view defaults to notebook.
        assert loaded[1]["view"] == "notebook"
    finally:
        mod._STORAGE_DIR = orig


def test_index_is_none_when_never_written():
    import asyncio

    svc, mod, orig = _storage()
    try:
        assert asyncio.run(svc.load_tab_index("never")) is None
    finally:
        mod._STORAGE_DIR = orig


def test_index_defaults_view_and_rejects_blank_ids():
    import asyncio

    svc, mod, orig = _storage()
    try:
        asyncio.run(
            svc.save_tab_index("s1", [{"id": "nb1", "name": "A"}, {"id": "", "name": "x"}])
        )
        loaded = asyncio.run(svc.load_tab_index("s1"))
        assert [t["id"] for t in loaded] == ["nb1"]
        assert loaded[0]["view"] == "notebook"
    finally:
        mod._STORAGE_DIR = orig


def test_index_uses_index_filename_not_per_tab_files():
    import asyncio

    svc, mod, orig = _storage()
    try:
        asyncio.run(svc.save_notebook("s1", [{"id": "a"}], "nb1"))
        asyncio.run(svc.save_tab_index("s1", [{"id": "nb1", "name": "A"}]))
        # Both files exist and neither clobbers the other.
        assert (mod._STORAGE_DIR / "notebook_s1__nb1.json").exists()
        assert (mod._STORAGE_DIR / "notebook_s1__index.json").exists()
        cells = asyncio.run(svc.load_notebook("s1", "nb1"))
        assert [c["id"] for c in cells] == ["a"]
    finally:
        mod._STORAGE_DIR = orig


# ── list_notebooks: index order, glob fallback ──────────────────────────────


def test_list_notebooks_prefers_index_order():
    import asyncio

    svc, mod, orig = _storage()
    try:
        asyncio.run(svc.save_notebook("s1", [{"id": "a"}], "nb1"))
        asyncio.run(svc.save_notebook("s1", [{"id": "b"}], "nb2"))
        asyncio.run(
            svc.save_tab_index(
                "s1",
                [{"id": "nb2", "name": "B"}, {"id": "nb1", "name": "A"}],
            )
        )
        # Index order wins over the glob's alphabetical sort.
        assert asyncio.run(svc.list_notebooks("s1")) == ["nb2", "nb1"]
    finally:
        mod._STORAGE_DIR = orig


def test_list_notebooks_falls_back_to_glob_without_index():
    import asyncio

    svc, mod, orig = _storage()
    try:
        asyncio.run(svc.save_notebook("s1", [{"id": "a"}], "nb1"))
        asyncio.run(svc.save_notebook("s1", [{"id": "b"}], "nb2"))
        # No index: glob path must still find the tabs, and must NOT report the
        # index sidecar itself as a tab.
        assert asyncio.run(svc.list_notebooks("s1")) == ["nb1", "nb2"]
    finally:
        mod._STORAGE_DIR = orig


def test_index_alone_does_not_break_listing():
    import asyncio

    svc, mod, orig = _storage()
    try:
        asyncio.run(svc.save_tab_index("s1", [{"id": "nb1", "name": "A"}]))
        # Index with no per-tab file: the index entry is still the source of
        # truth for what tabs exist.
        assert asyncio.run(svc.list_notebooks("s1")) == ["nb1"]
    finally:
        mod._STORAGE_DIR = orig


# ── Orphan cleanup ──────────────────────────────────────────────────────────


def test_cleanup_keeps_index_for_live_session():
    import asyncio

    svc, mod, orig = _storage()
    try:
        asyncio.run(svc.save_notebook("s1", [{"id": "a"}], "nb1"))
        asyncio.run(svc.save_tab_index("s1", [{"id": "nb1", "name": "A"}]))
        asyncio.run(svc.save_notebook("dead", [{"id": "z"}], "nb9"))
        asyncio.run(svc.save_tab_index("dead", [{"id": "nb9", "name": "Z"}]))
        asyncio.run(svc.cleanup_orphaned_notebooks(["s1"]))
        assert asyncio.run(svc.load_tab_index("s1")) is not None
        assert asyncio.run(svc.load_tab_index("dead")) is None
    finally:
        mod._STORAGE_DIR = orig


def test_cleanup_empty_list_still_skips():
    import asyncio

    svc, mod, orig = _storage()
    try:
        asyncio.run(svc.save_tab_index("s1", [{"id": "nb1", "name": "A"}]))
        asyncio.run(svc.cleanup_orphaned_notebooks([]))
        assert asyncio.run(svc.load_tab_index("s1")) is not None
    finally:
        mod._STORAGE_DIR = orig


# ── CellData AI-readiness ───────────────────────────────────────────────────


def test_cell_defaults_omit_origin_and_tool_call_id():
    from components.notebook_cell import CellData

    d = CellData(cell_id="c1", source="x = 1").to_dict()
    assert "origin" not in d
    assert "tool_call_id" not in d


def test_cell_roundtrip_preserves_origin_and_tool_call_id():
    from components.notebook_cell import CellData

    cell = CellData(
        cell_id="c1",
        source="x = 1",
        origin="assistant",
        tool_call_id="call_abc123",
    )
    d = cell.to_dict()
    assert d["origin"] == "assistant"
    assert d["tool_call_id"] == "call_abc123"

    restored = CellData.from_dict(d)
    assert restored.origin == "assistant"
    assert restored.tool_call_id == "call_abc123"


def test_cell_from_dict_defaults_origin_to_user():
    from components.notebook_cell import CellData

    restored = CellData.from_dict({"id": "c1", "type": "code", "source": "x"})
    assert restored.origin == "user"
    assert restored.tool_call_id is None


def test_cell_to_dict_of_legacy_dict_is_byte_compatible():
    """A pre-Phase-1 file must serialize back to exactly what it was."""
    from components.notebook_cell import CellData

    legacy = {
        "id": "c1",
        "type": "code",
        "source": "x = 1",
        "outputs": [],
        "is_running": False,
        "is_editing": False,
    }
    assert CellData.from_dict(legacy).to_dict() == legacy


def test_cell_blank_origin_normalizes_to_user():
    from components.notebook_cell import CellData

    assert CellData(cell_id="c1", origin="").origin == "user"
    assert CellData(cell_id="c1", origin=None).origin == "user"


# ── Notebook view wiring (source-level guards) ─────────────────────────────


def test_notebook_view_exposes_insert_cells_and_rename():
    import pathlib

    src = pathlib.Path("src/screens/session/notebook_view.py").read_text(
        encoding="utf-8"
    )
    # Stable insertion path for the Phase 4 Assistant bridge.
    assert "def _insert_cells(" in src
    assert '"insert_cells": _insert_cells' in src
    # Rename flows: dialog + action + long-press.
    assert "def _show_rename_dialog(" in src
    assert '"rename_notebook"' in src
    assert "on_long_press=lambda e, tid=tab[\"id\"]: _show_rename_dialog(tid)" in src
    # Index sidecar is written on create/close and at restore.
    assert "def _save_index()" in src
    assert src.count("_save_index()") >= 4  # def + create + close + load paths


def test_tab_dicts_carry_view_preference():
    import pathlib

    src = pathlib.Path("src/screens/session/notebook_view.py").read_text(
        encoding="utf-8"
    )
    # Tabs keep a view field so Phase 3's script mode can persist per tab.
    assert '"view": view or "notebook"' in src
    assert '"view": meta.get("view") or "notebook"' in src

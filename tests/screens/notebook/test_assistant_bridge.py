"""Assistant → notebook bridges: writing cells, tagging them, revealing them.

The tap-through is the property that matters: a step row points at cells the
assistant wrote, tapping it must land the user on that cell in an editable
state — so they take over where the AI stopped. Everything else here is the
machinery that makes that exact rather than approximate.
"""

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from components.notebook_cell import CellData
from screens.session import notebook_view


def _fresh_bridges(tab_id="tab-1"):
    """Register a fake mounted notebook and return its bridge registry."""
    tabs = [
        {"id": tab_id, "name": "Notebook", "view": "notebook",
         "cells": [CellData(cell_type="code", source="print(1)")]},
        {"id": "tab-2", "name": "Other", "view": "notebook",
         "cells": [CellData(cell_type="code", source="print(2)")]},
    ]
    focused = []
    switched = []

    bridges = {
        "insert_cells": lambda tid, cells, at_end=True: (
            tabs[0]["cells"].extend(cells), cells)[1] if tid == tab_id else None,
        "active_tab_id": lambda: tab_id,
        "switch_tab": switched.append,
        "focus_cell": focused.append,
        "locate_cell": lambda cid: next(
            ((t["id"], i) for t in tabs for i, c in enumerate(t["cells"])
             if c.id == cid), None
        ),
    }
    notebook_view._SESSION_BRIDGES["sess"] = bridges
    return tabs, bridges, focused, switched


def _teardown():
    notebook_view._SESSION_BRIDGES.pop("sess", None)


# ── write + origin tagging ───────────────────────────────────────────────────


def test_write_cells_tags_the_cells_as_assistant_written():
    _fresh_bridges()
    try:
        inserted = notebook_view.write_cells_to_active_tab(
            "sess",
            [{"type": "code", "source": "x = 1"}, {"type": "markdown", "source": "# hi"}],
        )
        assert inserted and len(inserted) == 2
        assert all(c.origin == "assistant" for c in inserted), (
            "AI-written cells must be tagged so the UI can tell them apart"
        )
    finally:
        _teardown()


def test_write_cells_is_a_no_op_when_no_tab_is_open():
    """No session mounted means no bridge, and the caller learns that rather
    than the tool pretending it wrote something."""
    assert notebook_view.write_cells_to_active_tab("nope", [{"type": "code", "source": "x"}]) is None


def test_write_cells_rejects_malformed_entries_without_blowing_up():
    _fresh_bridges()
    try:
        inserted = notebook_view.write_cells_to_active_tab(
            "sess", [{"type": "code", "source": "x"}, "not-a-dict", None]
        )
        assert inserted is not None and len(inserted) == 1
    finally:
        _teardown()


def test_origin_survives_a_notebook_round_trip():
    """The tag is on the saved cell, not just the live object — otherwise
    reopening the notebook loses who wrote the cell."""
    cell = CellData.from_dict({"type": "code", "source": "x", "origin": "assistant"})
    assert cell.to_dict()["origin"] == "assistant"
    # A default (user-written) cell stays byte-identical: the field is omitted.
    assert "origin" not in CellData(cell_type="code", source="y").to_dict()


# ── step → cell tap-through ──────────────────────────────────────────────────


def test_revealing_a_cell_in_the_active_tab_focuses_it():
    tabs, _, focused, switched = _fresh_bridges()
    try:
        target = tabs[0]["cells"][0].id
        assert notebook_view.reveal_cell("sess", target) is True
        assert focused == [target], "the cell must be brought into view"
        assert switched == [], "the active tab must not be switched for no reason"
    finally:
        _teardown()


def test_revealing_a_cell_in_another_tab_switches_first():
    tabs, _, focused, switched = _fresh_bridges()
    try:
        target = tabs[1]["cells"][0].id
        assert notebook_view.reveal_cell("sess", target) is True
        assert switched == ["tab-2"], "a cell in another tab requires switching"
        assert focused == [target], "and still focusing the cell"
    finally:
        _teardown()


def test_revealing_a_deleted_cell_reports_false_and_switches_nothing():
    _, _, focused, switched = _fresh_bridges()
    try:
        assert notebook_view.reveal_cell("sess", "gone-forever") is False
        assert switched == [], "a stale tap must not yank the user elsewhere"
        assert focused == []
    finally:
        _teardown()


def test_revealing_without_a_mounted_session_is_false():
    assert notebook_view.reveal_cell("not-mounted", "abc") is False


# ── in-cell AI insertion (M5) ─────────────────────────────────────────────


def test_insert_after_puts_the_answer_directly_under_the_cell():
    """An answer must land next to the question, not at the end of the
    notebook."""
    from components.notebook_cell import CellData

    tab = {"id": "t", "cells": [CellData(cell_type="code", source="a")]}
    anchor = tab["cells"][0].id
    answer = CellData(cell_type="code", source="x = 2")
    merged = notebook_view.insert_cells_into(tab, [answer], after_id=anchor)
    assert merged is not None
    assert [c.id for c in merged] == [anchor, answer.id]
    assert merged[1].source == "x = 2"


def test_insert_after_a_missing_anchor_falls_back_to_the_end():
    """A stale id cannot raise — it just appends, which is still useful."""
    from components.notebook_cell import CellData

    tab = {"id": "t", "cells": [CellData(cell_type="code", source="a")]}
    answer = CellData(cell_type="code", source="x = 2")
    merged = notebook_view.insert_cells_into(tab, [answer], after_id="gone")
    assert merged[-1].id == answer.id


def test_insert_after_a_middle_cell_lands_between_its_neighbours():
    from components.notebook_cell import CellData

    first = CellData(cell_type="code", source="a")
    second = CellData(cell_type="code", source="b")
    tab = {"id": "t", "cells": [first, second]}
    answer = CellData(cell_type="code", source="answer")
    merged = notebook_view.insert_cells_into(tab, [answer], after_id=first.id)
    assert [c.source for c in merged] == ["a", "answer", "b"]


def test_insert_at_end_and_at_start_still_work():
    from components.notebook_cell import CellData

    tab = {"id": "t", "cells": [CellData(cell_type="code", source="a")]}
    assert notebook_view.insert_cells_into(tab, [CellData(source="b")])[-1].source == "b"
    fresh = {"id": "t", "cells": [CellData(cell_type="code", source="a")]}
    assert notebook_view.insert_cells_into(fresh, [CellData(source="z")], at_end=False)[0].source == "z"


def test_insert_into_a_missing_tab_or_empty_list_returns_none():
    assert notebook_view.insert_cells_into(None, [object()]) is None
    assert notebook_view.insert_cells_into({"id": "t", "cells": []}, []) is None


def test_an_ai_answer_cell_is_tagged_and_editable():
    from components.notebook_cell import CellData

    cell = CellData(cell_type="code", source="x = 2", origin="assistant")
    assert cell.origin == "assistant"
    assert cell.is_editing is False  # the caller turns this on for code answers

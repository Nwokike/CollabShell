"""Phase 3 — the Assistant working on the notebook that is on screen.

The bridge is faked here the way `NotebookView` builds the real one: a
plain object with the five operations the model can reach. What matters
is that reads are free, writes ask, and a detached notebook disappears
from the catalog instead of pointing at a dead view.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ai.cell_sheet import build_question
from ai.notebook_bridge import NotebookBridge
from ai.system_prompt import build_system_prompt
from ai.tools import (
    AUTO,
    CONFIRM,
    NOTEBOOK_SCHEMAS,
    NOTEBOOK_TIERS,
    TIERS,
    TOOL_SCHEMAS,
    ToolBox,
    label_for,
    schemas_for,
)
from components.notebook_cell.actions import (
    error_to_text,
    has_error,
    outputs_to_text,
)


class FakeNotebook:
    """The live list, the way NotebookView holds it."""

    def __init__(self, cells=None):
        self.cells_list = list(cells or [{"type": "code", "source": "print(1)"}])
        self.alive = True
        self.writes: list[tuple] = []

    def bridge(self) -> NotebookBridge:
        return NotebookBridge(
            "work",
            lambda: list(self.cells_list),
            self._read,
            self._set,
            self._insert,
            self._run,
            alive=lambda: self.alive,
        )

    def _read(self, ref):
        return f"Cell {ref}:\n\n```\n{self.cells_list[int(ref) - 1]['source']}\n```"

    def _set(self, ref, source):
        self.writes.append(("set", int(ref), source))
        self.cells_list[int(ref) - 1]["source"] = source
        return f"Cell {ref} now holds {len(source.splitlines())} lines."

    def _insert(self, after_ref, cell_type, source):
        self.writes.append(("insert", after_ref, cell_type, source))
        at = int(after_ref) if after_ref is not None else len(self.cells_list)
        self.cells_list.insert(at, {"type": cell_type, "source": source})
        return f"Added a {cell_type} cell."

    async def _run(self, ref):
        self.writes.append(("run", int(ref)))
        return f"Cell {ref} output:\nhello"


def _box(notebook=None):
    return ToolBox(None, notebook.bridge() if notebook else None)


# ── Catalog ────────────────────────────────────────────────────────────


def test_notebook_tools_appear_only_with_a_notebook():
    without = {s["function"]["name"] for s in schemas_for(False)}
    with_it = {s["function"]["name"] for s in schemas_for(True)}
    assert without == {s["function"]["name"] for s in TOOL_SCHEMAS}
    assert "set_cell_source" not in without
    assert "set_cell_source" in with_it
    assert len(with_it) == len(without) + len(NOTEBOOK_SCHEMAS)


def test_reads_are_free_and_writes_ask():
    assert NOTEBOOK_TIERS["list_cells"] == AUTO
    assert NOTEBOOK_TIERS["read_cell"] == AUTO
    for name in ("set_cell_source", "insert_cell", "run_cell"):
        assert NOTEBOOK_TIERS[name] == CONFIRM
        assert TIERS[name] == CONFIRM
    for schema in NOTEBOOK_SCHEMAS:
        fn = schema["function"]
        params = fn["parameters"]
        assert fn["description"]
        assert set(params["required"]) <= set(params["properties"])


def test_notebook_labels_read_like_plain_english():
    assert label_for("set_cell_source", {"cell": 3}) == "Rewriting cell 3"
    assert label_for("read_cell", {"cell": 1}) == "Reading cell 1"
    assert label_for("run_cell", {"cell": 2}) == "Running cell 2"
    assert label_for("insert_cell", {"after": 2}) == "Adding a cell after 2"
    assert label_for("insert_cell", {}) == "Adding a cell"
    assert label_for("list_cells", {}) == "Reading the notebook"


# ── Bridge behavior ────────────────────────────────────────────────────


def test_read_tools_report_the_real_notebook():
    box = _box(
        FakeNotebook(
            [
                {"type": "code", "source": "x = 1"},
                {"type": "markdown", "source": "# hi"},
            ]
        )
    )
    listing = asyncio.run(box.run("list_cells", {}))
    assert "1. [code] x = 1" in listing.text
    assert "2. [markdown] # hi" in listing.text
    read = asyncio.run(box.run("read_cell", {"cell": 2}))
    assert "# hi" in read.text


def test_write_tools_change_the_live_cells():
    nb = FakeNotebook()
    box = _box(nb)
    asyncio.run(box.run("set_cell_source", {"cell": 1, "source": "y = 2"}))
    assert nb.cells_list[0]["source"] == "y = 2"
    asyncio.run(box.run("insert_cell", {"after": 1, "source": "z = 3"}))
    assert nb.cells_list[1]["source"] == "z = 3"
    result = asyncio.run(box.run("run_cell", {"cell": 1}))
    assert "hello" in result.text
    assert ("run", 1) in nb.writes


def test_insert_at_the_end_without_an_anchor():
    nb = FakeNotebook()
    box = _box(nb)
    asyncio.run(box.run("insert_cell", {"cell_type": "markdown", "source": "# end"}))
    assert nb.cells_list[-1] == {"type": "markdown", "source": "# end"}


def test_bad_cell_numbers_are_explained_not_raised():
    box = _box(FakeNotebook())
    for name, args in (
        ("read_cell", {"cell": 99}),
        ("run_cell", {"cell": 0}),
        ("set_cell_source", {"cell": "two", "source": "x"}),
    ):
        text = asyncio.run(box.run(name, args)).text
        assert text and "cell" in text.lower()


def test_empty_writes_are_refused():
    nb = FakeNotebook()
    box = _box(nb)
    assert (
        "empty"
        in asyncio.run(box.run("set_cell_source", {"cell": 1, "source": "   "})).text
    )
    assert "empty" in asyncio.run(box.run("insert_cell", {"source": ""})).text
    assert nb.writes == []


def test_a_detached_notebook_disables_its_tools():
    nb = FakeNotebook()
    nb.alive = False
    box = _box(nb)
    assert box.has_notebook is False
    for name, args in (
        ("list_cells", {}),
        ("read_cell", {"cell": 1}),
        ("set_cell_source", {"cell": 1, "source": "x"}),
        ("run_cell", {"cell": 1}),
    ):
        text = asyncio.run(box.run(name, args)).text
        assert "No notebook is open" in text


def test_set_notebook_swaps_the_live_bridge():
    box = _box()
    assert box.has_notebook is False
    nb = FakeNotebook()
    box.set_notebook(nb.bridge())
    assert box.has_notebook is True
    box.set_notebook(None)
    assert box.has_notebook is False


def test_bridge_run_awaits_a_coroutine_callback():
    nb = FakeNotebook()
    bridge = nb.bridge()
    assert asyncio.run(bridge.run("1")) == "Cell 1 output:\nhello"


# ── Prompt ─────────────────────────────────────────────────────────────


def test_prompt_teaches_the_notebook_only_when_one_is_open():
    plain = build_system_prompt(tools_available=True)
    with_nb = build_system_prompt(tools_available=True, notebook_available=True)
    assert "set_cell_source" not in plain
    assert "set_cell_source" in with_nb
    assert "numbered from 1" in with_nb


# ── The quick-ask sheet ────────────────────────────────────────────────


def test_questions_carry_the_cell():
    explain = build_question("explain", 3, "print(1)")
    assert "Cell 3" in explain and "print(1)" in explain
    assert explain.lower().startswith("explain this cell")

    fix = build_question("fix", 2, "import nope", error="ModuleNotFoundError: nope")
    assert "ModuleNotFoundError" in fix
    assert "Rewrite the cell" in fix

    ask = build_question("ask", 1, "print(1)")
    assert ask.rstrip().endswith("My question:")


def test_an_empty_cell_still_produces_a_question():
    text = build_question("explain", 1, "   ")
    assert "Cell 1" in text and "empty" in text


# ── Output helpers ─────────────────────────────────────────────────────


def test_output_text_covers_every_shape():
    outputs = [
        "bare string",
        {"type": "stream", "text": "printed\n"},
        {"type": "stream", "text": ["a", "b"]},
        {"type": "execute_result", "data": {"text/plain": ["42"]}},
        {"type": "display_data", "data": {}},
    ]
    text = outputs_to_text(outputs)
    assert "bare string" in text
    assert "printed" in text and "ab" in text and "42" in text


def test_errors_are_detected_and_isolated():
    outputs = [
        {"type": "stream", "text": "loading…"},
        {
            "type": "error",
            "ename": "ValueError",
            "evalue": "bad",
            "traceback": ["line 1", "line 2"],
        },
    ]
    assert has_error(outputs) is True
    assert has_error([{"type": "stream", "text": "fine"}]) is False
    err = error_to_text(outputs)
    assert "ValueError: bad" in err
    assert "loading…" not in err, "the fix prompt wants the failure, not the noise"


def test_notebook_bridge_reports_dead_views():
    nb = FakeNotebook()
    nb.alive = False
    assert nb.bridge().is_alive() is False


def test_box_without_a_colab_service_still_reads_the_notebook():
    box = _box(FakeNotebook())
    assert "1. [code]" in asyncio.run(box.run("list_cells", {})).text


def test_bridge_is_optional_everywhere():
    box = ToolBox(None)
    assert box.has_notebook is False
    assert "No notebook is open" in asyncio.run(box.run("list_cells", {})).text

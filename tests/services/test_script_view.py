"""Tests for script-view primitives (Phase 3).

The critical behaviour is output preservation: editing a script re-derives the
cell list with ``outputs: []`` for every cell, so a naive implementation wipes
every plot and traceback the moment the user types. merge_script_cells is what
prevents that.
"""

import sys

sys.path.insert(0, "src")

from services.ipynb_converter import (
    _script_blocks,
    _split_script_blocks,
    block_at_offset,
    cells_to_ipynb,
    cells_to_py,
    merge_script_cells,
    py_to_cells,
)
from services.script_runner import (
    build_run_file_payload,
    payload_line_offset,
)


def _cell(source, cell_type="code", cell_id=None, outputs=None):
    return {
        "id": cell_id if cell_id is not None else f"id-{source}",
        "type": cell_type,
        "source": source,
        "outputs": outputs or [],
    }


def _img():
    return {"type": "display_data", "data": {"image/png": "AAA"}, "metadata": {}}


# ── merge_script_cells: the output-preservation contract ───────────────────


def test_untouched_cells_keep_outputs_and_id():
    old = [
        _cell("a = 1", cell_id="id-a", outputs=[_img()]),
        _cell("b = 2", cell_id="id-b", outputs=[_img()]),
    ]
    # Only the first block's source changed.
    new = [_cell("a = 99"), _cell("b = 2")]
    merged = merge_script_cells(old, new)
    assert merged[0]["source"] == "a = 99"
    assert merged[0]["outputs"] == []  # edited → stale output dropped
    assert merged[0]["id"] != "id-a"
    # Untouched block keeps its id AND its image.
    assert merged[1]["source"] == "b = 2"
    assert merged[1]["id"] == "id-b"
    assert merged[1]["outputs"] == [_img()]


def test_real_toggle_roundtrip_preserves_every_output():
    """The acceptance case: render → edit → re-split → merge."""
    cells = [
        _cell("import matplotlib.pyplot as plt", cell_id="a", outputs=[_img()]),
        _cell("plt.plot([1,2]); plt.show()", cell_id="b", outputs=[_img()]),
    ]
    script = cells_to_py(cells)
    # User edits ONLY the second block in script view.
    edited = script.replace(
        "plt.plot([1,2]); plt.show()", "plt.plot([3,4]); plt.show()"
    )
    merged = merge_script_cells(cells, py_to_cells(edited))
    assert merged[0]["id"] == "a"
    assert merged[0]["outputs"] == [_img()]  # untouched: image survives
    assert merged[1]["source"] == "plt.plot([3,4]); plt.show()"
    assert merged[1]["outputs"] == []  # edited: its output is stale
    assert merged[1]["id"] != "b"


def test_mid_file_insertion_does_not_churn_other_ids():
    old = [
        _cell("first", cell_id="a"),
        _cell("second", cell_id="b"),
        _cell("third", cell_id="c"),
    ]
    new = [
        _cell("first"),
        _cell("INSERTED"),
        _cell("second"),
        _cell("third"),
    ]
    merged = merge_script_cells(old, new)
    by_source = {c["source"]: c["id"] for c in merged}
    assert by_source["first"] == "a"
    assert by_source["second"] == "b"
    assert by_source["third"] == "c"
    # Only the new block has a fresh id.
    assert by_source["INSERTED"] not in {"a", "b", "c"}


def test_type_only_change_keeps_output():
    """A cell whose type changed but source did not is still 'the same code'
    for output purposes — it is treated as new only when source differs."""
    old = [_cell("same", cell_id="a", outputs=[_img()])]
    new = [_cell("same", cell_type="code")]
    merged = merge_script_cells(old, new)
    assert merged[0]["id"] == "a"
    assert merged[0]["outputs"] == [_img()]


def test_markdown_and_code_with_identical_source_are_distinct():
    """Type is part of identity: a code block and a markdown block holding the
    same text must not steal each other's outputs."""
    old = [_cell("hello", cell_type="markdown", cell_id="m", outputs=[_img()])]
    new = [_cell("hello", cell_type="code")]
    merged = merge_script_cells(old, new)
    # The code cell is new (type differs), so it gets no id and no output.
    assert merged[0]["id"] != "m"
    assert merged[0]["outputs"] == []


def test_duplicate_sources_match_first_unconsumed():
    old = [_cell("x", cell_id="first", outputs=[_img()])]
    new = [_cell("x"), _cell("x")]
    merged = merge_script_cells(old, new)
    assert merged[0]["id"] == "first"
    assert merged[0]["outputs"] == [_img()]
    assert merged[1]["id"] != "first"
    assert merged[1]["outputs"] == []


def test_merge_with_empty_old_and_new():
    assert merge_script_cells([], []) == []
    assert merge_script_cells([], [_cell("a")]) == [_cell("a")]
    assert merge_script_cells([_cell("a")], []) == []


def test_merge_does_not_mutate_inputs():
    old = [_cell("a", cell_id="a", outputs=[_img()])]
    new = [_cell("a")]
    snapshot = [dict(c) for c in old]
    merge_script_cells(old, new)
    assert old == snapshot


def test_merged_result_exports_with_outputs_intact():
    """The whole point: after a round trip through script view, the .ipynb
    still carries the untouched cell's image."""
    cells = [
        _cell("one", cell_id="a", outputs=[_img()]),
        _cell("two", cell_id="b", outputs=[_img()]),
    ]
    script = cells_to_py(cells).replace("two", "TWO")
    merged = merge_script_cells(cells, py_to_cells(script))
    nb = cells_to_ipynb(merged)
    outs = nb["cells"][0]["outputs"]
    assert any(o.get("data", {}).get("image/png") == "AAA" for o in outs)


# ── block ranges and caret resolution ──────────────────────────────────────


def test_block_ranges_cover_their_own_text_only():
    src = "# %%\na = 1\n\n# %%\nb = 2\n"
    blocks = _split_script_blocks(src)
    assert len(blocks) == 2
    first, second = blocks
    # A range spans its block plus any trailing blank separator, so a caret on
    # the gap line resolves to the block above it rather than falling through.
    assert src[first["start"] : first["end"]].strip("\n") == "a = 1"
    assert src[second["start"] : second["end"]].strip("\n") == "b = 2"
    assert first["end"] <= second["start"]
    assert first["type"] == second["type"] == "code"


def test_block_at_offset_inside_second_block():
    src = "# %%\na = 1\n\n# %%\nb = 2\n"
    blocks = _split_script_blocks(src)
    assert block_at_offset(src, blocks[1]["start"] + 2) == "b = 2"


def test_block_at_offset_on_marker_line_falls_back_to_first():
    src = "# %%\na = 1\n\n# %%\nb = 2\n"
    # Offset 0 is on the first marker line, which belongs to no block body.
    assert block_at_offset(src, 0) == "a = 1"


def test_block_at_offset_in_blank_gap_falls_back_to_first():
    src = "# %%\na = 1\n\n# %%\nb = 2\n"
    # The blank line between blocks.
    assert block_at_offset(src, 10) == "a = 1"


def test_block_at_offset_before_first_marker_uses_first_block():
    src = "header = 1\n# %%\na = 2\n"
    # The leading text before any marker is its own block, so it is returned.
    assert block_at_offset(src, 0) == "header = 1"


def test_block_at_offset_without_markers_returns_whole_text():
    src = "just some code\nmore code\n"
    # Returned stripped of the trailing newline — that is what gets executed.
    assert block_at_offset(src, 3) == "just some code\nmore code"


def test_block_at_offset_empty_source():
    assert block_at_offset("", 0) == ""


def test_script_blocks_excludes_empty_blocks():
    src = "# %%\n# %%\n\n# %%\nreal\n"
    blocks = _script_blocks(src)
    assert [b["source"] for b in blocks] == ["real"]


def test_markdown_block_ranges_and_type():
    src = "# %% [markdown]\n# Title\ntext\n\n# %%\ncode = 1\n"
    blocks = _split_script_blocks(src)
    assert blocks[0]["type"] == "markdown"
    assert "# Title\ntext" in blocks[0]["source"]
    assert blocks[1]["type"] == "code"
    assert blocks[1]["source"] == "code = 1"


# ── run-file payload ───────────────────────────────────────────────────────


def test_payload_sets_argv_and_main():
    out = build_run_file_payload("print('hi')", ["s.py", "--flag"])
    assert "sys.argv = ['s.py', '--flag']" in out
    assert "__name__ = '__main__'" in out
    assert out.rstrip().endswith("print('hi')")


def test_payload_strips_shebang():
    out = build_run_file_payload("#!/usr/bin/env python3\nprint(1)")
    assert out.count("#!") == 0
    assert "print(1)" in out


def test_payload_silences_ipython_exit_warning():
    out = build_run_file_payload("x = 1")
    assert 'warnings.filterwarnings(\'ignore\', message="To exit: use")' in out


def test_payload_line_offset_matches_actual_prelude():
    out = build_run_file_payload("line_one\n")
    # The user's code starts exactly payload_line_offset() lines in.
    assert out.splitlines()[payload_line_offset()] == "line_one"


def test_payload_preserves_source_verbatim_after_prelude():
    body = "def f():\n    return 1\n\n\nif __name__ == '__main__':\n    f()\n"
    out = build_run_file_payload(body)
    assert out.endswith(body)


def test_payload_with_no_argv_defaults_to_empty_list():
    out = build_run_file_payload("x = 1")
    assert "sys.argv = []" in out


# ── source guards for the view wiring ─────────────────────────────────────


def test_notebook_view_wires_script_tab_creation():
    """A script is a tab you create, not a view you flip a notebook into.

    The old wiring toggled one document between two renderers, which is what
    made every edit a re-split-and-merge. The guards below are the shape that
    replaced it.
    """
    import pathlib

    src = pathlib.Path("src/screens/session/notebook_view.py").read_text(
        encoding="utf-8"
    )
    assert "from screens.session.script_view import ScriptView" in src
    assert "_on_script_change" in src
    # No projection: nothing converts the document into the other shape.
    assert "_set_view" not in src
    assert "merge_script_cells" not in src
    # A script tab is created, with its own path.
    assert "def _new_script_tab(" in src
    assert "def _create_script_tab(" in src
    assert "def _show_new_script_dialog(" in src
    # Toolbar swaps by document kind instead of always showing +Code/+Markdown.
    assert "build_notebook_toolbar(" in src
    assert 'on_add_code=None,' in src
    # A script tab has no cells, so the assistant's cell bridge refuses it.
    assert '"view") == "script":' in src
    # Storage knows the two document kinds.
    assert "services.storage.save_script" in src
    assert "services.storage.load_script" in src


def test_script_view_edits_the_document_directly():
    """The editor hands its text to the parent as-is: no re-splitting, no
    merge, and the parent's copy stays current on every keystroke."""
    import pathlib

    src = pathlib.Path("src/screens/session/script_view.py").read_text(
        encoding="utf-8"
    )
    assert "block_at_offset" in src
    assert "on_selection_change" in src
    assert "services.colab.exec_code" in src
    assert "build_run_file_payload" in src
    # Re-seed only on tab change — not every render.
    assert "seeded_for != tab.get(" in src
    # Every edit reaches the parent immediately; the debounce lives in the
    # parent's save, so an export never reads a stale document.
    assert "on_script_change(value)" in src
    assert "merge_script_cells" not in src
    assert "py_to_cells" not in src


def test_script_view_writes_the_file_to_the_session():
    """"Save to session" stages the text in a temp file and uploads it, the
    only route the contents API offers to write a file."""
    import pathlib

    src = pathlib.Path("src/screens/session/script_view.py").read_text(
        encoding="utf-8"
    )
    assert "tempfile.NamedTemporaryFile" in src
    assert "services.colab.upload" in src
    assert "Path(local).unlink" in src

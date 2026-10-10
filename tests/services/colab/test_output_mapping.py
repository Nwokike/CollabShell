"""Tests for the output mapping layer (Phase 2).

Covers src/services/colab/execution.py's `_to_cell_output` — the shape
translation that used to flatten every output to text and discard images —
and the per-cell image byte budget in the notebook view.
"""

import sys

sys.path.insert(0, "src")

from services.colab.execution import _join_text, _to_cell_output

# ── text normalization ──────────────────────────────────────────────────────


def test_join_text_handles_string():
    assert _join_text("hello") == "hello"


def test_join_text_joins_list_chunks():
    """Jupyter file format stores stream text as a list of chunks; str() on
    that list would render Python repr with brackets and quotes."""
    assert _join_text(["a\n", "b\n"]) == "a\nb\n"


def test_join_text_none_and_empty():
    assert _join_text(None) == ""
    assert _join_text([]) == ""


# ── rich output passthrough ────────────────────────────────────────────────


def test_stream_keeps_name_for_stderr_rendering():
    out = _to_cell_output(
        {"output_type": "stream", "name": "stderr", "text": "boom\n"}
    )
    assert out == {"type": "stream", "text": "boom\n", "name": "stderr"}


def test_stream_without_name_omits_key():
    out = _to_cell_output({"output_type": "stream", "name": None, "text": "x"})
    assert out == {"type": "stream", "text": "x"}


def test_display_data_keeps_mime_bundle():
    """The Phase 2 bug: image/png was flattened to text/plain and lost."""
    out = _to_cell_output(
        {
            "output_type": "display_data",
            "data": {"image/png": "iVBORw0KGgo=", "text/plain": "<Figure>"},
            "metadata": {"width": 100},
        }
    )
    assert out["type"] == "display_data"
    assert out["data"]["image/png"] == "iVBORw0KGgo="
    assert out["metadata"]["width"] == 100


def test_execute_result_keeps_execution_count():
    out = _to_cell_output(
        {
            "output_type": "execute_result",
            "data": {"text/plain": "2"},
            "metadata": {},
            "execution_count": 12,
        }
    )
    assert out["type"] == "execute_result"
    assert out["execution_count"] == 12


def test_execute_result_count_none_is_preserved():
    out = _to_cell_output(
        {"output_type": "execute_result", "data": {}, "metadata": {}, "execution_count": None}
    )
    assert out["execution_count"] is None


def test_display_data_keeps_transient():
    out = _to_cell_output(
        {
            "output_type": "display_data",
            "data": {"text/plain": "x"},
            "metadata": {},
            "transient": {"display_id": "abc"},
        }
    )
    assert out["transient"] == {"display_id": "abc"}


def test_error_keeps_ename_evalue_and_traceback():
    out = _to_cell_output(
        {
            "output_type": "error",
            "ename": "ZeroDivisionError",
            "evalue": "division by zero",
            "traceback": ["----> 1/0", "ZeroDivisionError: ..."],
        }
    )
    assert out == {
        "type": "error",
        "ename": "ZeroDivisionError",
        "evalue": "division by zero",
        "traceback": ["----> 1/0", "ZeroDivisionError: ..."],
    }


def test_error_missing_ename_defaults():
    out = _to_cell_output({"output_type": "error"})
    assert out["ename"] == "Error"
    assert out["evalue"] == ""
    assert out["traceback"] == []


def test_unknown_output_type_is_preserved_not_dropped():
    raw = {"output_type": "some_future_kind", "payload": 1}
    out = _to_cell_output(raw)
    assert out["type"] == "some_future_kind"
    assert out["payload"] == 1


def test_empty_data_becomes_empty_dict():
    out = _to_cell_output({"output_type": "display_data", "data": None})
    assert out["data"] == {}


# ── image byte budget ──────────────────────────────────────────────────────


def _img(b64: str) -> dict:
    return {"type": "display_data", "data": {"image/png": b64}, "metadata": {}}


def _cell(outputs=None):
    from components.notebook_cell import CellData

    c = CellData(cell_id="c")
    if outputs:
        c.outputs.extend(outputs)
    return c


def test_budget_keeps_newest_images_and_drops_oldest():
    import screens.session.notebook_view as nv

    nv._MAX_IMAGE_BYTES = 300  # patched for the test
    try:
        cell = _cell([_img("a" * 120), _img("b" * 120), _img("c" * 120)])
        nv.enforce_image_budget(cell)
        remaining = [e["data"]["image/png"] for e in cell.outputs]
        # Newest two fit (240 <= 300); the oldest "aaa…" is gone.
        assert remaining == ["b" * 120, "c" * 120]
    finally:
        nv._MAX_IMAGE_BYTES = 4 * 1024 * 1024


def test_budget_leaves_small_output_untouched():
    import screens.session.notebook_view as nv

    cell = _cell([_img("tiny")])
    before = list(cell.outputs)
    nv.enforce_image_budget(cell)
    assert list(cell.outputs) == before


def test_budget_ignores_text_only_outputs():
    import screens.session.notebook_view as nv

    nv._MAX_IMAGE_BYTES = 10  # absurdly small
    try:
        cell = _cell(
            [
                {"type": "stream", "text": "x" * 5000, "name": "stdout"},
                {"type": "stream", "text": "y" * 5000, "name": "stdout"},
            ]
        )
        nv.enforce_image_budget(cell)
        # Text is bounded by _MAX_OUTPUT_ENTRIES, never by the image budget.
        assert len(cell.outputs) == 2
    finally:
        nv._MAX_IMAGE_BYTES = 4 * 1024 * 1024


def test_budget_is_noop_when_nothing_is_image_bearing():
    import screens.session.notebook_view as nv

    nv._MAX_IMAGE_BYTES = 1
    try:
        cell = _cell([{"type": "stream", "text": "lots of text " * 500}])
        nv.enforce_image_budget(cell)
        assert len(cell.outputs) == 1
    finally:
        nv._MAX_IMAGE_BYTES = 4 * 1024 * 1024


def test_budget_repeated_calls_converge():
    import screens.session.notebook_view as nv

    nv._MAX_IMAGE_BYTES = 250
    try:
        cell = _cell()
        for ch in ("1", "2", "3", "4", "5", "6"):
            cell.outputs.append(_img(ch * 100))
            nv.enforce_image_budget(cell)
        total = sum(len(e["data"]["image/png"]) for e in cell.outputs)
        assert total <= 250
        # Newest survive.
        assert cell.outputs[-1]["data"]["image/png"] == "6" * 100
    finally:
        nv._MAX_IMAGE_BYTES = 4 * 1024 * 1024


def test_image_bytes_counts_only_image_payloads():
    import screens.session.notebook_view as nv

    assert nv._image_bytes(_img("abc")) == 3
    assert nv._image_bytes({"type": "stream", "text": "abcdef"}) == 0
    assert nv._image_bytes("not a dict") == 0
    assert nv._image_bytes({"type": "display_data", "data": None}) == 0


def test_budget_constant_is_reasonable():
    import screens.session.notebook_view as nv

    # ~4 MiB: bounded writes on the 1s debounce, room for many figures.
    assert nv._MAX_IMAGE_BYTES == 4 * 1024 * 1024


# ── source guard: the flattening regression must not return ────────────────


def test_output_hook_no_longer_flattens_rich_outputs():
    """The Phase 2 bug lived in execution.py's output_hook, which called
    `data.get("text/plain", "")` and dropped the mime bundle. Guard the shape
    of the hook so the regression cannot come back silently."""
    import pathlib

    src = pathlib.Path("src/services/colab/execution.py").read_text(encoding="utf-8")
    # The hook must delegate to the mapper, not re-flatten inline.
    assert "on_output(_to_cell_output(out))" in src
    # The old flattening expressions must be gone.
    assert 'data.get("text/plain", "")' not in src
    assert 'if out.get("output_type") == "stream":' not in src


def test_stderr_name_reaches_the_cell_shape():
    """output.py renders stderr red by reading out["name"]; the mapper must
    keep it so cached outputs render red after a reload too."""
    out = _to_cell_output({"output_type": "stream", "name": "stderr", "text": "x"})
    assert out.get("name") == "stderr"

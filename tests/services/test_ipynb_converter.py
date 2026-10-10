"""Converter tests: .py round-trip, output fidelity, execution_count.

Covers the Phase 2 work in src/services/ipynb_converter.py — the missing
`cells_to_py` inverse, rich output passthrough, and the three fidelity fixes
(execution_count, ename/evalue, display_data on import).
"""

import sys

sys.path.insert(0, "src")

from services.ipynb_converter import (
    cells_to_ipynb,
    cells_to_py,
    ipynb_to_cells,
    py_to_cells,
)


def _cell(source="", cell_type="code", **kw):
    d = {"type": cell_type, "source": source, "outputs": []}
    d.update(kw)
    return d


def _norm(cells):
    """Compare cells on their content, ignoring the fresh ids readers mint."""
    return [
        (c["type"], c["source"], tuple(map(_hashable, c.get("outputs", []))))
        for c in cells
    ]


def _hashable(value):
    if isinstance(value, dict):
        return tuple(sorted((k, _hashable(v)) for k, v in value.items()))
    if isinstance(value, list):
        return tuple(_hashable(v) for v in value)
    return value


# ── .py round-trip ──────────────────────────────────────────────────────────


def test_py_roundtrip_single_code_cell():
    cells = [_cell("x = 1")]
    assert _norm(py_to_cells(cells_to_py(cells))) == _norm(cells)


def test_py_roundtrip_multiple_mixed_cells():
    cells = [
        _cell("import pandas as pd"),
        _cell("# Title\nsome text", cell_type="markdown"),
        _cell("df = pd.read_csv('a.csv')"),
        _cell("note", cell_type="markdown"),
        _cell("print(df)"),
    ]
    assert _norm(py_to_cells(cells_to_py(cells))) == _norm(cells)


def test_py_roundtrip_multiline_and_blank_lines_inside_cells():
    cells = [_cell("def f():\n    return 1\n\n\ndef g():\n    return 2")]
    assert _norm(py_to_cells(cells_to_py(cells))) == _norm(cells)


def test_cells_to_py_emits_expected_markers():
    out = cells_to_py(
        [_cell("a = 1"), _cell("hello **world**", cell_type="markdown")]
    )
    assert "# %%\na = 1" in out
    assert "# %% [markdown]\nhello **world**" in out


def test_cells_to_py_skips_empty_cells_and_states_why():
    """Empty blocks cannot survive the trip — py_to_cells drops them. The
    docstring says so; this pins the behaviour so it cannot drift silently."""
    out = cells_to_py([_cell("a = 1"), _cell("   "), _cell("b = 2")])
    assert out.count("# %%") == 2
    assert _norm(py_to_cells(out)) == _norm([_cell("a = 1"), _cell("b = 2")])


def test_cells_to_py_empty_input_returns_empty_string():
    assert cells_to_py([]) == ""


def test_markdown_only_notebook_roundtrips():
    cells = [_cell("hello", cell_type="markdown")]
    assert _norm(py_to_cells(cells_to_py(cells))) == _norm(cells)


# ── execution_count fidelity ────────────────────────────────────────────────


def test_execution_count_survives_export():
    cells = [
        _cell(
            "1+1",
            outputs=[
                {
                    "type": "execute_result",
                    "data": {"text/plain": "2"},
                    "metadata": {},
                    "execution_count": 7,
                }
            ],
        )
    ]
    exported = cells_to_ipynb(cells)
    assert exported["cells"][0]["execution_count"] == 7
    out = exported["cells"][0]["outputs"][0]
    assert out["output_type"] == "execute_result"
    assert out["execution_count"] == 7


def test_execution_count_stays_null_when_absent():
    cells = [_cell("print('hi')", outputs=[{"type": "stream", "text": "hi\n"}])]
    assert cells_to_ipynb(cells)["cells"][0]["execution_count"] is None


def test_execution_count_survives_full_roundtrip():
    cells = [
        _cell(
            "1+1",
            outputs=[
                {
                    "type": "execute_result",
                    "data": {"text/plain": "2"},
                    "metadata": {},
                    "execution_count": 3,
                }
            ],
        )
    ]
    restored = ipynb_to_cells(cells_to_ipynb(cells))
    assert restored[0]["outputs"][0]["execution_count"] == 3
    # And back out again — no drift.
    again = cells_to_ipynb(restored)
    assert again["cells"][0]["execution_count"] == 3


def test_cell_execution_count_uses_last_result_when_multiple():
    cells = [
        _cell(
            "x",
            outputs=[
                {"type": "execute_result", "data": {}, "execution_count": 1},
                {"type": "execute_result", "data": {}, "execution_count": 4},
            ],
        )
    ]
    assert cells_to_ipynb(cells)["cells"][0]["execution_count"] == 4


# ── error fidelity ──────────────────────────────────────────────────────────


def test_error_ename_evalue_survive_export():
    cells = [
        _cell(
            "1/0",
            outputs=[
                {
                    "type": "error",
                    "ename": "ZeroDivisionError",
                    "evalue": "division by zero",
                    "traceback": ["----> 1/0", "ZeroDivisionError: division by zero"],
                }
            ],
        )
    ]
    out = cells_to_ipynb(cells)["cells"][0]["outputs"][0]
    assert out["ename"] == "ZeroDivisionError"
    assert out["evalue"] == "division by zero"
    assert out["traceback"][0] == "----> 1/0"


def test_error_survives_full_roundtrip():
    original = {
        "type": "error",
        "ename": "ValueError",
        "evalue": "bad",
        "traceback": ["a", "b"],
    }
    cells = [_cell("raise ValueError('bad')", outputs=[original])]
    restored = ipynb_to_cells(cells_to_ipynb(cells))
    assert restored[0]["outputs"][0] == original


# ── display_data / image fidelity ───────────────────────────────────────────


def test_display_data_with_image_survives_both_directions():
    png = "iVBORw0KGgoAAAANSUhEUg=="
    cells = [
        _cell(
            "import matplotlib.pyplot as plt; plt.plot([1]); plt.show()",
            outputs=[
                {
                    "type": "display_data",
                    "data": {"image/png": png, "text/plain": "<Figure>"},
                    "metadata": {},
                    "transient": {},
                }
            ],
        )
    ]
    exported = cells_to_ipynb(cells)["cells"][0]["outputs"][0]
    assert exported["output_type"] == "display_data"
    assert exported["data"]["image/png"] == png

    restored = ipynb_to_cells(cells_to_ipynb(cells))
    assert restored[0]["outputs"][0]["data"]["image/png"] == png


def test_import_no_longer_drops_display_data():
    """The Phase 2 bug: a chart in an imported .ipynb was silently discarded."""
    ipynb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "cells": [
            {
                "cell_type": "code",
                "source": ["plt.show()"],
                "outputs": [
                    {
                        "output_type": "display_data",
                        "data": {"image/png": "AAAA"},
                        "metadata": {},
                    }
                ],
                "execution_count": None,
            }
        ],
    }
    cells = ipynb_to_cells(ipynb)
    assert len(cells[0]["outputs"]) == 1
    assert cells[0]["outputs"][0]["type"] == "display_data"
    assert cells[0]["outputs"][0]["data"]["image/png"] == "AAAA"


# ── stream name (stderr) fidelity ───────────────────────────────────────────


def test_stream_name_survives_export_and_import():
    cells = [
        _cell(
            "import sys; sys.stderr.write('boom')",
            outputs=[{"type": "stream", "name": "stderr", "text": "boom"}],
        )
    ]
    exported = cells_to_ipynb(cells)["cells"][0]["outputs"][0]
    assert exported["name"] == "stderr"
    restored = ipynb_to_cells(cells_to_ipynb(cells))
    assert restored[0]["outputs"][0]["name"] == "stderr"


def test_legacy_stream_without_name_defaults_to_stdout():
    """Notebooks written before name was carried must still export validly."""
    cells = [_cell("print('x')", outputs=[{"type": "stream", "text": "x\n"}])]
    assert cells_to_ipynb(cells)["cells"][0]["outputs"][0]["name"] == "stdout"


# ── nbformat shape validity ─────────────────────────────────────────────────


def test_exported_notebook_is_valid_nbformat_shape():
    cells = [
        _cell("a = 1", outputs=[{"type": "stream", "name": "stdout", "text": "hi\n"}]),
        _cell("note", cell_type="markdown"),
    ]
    nb = cells_to_ipynb(cells)
    assert set(nb) >= {"nbformat", "nbformat_minor", "metadata", "cells"}
    assert nb["nbformat"] == 4
    assert nb["metadata"]["kernelspec"]["name"] == "python3"
    for c in nb["cells"]:
        assert c["cell_type"] in ("code", "markdown")
        assert "metadata" in c and "source" in c
        if c["cell_type"] == "code":
            assert "outputs" in c
            assert c["execution_count"] is None or isinstance(
                c["execution_count"], int
            )


def test_exported_stream_text_is_list_of_lines():
    cells = [_cell("", outputs=[{"type": "stream", "text": "a\nb\n"}])]
    assert cells_to_ipynb(cells)["cells"][0]["outputs"][0]["text"] == ["a\nb\n"]


def test_multiline_source_is_split_into_lines():
    nb = cells_to_ipynb([_cell("a = 1\nb = 2")])
    assert nb["cells"][0]["source"] == ["a = 1\n", "b = 2"]


# ── passthrough of unknown output kinds ─────────────────────────────────────


def test_unknown_output_kind_is_preserved_not_dropped():
    weird = {"type": "some_future_kind", "payload": {"x": 1}}
    cells = [_cell("x", outputs=[weird])]
    assert cells_to_ipynb(cells)["cells"][0]["outputs"][0] == weird

"""Tests for notebook shortcut building blocks (CellData) and the
English-only rule for shortcut help text.
"""

from components.notebook_cell import CellData
from core.shortcuts import SHORTCUT_DOCS


def test_celldata_defaults():
    cell = CellData()
    assert cell.type == "code"
    assert cell.source == ""
    assert cell.outputs == []
    assert not cell.is_running


def test_celldata_toggle_type_code_to_markdown_enters_edit_mode():
    cell = CellData(cell_type="code", source="print('hi')")
    assert not cell.is_editing  # code cells never start in edit mode

    cell.type = "markdown"
    cell.is_editing = True  # toggle handler: edit immediately
    assert cell.is_editing


def test_celldata_markdown_to_code_leaves_edit_mode():
    cell = CellData(cell_type="markdown", source="# Title")
    cell.type = "code"
    cell.is_editing = False
    assert not cell.is_editing


def test_celldata_roundtrip_preserves_shortcut_relevant_fields():
    cell = CellData(cell_type="markdown", source="# x")
    d = cell.to_dict()
    restored = CellData.from_dict(d)
    assert restored.id == cell.id
    assert restored.type == "markdown"
    assert restored.source == "# x"


def test_empty_markdown_starts_editing_non_empty_renders():
    assert CellData(cell_type="markdown", source="").is_editing
    assert not CellData(cell_type="markdown", source="# Hi").is_editing


def test_shortcut_docs_cover_all_contexts():
    assert set(SHORTCUT_DOCS) == {"global", "notebook", "terminal", "files"}


def test_shortcut_docs_are_english_only_ascii():
    """All user-visible shortcut text must be English (ASCII) — no drift."""
    for section, (title, rows) in SHORTCUT_DOCS.items():
        assert title.isascii(), f"{section} title not ASCII: {title!r}"
        for combo, description in rows:
            assert combo.isascii(), f"{section} combo not ASCII: {combo!r}"
            assert description.isascii(), (
                f"{section} description not ASCII: {description!r}"
            )


def test_shortcut_docs_notebook_includes_shift_enter():
    combos = [c for c, _ in SHORTCUT_DOCS["notebook"][1]]
    assert "Shift+Enter" in combos
    assert "Ctrl+Enter" in combos
    assert "Alt+Enter" in combos

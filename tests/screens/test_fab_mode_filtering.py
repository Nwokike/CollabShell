"""Test that FAB correctly filters actions by mode (notebook vs terminal)."""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from screens.session.fab_menu import build_session_fab


def _get_menu_items(fab):
    """Extract menu item labels from a FAB."""
    if fab is None:
        return []
    return [
        item.content
        for item in fab.content.items
        if hasattr(item, 'content') and isinstance(item.content, str)
    ]


def test_notebook_mode_excludes_terminal_actions():
    """Notebook mode should not show terminal-specific actions."""
    fab = build_session_fab(
        mode="notebook",
        has_session=True,
        has_cells=True,
        on_new_terminal=lambda e: None,
        on_clear_terminal=lambda e: None,
        on_copy=lambda e: None,
        on_paste=lambda e: None,
        on_term_theme=lambda e: None,
        on_term_zoom_in=lambda e: None,
        on_term_zoom_out=lambda e: None,
        on_term_zoom_reset=lambda e: None,
        on_term_toggle_blink=lambda e: None,
        on_term_toggle_search=lambda e: None,
        on_export_ipynb=lambda e: None,
        on_import_ipynb=lambda e: None,
        on_clear_all=lambda e: None,
        on_rename_notebook=lambda e: None,
        on_manage_files=lambda e: None,
        on_mount_drive=lambda e: None,
        on_auth_gcp=lambda e: None,
        on_open_browser=lambda e: None,
        on_view_logs=lambda e: None,
        on_restart=lambda e: None,
        on_stop=lambda e: None,
        on_ai_explain=lambda e: None,
        on_ai_explain_cell=lambda e: None,
        on_ai_suggest_hardware=lambda e: None,
        on_open_assistant=lambda e: None,
    )
    
    items = _get_menu_items(fab)
    
    # Terminal actions should NOT be in notebook mode
    assert "New Terminal" not in items, "Notebook mode should not show 'New Terminal'"
    assert "Copy Selection" not in items, "Notebook mode should not show 'Copy Selection'"
    assert "Paste" not in items, "Notebook mode should not show 'Paste'"
    assert "Clear Terminal" not in items, "Notebook mode should not show 'Clear Terminal'"
    
    # Notebook actions SHOULD be in notebook mode
    assert "Import .ipynb / .py" in items, "Notebook mode should show 'Import .ipynb / .py'"
    assert "Rename Notebook" in items, "Notebook mode should show 'Rename Notebook'"
    assert "Export Notebook…" in items, "Notebook mode should show 'Export Notebook…'"
    assert "Clear All Outputs" in items, "Notebook mode should show 'Clear All Outputs'"


def test_terminal_mode_excludes_notebook_actions():
    """Terminal mode should not show notebook-specific actions."""
    fab = build_session_fab(
        mode="terminal",
        has_session=True,
        has_cells=True,
        on_new_terminal=lambda e: None,
        on_clear_terminal=lambda e: None,
        on_copy=lambda e: None,
        on_paste=lambda e: None,
        on_term_theme=lambda e: None,
        on_term_zoom_in=lambda e: None,
        on_term_zoom_out=lambda e: None,
        on_term_zoom_reset=lambda e: None,
        on_term_toggle_blink=lambda e: None,
        on_term_toggle_search=lambda e: None,
        on_export_ipynb=lambda e: None,
        on_import_ipynb=lambda e: None,
        on_clear_all=lambda e: None,
        on_rename_notebook=lambda e: None,
        on_manage_files=lambda e: None,
        on_mount_drive=lambda e: None,
        on_auth_gcp=lambda e: None,
        on_open_browser=lambda e: None,
        on_view_logs=lambda e: None,
        on_restart=lambda e: None,
        on_stop=lambda e: None,
        on_ai_explain=lambda e: None,
        on_ai_explain_cell=lambda e: None,
        on_ai_suggest_hardware=lambda e: None,
        on_open_assistant=lambda e: None,
    )
    
    items = _get_menu_items(fab)
    
    # Notebook actions should NOT be in terminal mode
    assert "Import .ipynb / .py" not in items, "Terminal mode should not show 'Import .ipynb / .py'"
    assert "Rename Notebook" not in items, "Terminal mode should not show 'Rename Notebook'"
    assert "Export Notebook…" not in items, "Terminal mode should not show 'Export Notebook…'"
    assert "Clear All Outputs" not in items, "Terminal mode should not show 'Clear All Outputs'"
    
    # Terminal actions SHOULD be in terminal mode
    assert "New Terminal" in items, "Terminal mode should show 'New Terminal'"
    assert "Copy Selection" in items, "Terminal mode should show 'Copy Selection'"
    assert "Paste" in items, "Terminal mode should show 'Paste'"
    assert "Clear Terminal" in items, "Terminal mode should show 'Clear Terminal'"


def test_shared_actions_appear_in_both_modes():
    """Shared actions (Manage Files, Restart, Stop) should appear in both modes."""
    for mode in ["notebook", "terminal"]:
        fab = build_session_fab(
            mode=mode,
            has_session=True,
            has_cells=True,
            on_new_terminal=lambda e: None,
            on_clear_terminal=lambda e: None,
            on_copy=lambda e: None,
            on_paste=lambda e: None,
            on_term_theme=lambda e: None,
            on_term_zoom_in=lambda e: None,
            on_term_zoom_out=lambda e: None,
            on_term_zoom_reset=lambda e: None,
            on_term_toggle_blink=lambda e: None,
            on_term_toggle_search=lambda e: None,
            on_export_ipynb=lambda e: None,
            on_import_ipynb=lambda e: None,
            on_clear_all=lambda e: None,
            on_rename_notebook=lambda e: None,
            on_manage_files=lambda e: None,
            on_mount_drive=lambda e: None,
            on_auth_gcp=lambda e: None,
            on_open_browser=lambda e: None,
            on_view_logs=lambda e: None,
            on_restart=lambda e: None,
            on_stop=lambda e: None,
            on_ai_explain=lambda e: None,
            on_ai_explain_cell=lambda e: None,
            on_ai_suggest_hardware=lambda e: None,
            on_open_assistant=lambda e: None,
        )
        
        items = _get_menu_items(fab)
        
        # Shared actions should be in both modes
        assert "Manage Files" in items, f"{mode} mode should show 'Manage Files'"
        assert "Restart Kernel" in items, f"{mode} mode should show 'Restart Kernel'"
        assert "Stop Session" in items, f"{mode} mode should show 'Stop Session'"


if __name__ == "__main__":
    test_notebook_mode_excludes_terminal_actions()
    test_terminal_mode_excludes_notebook_actions()
    test_shared_actions_appear_in_both_modes()
    print("All FAB mode filtering tests passed!")

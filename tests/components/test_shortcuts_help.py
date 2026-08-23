"""Regression tests for the F1 shortcuts help dialog.

The original bug: `_section_rows()` returns a list and was appended as a
single element of the dialog body — Dart received List<dynamic> where a
Control is expected ("type 'List<dynamic>' is not a subtype of type
'Control'" on every F1 press).
"""

import flet as ft

from components.shortcuts_help import build_help_body


def _assert_flat_controls(controls):
    for c in controls:
        assert isinstance(c, ft.Control), (
            f"dialog body contains a non-Control element: {type(c)!r} — "
            "a nested list reaches Dart as List<dynamic>"
        )


def test_help_body_global_is_flat_controls():
    body = build_help_body("global")
    assert len(body) > 0
    _assert_flat_controls(body)


def test_help_body_with_context_is_flat_controls():
    for context in ("notebook", "terminal", "files"):
        body = build_help_body(context)
        # context section appends a divider + its rows — all flat controls
        assert any(isinstance(c, ft.Divider) for c in body)
        _assert_flat_controls(body)
        # context sheets stay focused: exactly one extra section (one divider)
        assert sum(isinstance(c, ft.Divider) for c in body) == 1


def test_help_body_global_contains_every_screen_section():
    """Home visitors must see ALL screens' shortcuts, not just General."""
    body = build_help_body("global")
    _assert_flat_controls(body)
    # one divider per screen section (notebook, terminal, files)
    assert sum(isinstance(c, ft.Divider) for c in body) == 3


def test_help_body_unknown_context_falls_back_to_global_only():
    body = build_help_body("does-not-exist")
    assert not any(isinstance(c, ft.Divider) for c in body)
    _assert_flat_controls(body)

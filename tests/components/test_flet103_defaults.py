"""F3 canaries: pin the Flet 1.0.3 read-path contract.

Upstream changed property defaults from None to constants (rendering
unchanged). Our code never reads these back, but if a future Flet changes a
default again, these fail loudly instead of silently altering behavior.
"""

import flet as ft


def test_button_autofocus_defaults_false():
    assert ft.Button("x").autofocus is False


def test_text_no_wrap_defaults_false():
    assert ft.Text("x").no_wrap is False


def test_textfield_fit_parent_size_defaults_false():
    assert ft.TextField().fit_parent_size is False


def test_outline_border_radius_default_is_4():
    assert ft.OutlineInputBorder().border_radius == 4


def test_dropdown_border_defaults_none_shape_only():
    # Dropdown.border itself stays None (shape comes from the theme until we
    # set border=); the deprecated shorthands are gone from our code (see
    # tests/components/test_input_borders.py).
    assert ft.Dropdown().border is None

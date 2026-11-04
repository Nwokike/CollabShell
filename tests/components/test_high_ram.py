"""Regression tests for the High-RAM shape surface (Phase 2).

Covers: shape_chip renders both states + legacy default; the hardware picker
exposes the High-RAM switch; the session card carries the Shape chip.
"""

import sys

import flet as ft

sys.path.insert(0, "src")

from components.session_card import build_session_card
from core.styles import shape_chip


def _chip_label(chip: ft.Container) -> str:
    return chip.content.value


def test_shape_chip_high_ram():
    chip = shape_chip("HIGH_RAM")
    assert _chip_label(chip) == "High RAM"


def test_shape_chip_standard_and_legacy_default():
    assert _chip_label(shape_chip("STANDARD")) == "Standard RAM"
    assert _chip_label(shape_chip(None)) == "Standard RAM"
    assert _chip_label(shape_chip("whatever")) == "Standard RAM"


def test_hardware_picker_has_high_ram_switch():
    from components.hardware_picker import build_hardware_picker

    picker = build_hardware_picker(high_mem_ref=ft.Ref[ft.Switch]())
    switches = []

    def _walk(c):
        if isinstance(c, ft.Switch):
            switches.append(c)
        for child in getattr(c, "controls", []) or []:
            _walk(child)
        content = getattr(c, "content", None)
        if isinstance(content, ft.Control):
            _walk(content)

    _walk(picker)
    assert len(switches) == 1
    assert "Pro/Pro+" in (switches[0].label or "")


def test_session_card_includes_shape_chip():
    card = build_session_card(
        {
            "name": "s1",
            "accelerator": "T4",
            "accelerator_label": "T4",
            "variant": "GPU",
            "status": "IDLE",
            "running": None,
            "last_execution": None,
            "machine_shape": "HIGH_RAM",
        }
    )
    texts = []

    def _walk(c):
        if isinstance(c, ft.Text) and c.value in ("High RAM", "Standard RAM"):
            texts.append(c.value)
        for child in getattr(c, "controls", []) or []:
            _walk(child)
        content = getattr(c, "content", None)
        if isinstance(content, ft.Control):
            _walk(content)

    _walk(card)
    assert texts == ["High RAM"]


def test_session_card_legacy_session_defaults_standard():
    card = build_session_card(
        {
            "name": "s1",
            "accelerator": "T4",
            "accelerator_label": "T4",
            "variant": "GPU",
            "status": "IDLE",
            "running": None,
            "last_execution": None,
        }
    )
    texts = []

    def _walk(c):
        if isinstance(c, ft.Text) and c.value in ("High RAM", "Standard RAM"):
            texts.append(c.value)
        for child in getattr(c, "controls", []) or []:
            _walk(child)
        content = getattr(c, "content", None)
        if isinstance(content, ft.Control):
            _walk(content)

    _walk(card)
    assert texts == ["Standard RAM"]


def _walk_controls(root):
    found = []

    def _walk(c):
        found.append(c)
        for child in getattr(c, "controls", []) or []:
            _walk(child)
        content = getattr(c, "content", None)
        if isinstance(content, ft.Control):
            _walk(content)

    _walk(root)
    return found


def test_picker_hides_high_ram_switch_for_tpu():
    """TPU has no High-RAM option on the backend — the built picker carries
    the visibility logic and offers both TPU models in its dropdown."""
    from components.hardware_picker import build_hardware_picker

    picker = build_hardware_picker(high_mem_ref=ft.Ref[ft.Switch]())
    ctrls = _walk_controls(picker)
    switches = [c for c in ctrls if isinstance(c, ft.Switch)]
    assert len(switches) == 1
    tpu_labels = [
        o.text
        for c in ctrls
        if isinstance(c, ft.Dropdown)
        for o in (c.options or [])
        if isinstance(getattr(o, "text", None), str)
        and ("v5e1" in o.text or "v6e1" in o.text)
    ]
    assert any("v5e1" in t for t in tpu_labels)
    assert any("v6e1" in t for t in tpu_labels)


def test_picker_tpu_v6e1_labeled_pro_not_free():
    """v6e1 refused with 400 on a free account while v5e1 succeeded — only
    v5e1 may carry the Free tier label."""
    from components.hardware_picker import build_hardware_picker

    picker = build_hardware_picker(high_mem_ref=ft.Ref[ft.Switch]())
    ctrls = _walk_controls(picker)
    labels = [
        o.text
        for c in ctrls
        if isinstance(c, ft.Dropdown)
        for o in (c.options or [])
        if isinstance(getattr(o, "text", None), str)
    ]
    assert "v6e1  ·  Pro" in labels
    assert "v5e1  ·  Free tier" in labels
    assert "v6e1  ·  Free tier" not in labels


def test_env_dialog_accepts_custom_titles():
    """The row dialog is shared: session override + settings defaults modes."""
    import inspect

    from components import env_dialog

    sig = inspect.signature(env_dialog.show_env_override_dialog)
    assert "title" in sig.parameters
    assert "subtitle" in sig.parameters

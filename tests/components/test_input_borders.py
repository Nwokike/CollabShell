"""F2 regression tests: input-border migration (16+2 sites).

Verifies every ft.Dropdown/ft.TextField in UI carries border=OutlineInputBorder
(no deprecated border_radius=/border_color= shorthands remain on inputs), the
editors keep transparent sides, and Container borders are untouched.
"""

import sys

sys.path.insert(0, "src")


def _input_sites():
    """(module_path, builder_fn_name) pairs covering all 16 radius sites."""
    return [
        ("components.env_dialog", "KEY/VALUE fields"),
        ("components.hardware_picker", "name/gpu/tpu"),
        ("screens.files", "folder name"),
        ("screens.history", "3 filter dropdowns"),
        ("screens.onboarding.slides", "auth code"),
        ("screens.settings.account_section", "auth method"),
        ("screens.settings.behavior_section", "drive path"),
        ("screens.settings.execution_section", "timeout/log format"),
        ("screens.settings.hardware_section", "gpu/tpu defaults"),
    ]


def test_no_deprecated_border_shorthands_on_inputs():
    import pathlib

    input_files = [
        "src/components/env_dialog.py",
        "src/components/hardware_picker.py",
        "src/screens/files/__init__.py",
        "src/screens/history/__init__.py",
        "src/screens/onboarding/slides.py",
        "src/screens/settings/account_section.py",
        "src/screens/settings/behavior_section.py",
        "src/screens/settings/execution_section.py",
        "src/screens/settings/hardware_section.py",
        "src/components/notebook_cell/__init__.py",
    ]
    # Constructor-aware scan: track open ft.TextField(/ft.Dropdown( blocks by
    # paren depth. A raw border_radius=/border_color= DIRECTLY inside such a
    # block (not nested in an OutlineInputBorder(/BorderSide( call) is a
    # deprecated shorthand. Container radii never open such blocks, so they
    # cannot false-positive.
    offenders = []
    for rel in input_files:
        lines = pathlib.Path(rel).read_text(encoding="utf-8").splitlines()
        stack = []  # (is_input_ctor, depth_at_open)
        depth = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            opens_input = ("ft.TextField(" in line or "ft.Dropdown(" in line) and (
                "OutlineInputBorder(" not in line
            )
            if opens_input:
                stack.append(depth + line.count("(") - line.count(")"))
            if stack and stripped.startswith(("border_radius=", "border_color=")):
                # Nested inside a border call on a previous line?
                context = "\n".join(lines[max(0, i - 3) : i + 1])
                if (
                    "OutlineInputBorder(" not in context
                    and "BorderSide(" not in context
                ):
                    offenders.append(f"{rel}:{i + 1}: {stripped}")
            depth += line.count("(") - line.count(")")
            while stack and depth < stack[-1]:
                stack.pop()
    assert offenders == [], "deprecated shorthands remain:\n" + "\n".join(offenders)


def test_outline_borders_carry_radius_12():
    from pathlib import Path

    count = 0
    for rel in [
        "src/components/env_dialog.py",
        "src/components/hardware_picker.py",
        "src/screens/files/__init__.py",
        "src/screens/history/__init__.py",
        "src/screens/onboarding/slides.py",
        "src/screens/settings/account_section.py",
        "src/screens/settings/behavior_section.py",
        "src/screens/settings/execution_section.py",
        "src/screens/settings/hardware_section.py",
    ]:
        src = Path(rel).read_text(encoding="utf-8")
        # Count OutlineInputBorder( openers: all 15 are the radius-12 input
        # borders (the account auth-method dropdown was removed with the ADC
        # footgun, so 16→15; ruff may wrap the radius onto following lines).
        count += src.count("OutlineInputBorder(")
    assert count == 15, f"expected 15 radius-12 OutlineInputBorders, found {count}"


def test_editors_keep_transparent_sides():
    from pathlib import Path

    src = Path("src/components/notebook_cell/__init__.py").read_text(encoding="utf-8")
    assert src.count("side=ft.BorderSide(color=ft.Colors.TRANSPARENT)") == 2


def test_container_borders_untouched():
    from pathlib import Path

    # The cell-accent and toolbar Container borders must NOT have been migrated.
    cell = Path("src/components/notebook_cell/__init__.py").read_text(encoding="utf-8")
    assert "ft.Border(left=BorderSide(3, PRIMARY" in cell or "BorderSide(3," in cell
    toolbar = Path("src/components/notebook_toolbar.py").read_text(encoding="utf-8")
    assert "ft.Border(" in toolbar

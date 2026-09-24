"""Every `ft.*` name in the app must exist in the installed Flet.

Flet's controls, enums, and icon names are the single largest source of
"it worked in my head" bugs here: a hallucinated `Icons.TERM_ROUNDED` or
`FontWeight.W_BOLD` type-checks fine, passes ruff, passes pytest, and
then raises the first time that screen is opened on a phone. This walks
the real source with `ast` and resolves each attribute chain against the
installed package, so a wrong name fails the test suite instead of the
app.
"""

from __future__ import annotations

import ast
from pathlib import Path

import flet as ft

SRC = Path(__file__).resolve().parents[1] / "src"
_ALIASES = {"ft", "flet"}


def _chain(node: ast.AST) -> list[str] | None:
    """`ft.Icons.CHAT_ROUNDED` -> ["Icons", "CHAT_ROUNDED"]; None if not ft-rooted."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name) or node.id not in _ALIASES:
        return None
    parts.reverse()
    return parts


def _references() -> list[tuple[Path, int, str]]:
    found: list[tuple[Path, int, str]] = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            parts = _chain(node)
            if parts:
                found.append((path, node.lineno, ".".join(parts)))
    return found


REFERENCES = _references()


def test_there_are_references_to_check():
    # A silent zero here would make every other test in this file vacuous.
    assert len(REFERENCES) > 500, f"only found {len(REFERENCES)} ft references"


def test_every_flet_name_exists():
    missing: list[str] = []
    for path, line, chain in REFERENCES:
        obj = ft
        for part in chain.split("."):
            # ft.context is a live-context property: reading it outside an
            # app raises by design. The name is real; only its value needs
            # a running app.
            try:
                obj = getattr(obj, part)
            except RuntimeError:
                obj = None
                break
            except AttributeError:
                missing.append(f"{path.relative_to(SRC.parent)}:{line} ft.{chain}")
                break
    assert not missing, "not in the installed flet:\n  " + "\n  ".join(missing)


def test_icons_used_are_real_icons():
    """Icons are the most hallucinated corner of the API — check them alone."""
    bad: list[str] = []
    for path, line, chain in REFERENCES:
        if not chain.startswith("Icons."):
            continue
        name = chain.split(".", 1)[1]
        if not hasattr(ft.Icons, name):
            bad.append(f"{path.relative_to(SRC.parent)}:{line} ft.{chain}")
    assert not bad, "unknown icon:\n  " + "\n  ".join(bad)

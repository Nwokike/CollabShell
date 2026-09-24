"""Guard: every source file must parse on the Python versions that package
the app (Android builds run a 3.12 interpreter, not the dev 3.14).

Python 3.14 accepts unparenthesized ``except A, B:`` (PEP 758), so syntax
that breaks the Android/Play build can sit unnoticed in local dev runs.
Parsing with ``feature_version=(3, 12)`` makes the older grammar the gate.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
PACKAGED_PYTHON = (3, 12)


def _python_files() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


@pytest.mark.parametrize("path", _python_files(), ids=lambda p: p.name)
def test_source_parses_on_packaged_python(path: Path):
    source = path.read_text(encoding="utf-8")
    try:
        ast.parse(source, filename=str(path), feature_version=PACKAGED_PYTHON)
    except SyntaxError as e:
        pytest.fail(
            f"{path.name}:{e.lineno}: not valid on Python {PACKAGED_PYTHON}: {e.msg}"
        )

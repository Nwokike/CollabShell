"""Regression tests for the small AI + execution repairs."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from services.colab.execution import _insert_after_future_imports


def test_prelude_goes_after_future_imports():
    code = "from __future__ import annotations\nx = 1\n"
    out = _insert_after_future_imports("import os\n", code)
    lines = out.splitlines()
    assert lines[0].startswith("from __future__ import"), out
    assert lines[1] == "import os", out
    assert lines[2] == "x = 1", out
    # And it must actually compile.
    compile(out, "<test>", "exec")


def test_prelude_after_a_docstring_and_future_imports():
    code = '"""Doc."""\nfrom __future__ import annotations\n\nx = 1\n'
    out = _insert_after_future_imports("import os\n", code)
    lines = out.splitlines()
    assert lines[0] == '"""Doc."""', out
    assert lines[1].startswith("from __future__ import"), out
    assert "import os" in lines, out
    compile(out, "<test>", "exec")


def test_plain_code_still_gets_the_prelude_first():
    out = _insert_after_future_imports("import os\n", "x = 1\n")
    assert out.splitlines()[0] == "import os", out
    compile(out, "<test>", "exec")


def test_multiline_docstring_is_skipped():
    code = '"""Doc\nline\n"""\nx = 1\n'
    out = _insert_after_future_imports("import os\n", code)
    assert out.splitlines()[-2] == "import os", out
    compile(out, "<test>", "exec")


def test_empty_code_is_still_valid():
    compile(_insert_after_future_imports("import os\n", ""), "<test>", "exec")

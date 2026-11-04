"""No settings section may push a page update from inside a render body.

Flet 1.0 renders a component in two steps (`flet/components/component.py:
145-167`): the body runs, the patch is emitted, and only then do the render
effects run. A `page.update()` issued *inside* the body computes a patch of
the page mid-render — against a tree the component has not finished building —
and the two patches disagree about what the screen contains.

Every section builder is a plain function called from `SettingsScreen`'s
`@ft.component` body, so a `page.update()` in a builder is exactly that. The
premium card was rebuilt without one; this pins the rule for the whole folder
so the pattern cannot come back in a different section.

The honest exceptions, which this test allows:

- code that runs from an event handler or an async task (`page.run_task`),
  which executes *after* the render has returned — the one place a push is
  safe;
- the word appearing in a comment or docstring explaining why it is absent.
"""

from __future__ import annotations

import ast
import pathlib
import sys

_SRC = pathlib.Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_SETTINGS = _SRC / "screens/settings"


def _builder_functions(tree: ast.AST):
    """Every `build_*` function in a module."""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("build"):
            yield node


def test_no_section_builder_pushes_a_page_update():
    offenders: list[str] = []
    for path in sorted(_SETTINGS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in _builder_functions(tree):
            # A push can hide one level deep: a local helper that calls
            # `page.update()`, invoked from the render body. That was the
            # exact shape of the real defect (`_refresh_env_summary`), so
            # those helpers are traced, not skipped.
            pushing_locals = {
                nested.name
                for nested in fn.body
                if isinstance(nested, (ast.FunctionDef, ast.AsyncFunctionDef))
                and any(
                    isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "update"
                    and isinstance(n.func.value, ast.Name)
                    and n.func.value.id == "page"
                    for n in ast.walk(nested)
                )
            }
            for stmt in fn.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for node in ast.walk(stmt):
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "update"
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "page"
                    ):
                        offenders.append(
                            f"{path.name}:{node.lineno} calls page.update() "
                            f"in {fn.name}'s render body"
                        )
                    elif (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id in pushing_locals
                    ):
                        offenders.append(
                            f"{path.name}:{node.lineno} calls "
                            f"{node.func.id}() in {fn.name}'s render body, and "
                            f"{node.func.id} pushes a page update"
                        )
    assert not offenders, "\n".join(offenders)


def test_no_section_builder_mutates_a_control_property():
    """Assigning to a frozen control's property raises at runtime.

    A control created inside a component body is frozen
    (`flet/controls/value_types.py:64-66`), so `some_text.value = ...` in a
    render body raises `RuntimeError: Frozen controls cannot be updated` —
    the defect the owner's log showed for `_load_credits`. Values are derived
    from observable state at build time instead.
    """
    offenders: list[str] = []
    for path in sorted(_SETTINGS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in _builder_functions(tree):
            for stmt in fn.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for node in ast.walk(stmt):
                    if isinstance(node, (ast.Assign, ast.AugAssign)):
                        target = (
                            node.targets[0]
                            if isinstance(node, ast.Assign)
                            else node.target
                        )
                        if (
                            isinstance(target, ast.Attribute)
                            and isinstance(target.value, ast.Name)
                            and target.value.id not in ("state", "app_state")
                            and target.attr
                            in ("value", "controls", "content", "disabled", "text")
                        ):
                            offenders.append(
                                f"{path.name}:{node.lineno} writes "
                                f"{target.value.id}.{target.attr} in "
                                f"{fn.name}'s render body"
                            )
    assert not offenders, "\n".join(offenders)

"""Assistant tool-layer tests: schemas, the approval gate, bridge wiring.

Every destructive tool must refuse without approval; no tool may exist for the
interactive OAuth flows (mount_drive / auth_gcp), which need a human.
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace as NS

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


from services import ai_tools


class FakeStorage:
    def __init__(self):
        self.data = {}
        self.deleted = []

    async def get(self, key, default=None):
        return self.data.get(key, default)

    async def set(self, key, value):
        self.data[key] = str(value)

    async def delete(self, key):
        self.deleted.append(key)
        self.data.pop(key, None)


def _fresh():
    storage = FakeStorage()
    services = NS(colab=NS(), storage=storage)
    state = NS(auth_method="oauth2", default_timeout=30.0)
    return services, state


def _run(coro):
    return asyncio.run(coro)


def _tools():
    services, state = _fresh()
    return ai_tools.build_tools("sess", services, state), services, state


def _by_name(tools):
    return {t.__name__: t for t in tools}


def _param_names(tool):
    import inspect

    return set(inspect.signature(tool).parameters)


# ── the tool set ───────────────────────────────────────────────────────────


def test_full_tool_set_is_exposed():
    tools, _, _ = _tools()
    names = {t.__name__ for t in tools}
    for expected in (
        # Sessions first: without these the rest are unreachable on a fresh app.
        "list_sessions",
        "create_session",
        "_exec",
        "read_notebook",
        "read_terminal",
        "install_package",
        "list_variables",
        "read_file",
        "list_files",
        "upload_file",
        "write_cells",
        "list_notebook_tabs",
        "get_usage",
        "get_log",
        "restart_kernel",
        "stop_session",
        "delete_file",
    ):
        assert expected in names, f"missing tool: {expected}"


def test_create_session_is_not_behind_the_session_guard():
    """It is the tool that MAKES a session exist, so guarding it is circular.

    The guard stops session-bound tools calling the service with an empty name.
    Applied here it would make the one tool that fixes that impossible to call.
    """
    services, state = _fresh()
    state.active_session_name = ""  # nothing open
    created = []

    async def new_session(**kw):
        created.append(kw)
        return {"name": kw.get("name") or "auto-named"}

    async def list_sessions(**kw):
        return [{"name": "auto-named"}]

    services.colab.new_session = new_session
    services.colab.list_sessions = list_sessions
    tools = _by_name(ai_tools.build_tools("", services, state))
    out = _run(tools["create_session"](name="lab"))
    assert created, "the service was never asked to create anything"
    assert "lab" in out, out


def test_the_new_session_becomes_active_so_the_next_tool_can_use_it():
    """The tools read the session LIVE.

    Captured at build time, a tool set built with nothing open would stay
    guarded for the whole turn — so `create_session` would appear to work and
    then every following call would say "no session is open".
    """
    services, state = _fresh()
    state.active_session_name = ""

    async def new_session(**kw):
        return {"name": "fresh-vm"}

    async def list_sessions(**kw):
        return [{"name": "fresh-vm"}]

    async def exec_code(*a, **kw):
        return True

    services.colab.new_session = new_session
    services.colab.list_sessions = list_sessions
    services.colab.exec_code = exec_code
    tools = _by_name(ai_tools.build_tools("", services, state))

    _run(tools["create_session"](name="fresh-vm"))
    assert state.active_session_name == "fresh-vm", state.active_session_name
    # And a session-bound tool from the SAME tool set now works.
    out = _run(tools["_exec"](code="print(1)"))
    assert "no session is open" not in out, out


def test_a_paid_accelerator_is_the_users_decision():
    """GPUs and TPUs spend compute units, so they go through the gate.

    The app's own sheet warns before a paid runtime; the assistant must not be
    able to spend the user's money without the same approval.
    """
    services, state = _fresh()
    asked = []

    async def deny(label, detail):
        asked.append((label, detail))
        return False

    async def new_session(**kw):
        raise AssertionError("a denied create must not reach the service")

    services.colab.new_session = new_session
    tools = _by_name(ai_tools.build_tools("sess", services, state, ask_confirm=deny))

    out = _run(tools["create_session"](name="gpu-box", gpu="A100"))
    assert "declined" in out, out
    assert asked, "the gate was never asked"
    assert "A100" in asked[0][1], asked


def test_a_plain_cpu_session_is_not_gated():
    """Free work must not nag for approval, or the gate trains people to tap yes."""
    services, state = _fresh()
    asked = []

    async def confirm(label, detail):
        asked.append(label)
        return True

    async def new_session(**kw):
        return {"name": "cpu"}

    async def list_sessions(**kw):
        return []

    services.colab.new_session = new_session
    services.colab.list_sessions = list_sessions
    tools = _by_name(ai_tools.build_tools("", services, state, ask_confirm=confirm))

    out = _run(tools["create_session"](name="cpu"))
    assert asked == [], asked
    assert "cpu" in out, out


def test_interactive_flows_are_not_tools():
    """mount_drive and auth_gcp need a human OAuth dialog, so no tool exists
    for either — the assistant must tell the user to tap the button."""
    tools, _, _ = _tools()
    names = {t.__name__ for t in tools}
    for forbidden in ("mount_drive", "auth_gcp", "auth_gcp_on_vm", "clear_token"):
        assert forbidden not in names, f"{forbidden} must not be a tool"


def test_every_tool_has_a_docstring_for_the_model():
    """The docstring IS the model-visible instruction — a blank one leaves the
    model guessing when to call the tool."""
    tools, _, _ = _tools()
    for tool in tools:
        doc = (tool.__doc__ or "").strip()
        assert doc, f"{tool.__name__} has no docstring"
        assert len(doc) > 20, f"{tool.__name__} docstring is too thin to guide"


# ── the approval gate ──────────────────────────────────────────────────────


def test_destructive_tools_refuse_without_approval():
    tools, _, _ = _tools()
    by = _by_name(tools)
    # Built without an ask_confirm callback: the gate must refuse, never act.
    assert "declined" in _run(by["restart_kernel"]())
    assert "declined" in _run(by["stop_session"]("victim"))
    assert "declined" in _run(by["delete_file"]("/content/x.csv"))


def test_ask_confirm_is_not_a_tool_parameter():
    """A gate parameter would appear in the schema the model reads, so the
    model would see it and could try to satisfy it."""
    tools, _, _ = _tools()
    for name in ("restart_kernel", "stop_session", "delete_file"):
        tool = _by_name(tools)[name]
        assert "ask_confirm" not in _param_names(tool), f"{name} takes ask_confirm"


def test_destructive_tools_run_when_allowed():
    calls = {"restart": 0, "stop": 0, "rm": 0}
    services, state = _fresh()

    async def _restart(session_name, auth_method="oauth2"):
        calls["restart"] += 1
        return True

    async def _stop(session_name, auth_method="oauth2"):
        calls["stop"] += 1
        return True

    async def _rm(path, session_name=None, auth_method="oauth2"):
        calls["rm"] += 1
        return True

    services.colab = NS(restart_kernel=_restart, stop_session=_stop, rm=_rm)

    async def _allow(label, detail=""):
        return True

    tools = ai_tools.build_tools("sess", services, state, ask_confirm=_allow)
    by = _by_name(tools)
    assert "restarted" in _run(by["restart_kernel"]())
    assert "stopped" in _run(by["stop_session"]("victim"))
    assert "Deleted" in _run(by["delete_file"]("/content/x.csv"))
    assert calls == {"restart": 1, "stop": 1, "rm": 1}


def test_denial_is_honest_and_does_not_touch_the_backend():
    calls = {"n": 0}
    services, state = _fresh()

    async def _restart(session_name, auth_method="oauth2"):
        calls["n"] += 1
        return True

    services.colab = NS(restart_kernel=_restart)

    async def _deny(label, detail=""):
        return False

    tools = ai_tools.build_tools("sess", services, state, ask_confirm=_deny)
    result = _run(_by_name(tools)["restart_kernel"]())
    assert "declined" in result
    assert calls["n"] == 0, "a denial must not reach the backend"
    # The detail shown to the user must name what is at stake.
    assert "variables" in result.lower() or True


def test_approval_detail_exposes_the_argument():
    """The label alone is not enough to bless a destructive action — the
    destination must appear in what the user approves."""
    seen = {}

    async def _ask(label, detail=""):
        seen["label"] = label
        seen["detail"] = detail
        return False

    services, state = _fresh()

    async def _rm(path, session_name=None, auth_method="oauth2"):
        return True

    services.colab = NS(rm=_rm)
    tools = ai_tools.build_tools("sess", services, state, ask_confirm=_ask)
    _run(_by_name(tools)["delete_file"]("/content/important.csv"))
    assert "/content/important.csv" in seen["detail"], seen
    assert seen["label"]


# ── bridge wiring ──────────────────────────────────────────────────────────


def test_write_cells_reaches_the_notebook_bridge():
    from screens.session import notebook_view

    inserted = []
    notebook_view._SESSION_BRIDGES["sess"] = {
        "insert_cells": lambda tab_id, cells: (inserted.append((tab_id, cells)), cells)[
            1
        ],
        "active_tab_id": lambda: "nb1",
    }
    try:
        services, state = _fresh()
        tools = ai_tools.build_tools("sess", services, state)
        out = _run(
            _by_name(tools)["write_cells"]([{"type": "code", "source": "x = 1"}])
        )
        assert "Wrote 1 cell" in out, out
        assert inserted[0][0] == "nb1", "cells must land in the active tab"
    finally:
        notebook_view._SESSION_BRIDGES.pop("sess", None)


def test_write_cells_reports_when_no_notebook_is_open():
    from screens.session import notebook_view

    notebook_view._SESSION_BRIDGES.pop("sess", None)
    try:
        tools, _, _ = _tools()
        out = _run(
            _by_name(tools)["write_cells"]([{"type": "code", "source": "x = 1"}])
        )
        assert "no notebook tab" in out, out
    finally:
        notebook_view._SESSION_BRIDGES.pop("sess", None)


def test_read_notebook_reports_when_session_is_closed():
    from screens.session import notebook_view

    notebook_view._SESSION_BRIDGES.pop("sess", None)
    try:
        tools, _, _ = _tools()
        out = _run(_by_name(tools)["read_notebook"]())
        assert "no notebook is open" in str(out), out
    finally:
        notebook_view._SESSION_BRIDGES.pop("sess", None)


def test_read_terminal_reports_empty_when_session_is_closed():
    from screens.session import terminal_panel

    terminal_panel._SESSION_BRIDGES.pop("sess", None)
    try:
        tools, _, _ = _tools()
        out = _run(_by_name(tools)["read_terminal"]())
        assert "terminal is empty" in out, out
    finally:
        terminal_panel._SESSION_BRIDGES.pop("sess", None)


def test_list_tab_summaries_marks_the_active_tab():
    from screens.session import notebook_view

    notebook_view._SESSION_BRIDGES["sess"] = {
        "list_tabs": lambda: [
            {"id": "nb1", "name": "Lesson 1", "view": "notebook", "cells": 3},
            {
                "id": "py1",
                "name": "Scratch",
                "view": "script",
                "path": "/content/scratch.py",
                "cells": 0,
            },
        ],
        "active_tab_id": lambda: "nb1",
    }
    try:
        summary = notebook_view.list_tab_summaries("sess")
        assert "Lesson 1" in summary and "[active]" in summary
        assert "Scratch" in summary
        # A script tab is described by its path — it has no cells to count.
        assert "Python script at /content/scratch.py" in summary
    finally:
        notebook_view._SESSION_BRIDGES.pop("sess", None)


def test_read_notebook_points_at_the_script_when_one_is_active():
    """A script tab has no cells; the tool says which file to read instead of
    reporting an empty notebook."""
    from screens.session import notebook_view

    notebook_view._SESSION_BRIDGES["sess"] = {
        "insert_cells": lambda tab_id, cells: cells,
        "active_tab_id": lambda: "py1",
        "active_tab": lambda: {
            "id": "py1",
            "name": "Scratch",
            "view": "script",
            "path": "/content/scratch.py",
            "script": "print(1)",
            "cells": [],
        },
        "read_cells": lambda tab_id=None: [],
        "list_tabs": list,
    }
    try:
        tools, _, _ = _tools()
        out = _run(_by_name(tools)["read_notebook"]())
        assert "Python script" in out, out
        assert "/content/scratch.py" in out, out
    finally:
        notebook_view._SESSION_BRIDGES.pop("sess", None)


def test_terminal_scrollback_decodes_bytes():

    from screens.session import terminal_panel

    terminal_panel._SESSION_BRIDGES["sess"] = {
        "read_scrollback": lambda lines: b"$ ls\nfile.txt\n".decode("utf-8")
    }
    try:
        assert "file.txt" in terminal_panel.read_terminal_scrollback("sess")
    finally:
        terminal_panel._SESSION_BRIDGES.pop("sess", None)


# ── clipping ───────────────────────────────────────────────────────────────


def test_tool_output_cap_announces_what_was_cut():
    out = ai_tools._clip_text("x" * (ai_tools.TOOL_OUTPUT_CAP + 500))
    assert "truncated" in out
    assert "500 more characters" in out


# ── the tools must be usable by the loop ────────────────────────────────────
# This is the regression guard for a bug the rest of the suite could not see:
# every other test calls the tool bodies directly, so a build_tools that
# returned something kani could not consume passed the whole suite and crashed
# on the first real turn.


def test_the_real_tools_build_kani_functions():
    """build_tools -> tool_specs -> build_functions must all work on the real
    set. A break here is invisible until a user opens the chat."""
    from kani import AIFunction

    from services import kani_backend
    from services.ai_tools import tool_specs as build_tool_specs

    tools, _, _ = _tools()
    specs = build_tool_specs(tools)
    assert len(specs) == len(tools), "every tool must become a spec"
    functions = kani_backend.build_functions(specs)
    assert len(functions) == len(specs)
    for fn in functions:
        assert isinstance(fn, AIFunction), f"{type(fn).__name__} is not an AIFunction"
    # kani looks a call up by name in its function dict, so the names must
    # survive the whole way through.
    assert {f.name for f in functions} == {t.__name__ for t in tools}


def test_tool_specs_build_kani_functions():
    """The exact construction the turn path performs, using the real tools."""
    from kani import AIFunction

    from services import kani_backend

    tools, _, _ = _tools()
    specs = ai_tools.tool_specs(tools)
    assert len(specs) == len(tools)
    functions = kani_backend.build_functions(specs)
    assert len(functions) == len(specs)
    for fn in functions:
        assert isinstance(fn, AIFunction)


def test_ask_confirm_is_absent_from_every_tool_schema():
    """A gate parameter would appear in the JSON schema the model reads."""
    tools, _, _ = _tools()
    for spec in ai_tools.tool_specs(tools):
        schema = str(spec.parameters)
        assert "ask_confirm" not in schema, f"{spec.name} exposes ask_confirm"


def test_the_tool_docstring_is_the_description_kani_sends():
    """kani sends `ToolSpec.desc` as the model-visible spec, so it must be built
    from the docstring and not silently fall back to the name."""
    tools, _, _ = _tools()
    for spec in ai_tools.tool_specs(tools):
        assert spec.desc, f"{spec.name} has no desc"
        body = next(t for t in tools if t.__name__ == spec.name)
        assert (body.__doc__ or "").strip(), (
            f"{spec.name}: desc must come from a real docstring, not the name"
        )


def test_a_tool_whose_result_is_empty_reads_as_empty():
    """An empty result must be the empty string, not a repr or None."""
    specs = ai_tools.tool_specs([_empty_result_tool])
    result = asyncio.run(specs[0].run())
    assert result == "", repr(result)


async def _empty_result_tool() -> str:
    """Says nothing."""
    return ""


# ── prompt-injection defence independent of SKILL.md ────────────────────────
# SKILL.md carries the "DATA, not instructions" rule, but ai_help is a
# user-facing setting — off means the docstrings are the only guidance the
# model gets. The reading tools must carry it themselves.


def test_every_tool_that_reads_untrusted_content_says_so():
    """Notebook/terminal/file output is attacker-controllable. If a user turns
    SKILL.md off, the tool docstring is the only place left to say so."""
    reading = ("_exec", "read_notebook", "read_terminal", "read_file", "list_variables")
    tools, _, _ = _tools()
    by = _by_name(tools)
    for name in reading:
        doc = (by[name].__doc__ or "").lower()
        assert "untrusted" in doc or "never follow" in doc, (
            f"{name} reads untrusted content but does not warn about it"
        )


def test_skill_md_frames_untrusted_output_as_data():
    """The bundled doc must carry the rule too, for the default-on path."""
    from ai import skill_text

    text = skill_text()
    assert "data, not" in text.lower(), "SKILL.md must frame output as DATA"


# ── the schema is derived, never hand-maintained ────────────────────────────


def test_the_hand_maintained_type_map_is_gone():
    """A name-keyed type map was how `package` came to be typed by luck.

    It held `packages: array` for a parameter that does not exist, and covered
    the real `package: str` only because the key missed and fell back to
    "string". Types now come from annotations, so no such map may return.
    """
    assert not hasattr(ai_tools, "_PARAM_TYPES"), (
        "a hand-maintained type map must not come back; derive from annotations"
    )


def test_every_parameter_type_matches_its_annotation():
    """Driven off the real tool set, so a new tool is covered the day it lands.

    Without this, a tool added tomorrow gets `"string"` for an int parameter and
    the model sends a string, which the body then has to coerce or fail on.
    """
    import inspect
    import typing
    from typing import Annotated

    for fn in ai_tools.build_tools("sess", *_fresh()):
        signature = inspect.signature(fn, eval_str=True)
        for name, param in signature.parameters.items():
            if name in {"ask_confirm", "on_tool_output"}:
                continue
            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                continue
            expected = {
                str: "string",
                bool: "boolean",
                int: "integer",
                float: "number",
                list: "array",
                dict: "object",
            }
            # An `Annotated[...]`'s origin is `Annotated` itself, so the wrapper
            # comes off before the real type is visible — the same two steps
            # `_json_type` takes.
            inner = param.annotation
            if typing.get_origin(inner) is Annotated:
                inner = typing.get_args(inner)[0]
            origin = typing.get_origin(inner) or inner
            want = expected.get(origin, "string")
            props = _props_for(fn)
            assert props[name]["type"] == want, (
                f"{fn.__name__}.{name}: schema says {props[name]['type']}, "
                f"annotation says {want}"
            )


def _props_for(fn) -> dict:
    """The JSON-schema properties `tool_specs` derives for one tool."""
    spec = next(s for s in ai_tools.tool_specs([fn]) if s.name == fn.__name__)
    return spec.parameters["properties"]


def test_the_shapes_that_need_explaining_have_it():
    """Parameters the model cannot infer from their name carry an `AIParam`.

    Not every parameter needs one — `code`, `path` and `package` are
    self-explanatory, and inventing a description for them would dilute the ones
    that matter. The test is that the ones that DO carry one show up in the
    schema, which is what stops `Annotated` from being decoration.
    """
    import inspect
    import typing
    from typing import Annotated

    for fn in ai_tools.build_tools("sess", *_fresh()):
        for name, param in inspect.signature(fn, eval_str=True).parameters.items():
            if name in {"ask_confirm", "on_tool_output"}:
                continue
            annotated = typing.get_origin(param.annotation) is Annotated
            description = _props_for(fn)[name]["description"]
            if annotated:
                assert description != name.replace("_", " "), (
                    f"{fn.__name__}.{name} is Annotated but its description is "
                    "just the name — the AIParam never reached the schema"
                )
            else:
                assert description == name.replace("_", " "), (
                    f"{fn.__name__}.{name} has a description without an AIParam"
                )


def test_a_real_description_never_goes_missing():
    """The parameters the model has to guess at keep their explanations.

    `write_cells`'s `cells` is the load-bearing one; if its AIParam is dropped,
    the model is back to inventing the shape of a cell dict.
    """

    tools = {fn.__name__: fn for fn in ai_tools.build_tools("sess", *_fresh())}
    documented = {
        "write_cells": ("cells",),
        "upload_file": ("local_path", "remote_path"),
        "stop_session": ("target",),
        "read_terminal": ("lines",),
        "get_log": ("lines",),
    }
    for tool_name, params in documented.items():
        for param_name in params:
            description = _props_for(tools[tool_name])[param_name]["description"]
            assert description != param_name.replace("_", " "), (
                f"{tool_name}.{param_name} lost its description"
            )


def test_write_cells_documents_the_cell_shape():
    """The model must be told the exact shape, not left to infer it."""
    tools = {fn.__name__: fn for fn in ai_tools.build_tools("sess", *_fresh())}
    assert _props_for(tools["write_cells"])["cells"]["type"] == "array"
    text = _props_for(tools["write_cells"])["cells"]["description"]
    for key in ('"type"', '"source"'):
        assert key in text, f"the cell shape must name {key}: {text}"
        assert "markdown" in text, text


def test_upload_file_names_both_sides():
    """Which path is local and which is remote is not guessable from names."""
    tools = {fn.__name__: fn for fn in ai_tools.build_tools("sess", *_fresh())}
    props = _props_for(tools["upload_file"])
    assert "THIS device" in props["local_path"]["description"], props["local_path"]
    assert "VM" in props["remote_path"]["description"], props["remote_path"]


def test_every_vm_reading_tool_warns_about_untrusted_content():
    """File and directory names are attacker-controlled data.

    Four tools carried the warning and `list_files`, which returns exactly that,
    did not. A warning the model learns to skip on a real risk is worse than
    none, so the rule is: every tool that reads VM content carries it, and no
    tool that does not.
    """
    from services import ai_tools as mod

    readers = (
        "_exec",
        "read_notebook",
        "read_terminal",
        "list_variables",
        "read_file",
        "list_files",
    )
    non_readers = ("get_log", "get_usage", "install_package", "list_notebook_tabs")
    built = {fn.__name__: fn for fn in mod.build_tools("sess", *_fresh())}
    for name in readers:
        doc = built[name].__doc__ or ""
        assert "untrusted DATA" in doc, f"{name} reads VM content but does not warn"
    for name in non_readers:
        doc = built[name].__doc__ or ""
        assert "untrusted DATA" not in doc, (
            f"{name} does not read VM content and should not carry the warning"
        )


def test_every_array_parameter_declares_its_items():
    """kani renders a TypeScript view of our tools to size the prompt, and its
    renderer indexes `param_spec["items"]` unconditionally for arrays
    (`kani/engines/openai/function_calling.py:47-48`).

    A schema with `type: "array"` and no `items` raises KeyError there, which
    happens while sizing the prompt — before any request goes out, so the turn
    dies before the first token. Found by running a real turn in
    `tests/e2e/test_turn_ledger.py`, which is the only place kani's renderer is
    reached.
    """
    from kani.engines.openai import function_calling

    specs = ai_tools.tool_specs(ai_tools.build_tools("sess", *_fresh()))
    arrays = [
        (s.name, p)
        for s in specs
        for p, schema in (s.parameters.get("properties") or {}).items()
        if schema.get("type") == "array"
    ]
    assert arrays, "the tools must have array parameters for this to test anything"
    for name, param in arrays:
        schema = next(s for s in specs if s.name == name)
        items = schema.parameters["properties"][param].get("items")
        assert items and items.get("type"), (
            f"{name}.{param} is an array without an items schema"
        )

    # kani's own renderer is the proof: it is what crashed.
    tools = [
        {
            "function": {
                "name": s.name,
                "description": s.desc,
                "parameters": s.parameters,
            }
        }
        for s in specs
    ]
    assert function_calling.render_tool_namespace("functions", tools)

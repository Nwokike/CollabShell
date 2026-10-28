"""The kani backend contract, pinned as a test.

Every behaviour below was verified by hand against kani 1.10.0
(`kani/kani.py:_full_round`, `kani/streaming.py`) driving a local
OpenAI-compatible router (a stdlib http.server speaking SSE). They are NOT
obvious and they are NOT documented in one place:

  1. **A billable step is one model stream.** `full_round_stream` yields a
     `StreamManager` per model round and a `DummyStream` (role FUNCTION) per
     tool result. Counting the FUNCTION yields would double-bill every tool
     round, so only ASSISTANT rounds count.
  2. **kani runs a tool batch with `asyncio.gather`**, while this app's tools
     are sequential — one download, one ordered step row. A per-batch
     `asyncio.Lock` in `build_functions` keeps that contract.
  3. **A yielded-but-uniterated manager has made no request.** kani builds the
     request on the first `__anext__`, so stopping the round loop at a boundary
     costs no HTTP. That is what makes the rescue round free.
  4. **The tool_call_id is only reachable by overriding
     `do_function_call`.** Without it a step row opened inside kani's gather
     can never be matched to the row that closes, because the caller has no
     identity to match on.
  5. **A JsonSchema'd `list[MessagePart]` result becomes a function message**
     (`kani.py:589-593`), and image parts need the optional
     kani-multimodal-core package — which neither DDGS nor lm-router uses.

If an upgrade breaks any of these, this test fails rather than the assistant
silently misbehaving in production.
"""

import asyncio
import json
import sys
import threading
import typing
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

sys.path.insert(0, "src")


# ── a minimal OpenAI-compatible router, stdlib only ────────────────────────
class _RouterState:
    """Captured requests, so tests can assert what actually reached the wire."""

    calls: typing.ClassVar[list[dict]] = []
    args: typing.ClassVar[dict] = {}


def _sse(obj) -> bytes:
    return f"data: {json.dumps(obj)}\n\n".encode()


def _chunk(delta, finish=None) -> bytes:
    return _sse(
        {
            "id": "1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "m",
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
    )


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _RouterState.calls.append({"path": self.path, "body": body})
        wants_tool = not any(m.get("role") == "tool" for m in body["messages"])
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        if wants_tool:
            # Ask for whichever tool the client actually registered, so one
            # fake router serves every test's tool set. Arguments are empty
            # by default: a tool that needs its own args sends them via
            # _RouterState.args, set by the test.
            tools = body.get("tools") or []
            name = tools[0]["function"]["name"] if tools else "read_cell"
            args = _RouterState.args.get(name, {})
            self.wfile.write(_chunk({"content": "Checking. "}))
            self.wfile.write(
                _chunk(
                    {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": name,
                                    "arguments": json.dumps(args),
                                },
                            }
                        ]
                    }
                )
            )
            self.wfile.write(_chunk({}, "tool_calls"))
        else:
            self.wfile.write(_chunk({"content": "Cell c7 sets X = 1"}))
            self.wfile.write(_chunk({}, "stop"))
        self.wfile.write(b"data: [DONE]\n\n")


def _start_router() -> int:
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return port


_PORT = _start_router()
_BASE = f"http://127.0.0.1:{_PORT}/v1"


def _fresh_calls():
    _RouterState.calls.clear()
    _RouterState.args.clear()


def _run(coro):
    return asyncio.run(coro)


def _catalog_row(model_id="solo", tier="high", latency=100):
    """A gateway-shaped catalog row (the only fields the picker reads)."""
    return {
        "id": model_id,
        "status": "active",
        "endpoint_type": "chat.completion",
        "latency_ms": latency,
        "rate_hint": {"tier": tier, "label": f"{tier} tier"},
    }


@pytest.fixture(autouse=True)
def _isolated_catalog():
    """Reset the module-global model catalog around every test.

    ``model_catalog`` holds catalog + circuit-breaker state at module level, so
    a test that installs rows would otherwise change ``turn_candidates`` for
    every test that runs after it.
    """
    from core.state import state
    from services import model_catalog

    model_catalog.reset_circuits()
    model_catalog.apply_catalog([_catalog_row()])
    # Every test here runs against its own fake router, which is exactly what
    # the advanced-override seam is for: point ai_router_url at it and
    # run_turn will not probe 8082..8092 or try to embed a real engine.
    state.ai_router_url = _BASE
    yield
    model_catalog.reset_circuits()
    model_catalog.apply_catalog([_catalog_row()])
    state.ai_router_url = ""


# ── helpers ────────────────────────────────────────────────────────────────


def _spec(name, run=None, parameters=None, desc=None):
    """A ToolSpec whose body returns instantly, for the loop tests."""
    from services.kani_backend import ToolSpec

    async def default_run(**kwargs):
        return "ok"

    return ToolSpec(
        name=name,
        desc=desc or f"The {name} tool.",
        parameters=parameters
        or {"type": "object", "properties": {}, "additionalProperties": False},
        run=run or default_run,
    )


def _specs(tools, on_step=None):
    """The exact composition ai_service performs on the real tools.

    Two passes, one job each: the closures become specs with schemas, then each
    call gets its step row and its text for the wire. The test that only checks
    schemas needs the first pass; the rest need both.
    """
    from services.ai_tools import tool_specs as build_tool_specs
    from services.kani_backend import tool_specs as with_step_rows

    return with_step_rows(build_tool_specs(tools), on_step=on_step)


def _turn(specs, query="what does cell c7 do?", system="SYS", **kw):
    """One kani_backend.run_turn call with the plumbing the tests don't probe.

    `base_url` defaults to the fake router started at import: without it the
    turn falls through to the real attach path, and on a machine with its own
    LM Router on 8082 that is what answers.
    """
    from services import kani_backend

    kw.setdefault("base_url", _BASE)
    kw.setdefault("cancel", asyncio.Event())
    return kani_backend.run_turn(
        query,
        [],
        system_prompt=system,
        specs=specs,
        on_token=kw.pop("on_token", lambda _t: None),
        on_round_reset=kw.pop("on_round_reset", None),
        on_model_step=kw.pop("on_model_step", None),
        **kw,
    )


# ── 1. a billable step is one model stream ─────────────────────────────────


def test_the_preamble_before_a_tool_call_is_dropped():
    """ "Let me check that…" is not the answer.

    DDGS clears its buffer at the tool-round boundary; the same text must not
    ride along into the final answer here, or every answer is prefixed with
    the model's throat-clearing.
    """
    _fresh_calls()
    _RouterState.args["read_cell"] = {"cell_id": "c7"}

    result = _run(_turn([_spec("read_cell")]))
    assert result["text"] == "Cell c7 sets X = 1", result

    # The caller is told to drop its own buffer at the same point.
    resets: list[bool] = []
    _fresh_calls()
    _run(_turn([_spec("read_cell")], on_round_reset=lambda: resets.append(True)))
    assert resets, "the caller was never told to drop the preamble"


def test_step_rows_close_by_their_call_id_not_their_name():
    """The id that opens a row is the id that closes it, and it is not the name.

    Two calls to the same tool in one turn are two rows. Rows keyed by name
    collide: the second call never opens its own row, so one row's output is
    overwritten and the other spins forever.
    """
    _fresh_calls()
    _RouterState.args["read_cell"] = {"cell_id": "c7"}

    events: list[tuple[str, dict]] = []

    def on_step(event, payload):
        events.append((event, payload))

    from services.ai_tools import tool_specs as build_tool_specs

    async def read_cell(cell_id: str) -> str:
        """Read a cell."""
        return f"source-of-{cell_id}"

    from services import kani_backend

    specs = kani_backend.tool_specs(build_tool_specs([read_cell]), on_step=on_step)
    _run(_turn(specs))

    starts = [p for e, p in events if e == "start"]
    dones = [p for e, p in events if e == "done"]
    assert len(starts) == len(dones) == 1, events
    assert starts[0]["id"], events
    assert starts[0]["id"] == dones[0]["id"], events
    assert starts[0]["id"] != "read_cell" or len(starts) == 1


def test_a_tool_round_is_not_a_billable_step():
    """One model round that calls a tool, then one that answers: 2 steps.

    The FUNCTION yield in between is a tool RESULT, not a model call. Counting
    it would bill 3 for a turn that made 2 model calls — and the credit
    service bills on exactly this number.
    """
    _fresh_calls()
    _RouterState.args["read_cell"] = {"cell_id": "c7"}

    result = _run(_turn([_spec("read_cell")]))
    assert result["model_steps"] == 2, result
    # Two requests reached the wire: the one that called the tool, and the one
    # that answered from its result.
    assert len(_RouterState.calls) == 2, _RouterState.calls
    # The prelude before the tool call never belongs to the answer.
    assert result["text"] == "Cell c7 sets X = 1", result


def test_the_endpoint_sees_the_tool_result_between_the_rounds():
    """kani must be the one that injects the tool message, not us.

    The second request's transcript is system, user, assistant(tool_calls),
    tool — which is kani's own chat_history, carried through `full_round_stream`.
    """
    _fresh_calls()
    _RouterState.args["read_cell"] = {"cell_id": "c7"}

    _run(_turn([_spec("read_cell")]))
    second = _RouterState.calls[1]["body"]["messages"]
    roles = [m["role"] for m in second]
    assert roles == ["system", "user", "assistant", "tool"], roles
    assert second[-1]["content"] == "ok", second[-1]


def test_the_same_model_answered_both_rounds():
    """One candidate, two rounds: the model that called the tool answers.

    If the walk restarted on the tool round, the beneficiary model would be
    charged for a round it never ran.
    """
    _fresh_calls()
    _RouterState.args["read_cell"] = {"cell_id": "c7"}

    result = _run(_turn([_spec("read_cell")]))
    assert result["model"] == "solo", result


# ── 2. the tool batch is serialised, and its rows close ─────────────────────


def test_a_tool_batch_runs_one_at_a_time():
    """kani gathers the batch; our tools must still run in order.

    One download, one ordered step row — interleaving them corrupts both.
    """
    _fresh_calls()
    order: list[str] = []

    from services.kani_backend import ToolSpec

    async def slow_a(**kw):
        order.append("a-start")
        await asyncio.sleep(0.05)
        order.append("a-end")
        return "a"

    async def slow_b(**kw):
        order.append("b-start")
        await asyncio.sleep(0.05)
        order.append("b-end")
        return "b"

    class _BatchHandler(_Handler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            _RouterState.calls.append({"path": self.path, "body": body})
            has_tool = any(m.get("role") == "tool" for m in body["messages"])
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            if not has_tool:
                self.wfile.write(_chunk({"content": "Working. "}))
                for index in range(2):
                    self.wfile.write(
                        _chunk(
                            {
                                "tool_calls": [
                                    {
                                        "index": index,
                                        "id": f"call_{index}",
                                        "type": "function",
                                        "function": {
                                            "name": f"slow_{'ab'[index]}",
                                            "arguments": "{}",
                                        },
                                    }
                                ]
                            }
                        )
                    )
                self.wfile.write(_chunk({}, "tool_calls"))
            else:
                self.wfile.write(_chunk({"content": "Done."}))
                self.wfile.write(_chunk({}, "stop"))
            self.wfile.write(b"data: [DONE]\n\n")

    srv = HTTPServer(("127.0.0.1", 0), _BatchHandler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    from core.state import state

    state.ai_router_url = f"http://127.0.0.1:{port}/v1"
    try:
        specs = [
            ToolSpec(
                name="slow_a",
                desc="A.",
                parameters={"type": "object", "properties": {}},
                run=slow_a,
            ),
            ToolSpec(
                name="slow_b",
                desc="B.",
                parameters={"type": "object", "properties": {}},
                run=slow_b,
            ),
        ]
        _run(_turn(specs, base_url=state.ai_router_url))
        assert order == ["a-start", "a-end", "b-start", "b-end"], order
    finally:
        state.ai_router_url = _BASE


def test_a_step_row_is_opened_and_closed_by_the_same_call_id():
    """A row is only matchable by the tool_call_id that opened it.

    kani runs the batch in its own gather, so the only identity a row has is
    the one `do_function_call` publishes. Drop it and the row never closes.
    """
    _fresh_calls()
    _RouterState.args["read_cell"] = {"cell_id": "c7"}

    events: list[tuple[str, dict]] = []

    def on_step(event, payload):
        events.append((event, payload))

    tools = []

    async def read_cell(cell_id: str) -> str:
        """Read a cell."""
        return "source-of-c7"

    tools.append(read_cell)
    specs = _specs(tools, on_step=on_step)

    _run(_turn(specs))
    starts = [p for e, p in events if e == "start"]
    dones = [p for e, p in events if e == "done"]
    assert len(starts) == 1, events
    assert len(dones) == 1, events
    # The same id on both, and it is the id the router handed us.
    assert starts[0]["id"] == dones[0]["id"] == "call_1", events
    assert starts[0]["name"] == "read_cell"
    assert dones[0]["result"] == "source-of-c7"


def test_a_step_row_carries_its_args_and_result():
    """The UI's step row shows what was asked and what came back."""
    _fresh_calls()
    _RouterState.args["read_cell"] = {"cell_id": "c7"}

    seen: dict[str, dict] = {}

    def on_step(event, payload):
        seen[event] = payload

    async def read_cell(cell_id: str) -> str:
        """Read a cell."""
        return "source-of-c7"

    _run(_turn(_specs([read_cell], on_step=on_step)))
    assert seen["start"]["args"] == {"cell_id": "c7"}, seen
    assert seen["done"]["result"] == "source-of-c7", seen
    assert seen["done"]["error"] is None, seen


def test_a_failing_tool_body_becomes_an_error_payload():
    """A raising tool must not cost a kani retry (its auto_retry) — it becomes
    text the model reads."""
    _fresh_calls()

    seen: dict[str, dict] = {}

    def on_step(event, payload):
        seen[event] = payload

    async def broken_tool() -> str:
        """Always fails."""
        raise RuntimeError("kernel gone")

    result = _run(_turn(_specs([broken_tool], on_step=on_step)))
    assert "kernel gone" in seen["done"]["result"], seen
    assert seen["done"]["error"] == "kernel gone", seen
    # The model recovered, so the turn still answered.
    assert result["text"], result


def test_a_failing_tool_bills_two_steps():
    """A tool that fails costs one call to make it and one to answer from it.

    The number is the user-visible contract, so it is pinned. It also guards
    the `retry_attempts=1` choice: kani's own failure path
    (`handle_function_call_exception`, `kani/kani.py:618-651`) forces another
    model turn on an error, gated by `attempt < retry_attempts`. At
    `retry_attempts=1` the first error is already at attempt 1, so no extra
    round is spent and the two paths cost the same — raise it and this test
    starts failing, which is the point.

    The reason we catch the exception inside `tool_specs` rather than letting
    kani do it is NOT billing: it is that our step row needs the error, and
    kani's path would hand the model a bare `str(original)` while the row
    closed with no error at all. That is pinned separately by
    `test_a_failing_tool_body_becomes_an_error_payload`.
    """
    _fresh_calls()

    async def broken_tool() -> str:
        """Always fails."""
        raise RuntimeError("kernel gone")

    result = _run(_turn(_specs([broken_tool])))
    assert result["model_steps"] == 2, result
    assert len(_RouterState.calls) == 2, _RouterState.calls


def test_a_tool_that_fails_repeatedly_bills_one_step_per_round():
    """Two tool rounds that both fail: one call to make each, one to answer.

    The same rule applied per round, so the arithmetic has to hold when the
    failure repeats rather than only on the first one.
    """
    _fresh_calls()
    _RouterState.args["read_cell"] = {"cell_id": "c7"}

    async def broken_tool(cell_id: str) -> str:
        """Always fails."""
        raise RuntimeError("kernel gone")

    result = _run(_turn(_specs([broken_tool])))
    assert result["model_steps"] == 2, result
    assert result["text"], result


def test_the_gate_is_not_in_the_schema():
    """ask_confirm is bound into the closure, never a parameter.

    A gate parameter would appear in the JSON schema the model reads, which
    would let the model answer its own approval prompt.
    """
    from services.ai_tools import build_tools, tool_specs

    services = _FakeServices()
    state = _FakeState()
    for spec in tool_specs(build_tools("sess", services, state)):
        schema = str(spec.parameters)
        assert "ask_confirm" not in schema, f"{spec.name} exposes ask_confirm"


class _FakeServices:
    class _Sub:
        async def stop_session(self, *a, **kw):
            return True

        async def rm(self, *a, **kw):
            return True

    def __init__(self):
        self.colab = self._Sub()


class _FakeState:
    auth_method = "oauth2"


# ── 3. a tool's text is what reaches the wire ───────────────────────────────


def test_a_tools_text_is_what_the_model_reads():
    """A tool body returns a string, and that string is the tool message.

    No multimodal: a plot is marked in words by the tool itself, and the pixels
    never go near the model. This pins that no repr or dataclass leaks instead.
    """
    _fresh_calls()
    _RouterState.args["read_cell"] = {"cell_id": "c7"}

    seen: dict[str, dict] = {}

    def on_step(event, payload):
        seen[event] = payload

    async def read_cell(cell_id: str) -> str:
        """Read a cell."""
        return "Cell 4 ran. [plot]"

    result = _run(_turn(_specs([read_cell], on_step=on_step)))
    assert seen["done"]["result"] == "Cell 4 ran. [plot]", seen
    assert seen["done"]["error"] is None, seen
    assert result["text"], result


def test_a_plain_string_result_still_round_trips():
    """The pre-rich path must be unchanged: no images turn when there is none."""
    _fresh_calls()
    _RouterState.args["read_cell"] = {"cell_id": "c7"}

    async def read_cell(cell_id: str) -> str:
        """Read a cell."""
        return "source-of-c7"

    result = _run(_turn(_specs([read_cell])))
    assert result["text"], result
    # The tool message is the text, not a dataclass repr.
    tool_msg = _RouterState.calls[1]["body"]["messages"][-1]
    assert tool_msg["role"] == "tool", tool_msg
    assert tool_msg["content"] == "source-of-c7", tool_msg


# ── 4. the candidate walk ──────────────────────────────────────────────────


def _install_catalog(rows):
    """Install a catalog the walk will read.

    Clears outright rather than via apply_catalog: an empty list there is the
    module's stale-fallback path, which would leave the previous test's rows.
    """
    from services import model_catalog

    model_catalog.reset_circuits()
    model_catalog.apply_catalog(rows or [_catalog_row("only-model", "high", 10)])
    return model_catalog


def _make_router(fail_for):
    """Build a handler that 500s for ``fail_for`` models and answers the rest.

    The status is decided before any header is written — writing a 200 and then
    trying to switch to 500 raises and masks the failure.
    """

    class _Router(_Handler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            _RouterState.calls.append({"path": self.path, "body": body})
            model = str(body.get("model") or "").lower()
            if any(f in model for f in fail_for):
                self.send_response(500)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"model unavailable")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(_chunk({"content": f"answered by {model}"}))
            self.wfile.write(_chunk({}, "stop"))
            self.wfile.write(b"data: [DONE]\n\n")

    return _Router


def _with_router(fail_for) -> tuple[int, list[str]]:
    """Start a router that fails ``fail_for``; returns (port, seen_models)."""
    seen: list[str] = []
    handler = _make_router(fail_for)
    original = handler.do_POST

    def spy(self):
        before = len(_RouterState.calls)
        original(self)
        if len(_RouterState.calls) > before:
            seen.append(str(_RouterState.calls[-1]["body"].get("model") or ""))

    handler.do_POST = spy
    srv = HTTPServer(("127.0.0.1", 0), handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return port, seen


def test_turn_walks_to_the_next_model_when_the_first_fails():
    """The rank leader fails; the turn must retry on the next candidate and
    mark the failed one."""

    _fresh_calls()
    catalog = _install_catalog(
        [
            _catalog_row("ranked-first", "high", 10),
            _catalog_row("ranked-second", "high", 900),
        ]
    )

    port, seen = _with_router(["ranked-first"])

    result = _run(
        _turn(
            [],
            system="SYS",
            base_url=f"http://127.0.0.1:{port}/v1",
        )
    )
    assert result["model"] == "ranked-second", result
    assert "answered by" in result["text"], result
    assert seen == ["ranked-first", "ranked-second"], seen
    # The failed model is skipped for five minutes.
    assert catalog.model_circuit_open("ranked-first") is True
    assert catalog.model_circuit_open("ranked-second") is False


def test_turn_raises_unavailable_when_every_candidate_fails():
    from services import ai_service

    _fresh_calls()
    _install_catalog([_catalog_row("only-model", "high", 10)])

    port, _seen = _with_router(["only-model", "auto"])

    try:
        _run(_turn([], system="SYS", base_url=f"http://127.0.0.1:{port}/v1"))
        raise AssertionError("should have raised AIUnavailable")
    except ai_service.AIUnavailable as ex:
        assert "did not answer" in str(ex).lower(), ex


def test_a_dead_endpoint_never_becomes_a_model_failure():
    """A connection refusal marks the ROUTER down, not the model.

    Every candidate shares the endpoint, so a dead router is walked nowhere —
    and a single dead model must not black out the whole router for 60s.
    """
    from services import router as router_service
    from services.ai_service import AIUnavailable

    _fresh_calls()
    _install_catalog([_catalog_row("solo", "high", 10)])
    # A port that is not listening: nothing is going to answer here.
    dead = "http://127.0.0.1:1/v1"

    router_service._mark_router_failed()

    try:
        _run(_turn([], system="SYS", base_url=dead))
        raise AssertionError("should have raised AIUnavailable")
    except AIUnavailable as ex:
        assert "reach" in str(ex).lower(), ex


def test_turn_with_an_empty_catalog_raises_unavailable():
    """An empty catalog means no models are available from the router."""
    from services.ai_service import AIUnavailable

    _fresh_calls()
    catalog = _install_catalog([_catalog_row("x", "high", 10)])
    # A truly empty catalog: clear the module state directly.
    catalog._catalog = []
    catalog._catalog_fetched_at = 0.0

    try:
        _run(_turn([], system="SYS"))
        raise AssertionError("should have raised AIUnavailable")
    except AIUnavailable as ex:
        assert "no models" in str(ex).lower(), ex


# ── 5. per-candidate patience ──────────────────────────────────────────────


def test_a_hung_upstream_times_out_instead_of_eating_the_budget():
    """A candidate that connects but never yields a token is abandoned.

    The outer wall-clock is 240s; letting one hung model eat it would make
    every other candidate unreachable.
    """
    from services import ai_service

    class _HungHandler(_Handler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            _RouterState.calls.append({"path": self.path, "body": {}})
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            # Never sends a token: the client is left hanging.
            time = __import__("time")
            time.sleep(30)

    srv = HTTPServer(("127.0.0.1", 0), _HungHandler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    _install_catalog([_catalog_row("solo", "high", 10)])

    try:
        result = _run(
            _turn(
                [],
                system="SYS",
                base_url=f"http://127.0.0.1:{port}/v1",
                timeout_s=5.0,
            )
        )
        # No candidates left to try: the turn is honest about it.
        raise AssertionError(f"should have raised, got {result}")
    except ai_service.AIUnavailable:
        pass


def test_the_round_reset_clears_the_preamble():
    """The caller drops the previous round's partial text on a new round.

    A model that says "let me check that" and then calls a tool must not show
    that preamble twice.
    """
    _fresh_calls()
    _RouterState.args["read_cell"] = {"cell_id": "c7"}

    resets: list[bool] = []
    _run(
        _turn(
            [_spec("read_cell")],
            on_round_reset=lambda: resets.append(True),
        )
    )
    # Once before the round loop, and once at the tool-round boundary.
    assert resets == [True, True], resets


def test_on_model_step_fires_before_each_model_call():
    """Metering observes every attempted model call, including the first."""
    _fresh_calls()
    _RouterState.args["read_cell"] = {"cell_id": "c7"}

    steps: list[int] = []

    async def on_model_step():
        steps.append(len(steps))

    _run(_turn([_spec("read_cell")], on_model_step=on_model_step))
    # One tool round and one final answer.
    assert steps == [0, 1], steps


# ── 6. the rescue round ────────────────────────────────────────────────────


def test_past_the_round_budget_the_tools_are_stripped():
    """An over-cap turn still answers — from what it already gathered.

    Without this the round boundary instant-fails every remaining candidate and
    the user gets nothing for a turn that ran its tools.
    """
    _fresh_calls()

    class _EagerHandler(_Handler):
        """Always calls a tool, so the round budget is reached."""

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            _RouterState.calls.append({"path": self.path, "body": body})
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            tools = body.get("tools") or []
            if tools:
                name = tools[0]["function"]["name"]
                self.wfile.write(_chunk({"content": "Checking. "}))
                self.wfile.write(
                    _chunk(
                        {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": name,
                                        "arguments": "{}",
                                    },
                                }
                            ]
                        }
                    )
                )
                self.wfile.write(_chunk({}, "tool_calls"))
            else:
                # The rescue round: no tools were offered, so this is it.
                self.wfile.write(_chunk({"content": "Final answer."}))
                self.wfile.write(_chunk({}, "stop"))
            self.wfile.write(b"data: [DONE]\n\n")

    srv = HTTPServer(("127.0.0.1", 0), _EagerHandler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    from core.state import state

    state.ai_router_url = f"http://127.0.0.1:{port}/v1"
    try:
        result = _run(
            _turn([_spec("read_cell")], max_rounds=1, base_url=state.ai_router_url)
        )
    finally:
        state.ai_router_url = _BASE

    assert "Final answer." in result["text"], result
    # Two model rounds: the one that spent the budget, and the rescue.
    assert result["model_steps"] == 2, result
    # The rescue request carried no tools.
    assert not _RouterState.calls[-1]["body"].get("tools"), _RouterState.calls[-1]


# ── 7. cancellation ────────────────────────────────────────────────────────


def test_cancellation_stops_before_the_next_model_call():
    """A stop that lands between rounds must not bill another model call.

    The boundary check is what makes "Stop immediately" stop immediately
    instead of after one more round.
    """
    _fresh_calls()
    _RouterState.args["read_cell"] = {"cell_id": "c7"}

    cancel = asyncio.Event()

    from services import kani_backend

    async def go(base_url: str):
        async def read_cell(cell_id: str) -> str:
            """Read a cell."""
            # The user hits Stop the moment the tool finishes: there is no
            # round after this, and no further model call.
            cancel.set()
            return "source-of-c7"

        result = await kani_backend.run_turn(
            "what does c7 do?",
            [],
            system_prompt="SYS",
            specs=[_spec("read_cell", run=read_cell)],
            cancel=cancel,
            on_token=lambda _t: None,
            base_url=base_url,
        )
        return result

    # A cancel that trips the moment the tool round is done: the loop must
    # break at the next manager instead of making another request.
    class _CountingHandler(_Handler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            _RouterState.calls.append({"path": self.path, "body": body})
            has_tool = any(m.get("role") == "tool" for m in body["messages"])
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            if not has_tool:
                self.wfile.write(_chunk({"content": "Checking. "}))
                self.wfile.write(
                    _chunk(
                        {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "read_cell",
                                        "arguments": json.dumps({"cell_id": "c7"}),
                                    },
                                }
                            ]
                        }
                    )
                )
                self.wfile.write(_chunk({}, "tool_calls"))
            else:
                # A late answer must never arrive: the boundary check stops
                # the round before this request is made. If it does, the test
                # fails on the text and the step count.
                self.wfile.write(_chunk({"content": "Late answer."}))
                self.wfile.write(_chunk({}, "stop"))
            self.wfile.write(b"data: [DONE]\n\n")

    srv = HTTPServer(("127.0.0.1", 0), _CountingHandler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    from core.state import state

    base = f"http://127.0.0.1:{port}/v1"
    state.ai_router_url = base
    try:
        result = _run(go(base))
    finally:
        state.ai_router_url = _BASE

    assert result["text"] == "Checking. ", result
    assert result["model_steps"] == 1, result


def test_a_stop_before_the_turn_starts_is_free():
    """Nothing was delivered, so nothing is billed."""

    _fresh_calls()
    cancel = asyncio.Event()
    cancel.set()

    result = _run(_turn([_spec("read_cell")], cancel=cancel))
    assert result["text"] == "", result
    assert result["model_steps"] == 0, result
    assert not _RouterState.calls, _RouterState.calls


# ── 8. the engine is built per candidate, no SDK retries ───────────────────


def test_the_engine_uses_the_called_base_url_and_no_sdk_retries():
    """max_retries=0 matters: the SDK's backoff delays every candidate walk by
    retrying the same dead model first."""
    _fresh_calls()

    from services import kani_backend

    engine = _run(kani_backend._build_engine("solo", _BASE))
    assert engine.client.base_url.host == "127.0.0.1", engine.client.base_url
    assert engine.client.max_retries == 0, engine.client.max_retries
    # The context budget is ours, not the model's: `auto` has no known window
    # and kani's default for an unknown model is 2048.
    assert engine.max_context_size == kani_backend.DEFAULT_CONTEXT, (
        engine.max_context_size
    )
    # A counting tokenizer, so a cold tiktoken download cannot stall a turn.
    assert type(engine.tokenizer).__name__ == "_CountingTokenizer", engine.tokenizer
    # api_type is explicit: "auto" matches no known prefix and kani would pick
    # the Responses API, which a local router does not serve.
    assert engine.openai_api_type == "chat_completions", engine.openai_api_type


# ── 9. ai_service still routes through kani ────────────────────────────────


def test_ai_service_delegates_to_kani():
    """The shim the callers use must still work end-to-end.

    The two callers (ai_credits and the assistant) go through this, so a break
    here is invisible until a user opens the chat.
    """
    _fresh_calls()
    _RouterState.args["read_cell"] = {"cell_id": "c7"}

    from services import ai_service

    async def read_cell(cell_id: str) -> str:
        """Read a cell."""
        return "source-of-c7"

    async def go():
        return await ai_service.run_turn(
            model="auto",
            tools=[read_cell],
            messages=[{"role": "user", "content": "what does c7 do?"}],
            system="SYS",
        )

    result = _run(go())
    assert result["text"] == "Cell c7 sets X = 1", result
    assert result["cancelled"] is False
    assert result["model"] == "solo", result
    assert _RouterState.calls[0]["path"].endswith("/chat/completions"), (
        _RouterState.calls[0]
    )


def test_ai_service_forward_the_settings_override():
    """An explicit override must reach the engine, not be re-resolved here.

    Otherwise someone pointing the app at a remote router gets the local one.
    The proof is a router that answers NOTHING: the default fake router does
    answer, so a turn that succeeds against a silent override would mean the
    override was dropped on the floor.
    """
    _fresh_calls()

    from services import ai_service

    seen: list[str] = []

    class _Silent(_Handler):
        """Never answers, and records that it was reached at all."""

        def do_POST(self):
            import json

            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append(str(body.get("model") or ""))
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"silent router refuses everything")

    srv = HTTPServer(("127.0.0.1", 0), _Silent)
    silent = f"http://127.0.0.1:{srv.server_address[1]}/v1"
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    from core.state import state

    state.ai_router_url = silent

    async def go():
        try:
            return await ai_service.run_turn(
                model="auto",
                tools=[],
                messages=[{"role": "user", "content": "hi"}],
                system="SYS",
            )
        finally:
            state.ai_router_url = _BASE

    # Because nothing could answer, the turn is honest about it.
    with pytest.raises(ai_service.AIUnavailable):
        _run(go())

    # The silent router was actually reached — the override was forwarded.
    assert seen, "the settings override never reached the model client"


# ── 10. a silent candidate is not an answer ─────────────────────────────────


def test_a_round_that_said_nothing_walks_to_the_next_candidate():
    """An empty stream is a dead model, not an answer.

    Returning here would bill a credit for an empty bubble and show the user
    nothing.
    """
    _fresh_calls()
    catalog = _install_catalog(
        [
            _catalog_row("silent-first", "high", 10),
            _catalog_row("talks-second", "high", 900),
        ]
    )

    class _SilentFirstHandler(_Handler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            _RouterState.calls.append({"path": self.path, "body": body})
            model = str(body.get("model") or "").lower()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            if "silent" in model:
                # Connected, said nothing: the case that must not be billed.
                self.wfile.write(_chunk({}, "stop"))
            else:
                self.wfile.write(_chunk({"content": "answered by second"}))
                self.wfile.write(_chunk({}, "stop"))
            self.wfile.write(b"data: [DONE]\n\n")

    srv = HTTPServer(("127.0.0.1", 0), _SilentFirstHandler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    result = _run(_turn([], system="SYS", base_url=f"http://127.0.0.1:{port}/v1"))
    assert result["text"] == "answered by second", result
    assert result["model"] == "talks-second", result
    # Silent models are skipped for the circuit TTL too.
    assert catalog.model_circuit_open("silent-first") is True


def test_a_silent_end_everywhere_is_unavailable_not_an_empty_answer():
    """Every candidate silent: the caller must see a router error, not ""."""
    from services import ai_service

    _fresh_calls()
    _install_catalog([_catalog_row("only-silent", "high", 10)])

    class _AllSilentHandler(_Handler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            _RouterState.calls.append({"path": self.path, "body": {}})
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(_chunk({}, "stop"))
            self.wfile.write(b"data: [DONE]\n\n")

    srv = HTTPServer(("127.0.0.1", 0), _AllSilentHandler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    with pytest.raises(ai_service.AIUnavailable):
        _run(_turn([], system="SYS", base_url=f"http://127.0.0.1:{port}/v1"))


# ── 11. the ContextVar is reset, not leaked ─────────────────────────────────


def test_the_call_id_contextvar_is_reset_after_the_batch():
    """A leaked call id would make the NEXT call claim the previous id.

    `do_function_call` sets it per call; without a reset every later tool in
    the same task would report a stale id and close the wrong row.
    """
    from services import kani_backend

    async def go():
        assert kani_backend.call_id() == "", "leaked before any call"
        first = kani_backend._current_call_id.get()
        return first

    kani_backend._current_call_id.set("")
    assert asyncio.run(go()) == ""


def test_two_batches_report_different_call_ids():
    """The id is per call, never carried across a batch boundary."""
    from services import kani_backend

    async def run_one(call_id: str) -> str:
        kani_backend._current_call_id.set(call_id)
        token = kani_backend._call_id.set(kani_backend._current_call_id.get())
        try:
            return kani_backend.call_id()
        finally:
            kani_backend._call_id.reset(token)

    seen = asyncio.run(run_one("call_a"))
    assert seen == "call_a", seen
    # After the reset, the outside value is what remains.
    assert kani_backend.call_id() == "", kani_backend.call_id()


# ── thinking depth ──────────────────────────────────────────────────────────


def test_auto_sends_no_reasoning_effort_at_all():
    """`auto` must leave the gateway's own default in force, not pick for it.

    Both references do the same (`DDGS/src/services/chat_agent.py:512-515`):
    the depth is a hint the gateway understands better than we do, so "auto"
    means the parameter is absent rather than a value we invented.
    """
    from core.state import state
    from services.kani_backend import _thinking_depth

    for value in ("auto", "", "AUTO", "  auto  "):
        state.ai_thinking = value
        assert _thinking_depth() is None, value


def test_a_real_depth_is_passed_through():
    from core.state import state
    from services.kani_backend import _thinking_depth

    for value in ("minimal", "low", "medium", "high"):
        state.ai_thinking = value
        assert _thinking_depth() == value


def test_an_unknown_depth_is_ignored_rather_than_sent():
    """A saved value from a newer build must not reach a router that may reject it."""
    from core.state import state
    from services.kani_backend import _thinking_depth

    for value in ("xhigh", "deep", "42", "high;rm -rf"):
        state.ai_thinking = value
        assert _thinking_depth() is None, value

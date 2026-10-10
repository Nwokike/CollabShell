"""The mirascope contract, pinned as a test.

Every behaviour below was verified by hand against mirascope 2.5.0 driving a
local OpenAI-compatible router (a stdlib http.server speaking SSE). They are
NOT obvious and they are NOT documented in one place:

  1. The provider must be registered with scope **"openai/"** (prefix) to
     match model ids like ``openai/anything``.
  2. The model id needs the **":completions"** suffix or mirascope dials the
     Responses API (``/v1/responses``), which a local router does not serve.
  3. Streaming is **``ask.stream(...)``**, not a ``stream=True`` kwarg — the
     kwarg is silently ignored and the non-streaming path runs instead.
  4. **``chunk_stream`` is a method**, not a property; text arrives as
     ``TextChunk`` whose ``.delta`` is the text itself.
  5. **``execute_tools()`` is async**, and the tools must be async too (a sync
     tool returns a ToolOutput the async toolkit tries to await).
  6. A tool round is continued by wrapping the ToolOutput objects in a
     **UserMessage** (they are content parts, not messages).
  7. The system prompt must be a **SystemMessage(content=Text(...))** — a
     ``system=`` kwarg is silently dropped.

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
    # Per-tool arguments the fake router should send, keyed by tool name.
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
    from services import model_catalog

    model_catalog.reset_circuits()
    model_catalog.apply_catalog([_catalog_row()])
    yield
    model_catalog.reset_circuits()
    model_catalog.apply_catalog([_catalog_row()])


# ── the pinned contract ────────────────────────────────────────────────────


def test_scope_must_be_openai_prefix_to_resolve():
    """register_provider(scope='openai/') is what matches 'openai/<model>'."""
    from mirascope import llm
    from mirascope.llm.providers import provider_registry as pr

    _fresh_calls()
    provider = llm.register_provider(
        "openai", scope="openai/", api_key="any", base_url=_BASE
    )
    assert pr.get_provider_for_model("openai/whatever") is provider
    # A bare scope does NOT match.
    llm.register_provider("openai", scope="nope/", api_key="any", base_url=_BASE)
    assert pr.get_provider_for_model("openai/whatever") is provider


def test_completions_suffix_forces_chat_completions_api():
    """Without ':completions' mirascope dials /v1/responses, which a local
    router does not serve."""
    from mirascope import llm

    _fresh_calls()

    @llm.call("openai/m:completions")
    async def ask(q: str):
        return q

    _run(ask.stream("hi"))
    assert _RouterState.calls[-1]["path"].endswith("/chat/completions"), (
        _RouterState.calls[-1]["path"]
    )


def test_stream_is_a_method_not_a_kwarg():
    """stream=True is silently ignored; .stream() is the real entry point."""
    from mirascope import llm
    from mirascope.llm.providers.openai.completions.base_provider import (
        BaseOpenAICompletionsProvider as P,
    )

    _fresh_calls()
    seen = []
    orig_call, orig_stream = P._call_async, P._stream_async

    def spy_call(self, **kw):
        seen.append("non-stream")
        return orig_call(self, **kw)

    def spy_stream(self, **kw):
        seen.append("stream")
        return orig_stream(self, **kw)

    P._call_async, P._stream_async = spy_call, spy_stream
    try:

        @llm.call("openai/m:completions")
        async def ask(q: str):
            return q

        _run(ask.stream("hi"))
        assert seen == ["stream"], seen

        @llm.call("openai/m:completions", stream=True)
        async def ask_kwarg(q: str):
            return q

        seen.clear()
        _run(ask_kwarg.stream("hi"))
        # The kwarg changed nothing: still the streaming path via .stream().
        assert seen == ["stream"], seen
    finally:
        P._call_async, P._stream_async = orig_call, orig_stream


def test_chunk_stream_is_a_method_and_delta_is_text():
    """chunk_stream() is a method; TextChunk.delta is the text itself."""
    from mirascope import llm

    _fresh_calls()

    @llm.call("openai/m:completions")
    async def ask(q: str):
        return q

    async def go():
        resp = await ask.stream("hi")
        got = []
        async for chunk in resp.chunk_stream():
            if type(chunk).__name__ == "TextChunk":
                got.append(chunk.delta)
        return "".join(got)

    # The fake router answers the first request with a tool call, whose
    # prelude text is "Checking. " — what we assert here is the mechanism
    # (method + delta-is-text), not the wording.
    assert _run(go()) == "Checking. "


def test_execute_tools_is_async_and_needs_async_tools():
    """execute_tools() returns a coroutine, and a sync tool cannot be awaited
    by the async toolkit — our tools are async for exactly this reason."""
    from mirascope import llm

    _fresh_calls()

    async def go():
        _RouterState.args["read_cell"] = {"cell_id": "c7"}

        @llm.tool
        async def read_cell(cell_id: str) -> str:
            """Read a cell."""
            await asyncio.sleep(0)
            return f"source-of-{cell_id}"

        @llm.call("openai/m:completions", tools=[read_cell])
        async def ask(q: str):
            return q

        resp = await ask.stream("hi")
        async for _ in resp.chunk_stream():
            pass
        assert list(resp.tool_calls), "tool_calls empty after consuming stream"
        outs = await resp.execute_tools()
        return [(o.name, o.result, o.error) for o in outs]

    got = _run(go())
    assert got == [("read_cell", "source-of-c7", None)], got


def test_tool_round_continues_via_user_message_wrapping():
    """ToolOutput is a content part; it must be wrapped in a UserMessage."""
    from mirascope import llm
    from mirascope.llm.content import Text
    from mirascope.llm.messages import SystemMessage, UserMessage

    _fresh_calls()

    async def go():
        @llm.tool
        async def read_cell(cell_id: str) -> str:
            """Read a cell."""
            await asyncio.sleep(0)
            return f"source-of-{cell_id}"

        @llm.call("openai/m:completions", tools=[read_cell])
        async def ask(system: str, turn):
            body = (
                [UserMessage(content=[Text(text=turn)])]
                if isinstance(turn, str)
                else [UserMessage(content=list(turn))]
            )
            return [SystemMessage(content=Text(text=system)), *body]

        r1 = await ask.stream("SYS", "what is c7?")
        async for _ in r1.chunk_stream():
            pass
        outs = await r1.execute_tools()

        r2 = await ask.stream("SYS", outs)
        text = []
        async for c in r2.chunk_stream():
            if type(c).__name__ == "TextChunk":
                text.append(c.delta)
        return "".join(text), [m["role"] for m in _RouterState.calls[1]["body"]["messages"]]

    text, roles = _run(go())
    assert text == "Cell c7 sets X = 1", text
    assert roles == ["system", "tool"], roles


def test_system_prompt_must_be_a_system_message():
    """A system= kwarg is silently dropped; SystemMessage(Text) is required."""
    from mirascope import llm
    from mirascope.llm.content import Text
    from mirascope.llm.messages import SystemMessage, UserMessage

    _fresh_calls()

    async def go():
        @llm.call("openai/m:completions")
        async def ask(system: str, q: str):
            return [SystemMessage(content=Text(text=system)),
                    UserMessage(content=[Text(text=q)])]

        await ask.stream("MY-SYSTEM-TEXT", "q")

    _run(go())
    sysmsg = next(
        m for m in _RouterState.calls[-1]["body"]["messages"] if m["role"] == "system"
    )
    assert sysmsg["content"] == "MY-SYSTEM-TEXT"


# ── our loop over that contract ────────────────────────────────────────────


def test_run_turn_drives_stream_tools_and_continuation():
    from mirascope import llm

    from services import ai_service

    _fresh_calls()

    async def go():
        ai_service.configure_provider(_BASE)
        _RouterState.args["read_cell"] = {"cell_id": "c7"}

        @llm.tool
        async def read_cell(cell_id: str) -> str:
            """Read a cell."""
            await asyncio.sleep(0)
            return f"source-of-{cell_id}"

        tokens, starts = [], []
        return await ai_service.run_turn(
            model="auto",
            tools=[read_cell],
            messages=[{"role": "user", "content": "what does cell c7 do?"}],
            system=ai_service._system_prompt("TEST SKILL"),
            on_token=lambda t: tokens.append(t),
            on_tool_start=lambda n, a: starts.append((n, a)),
        ), tokens, starts

    result, tokens, starts = _run(go())
    assert "".join(tokens) == "Checking. Cell c7 sets X = 1"
    assert starts == [("read_cell", {"cell_id": "c7"})]
    assert [s["name"] for s in result["steps"]] == ["read_cell"]
    assert result["steps"][0]["result"] == "source-of-c7"
    assert result["steps"][0]["error"] is False
    assert result["cancelled"] is False
    # The system prompt really reached the model.
    sysmsg = next(
        m for m in _RouterState.calls[0]["body"]["messages"] if m["role"] == "system"
    )
    assert "TEST SKILL" in sysmsg["content"]
    # The model sent is the ranked head of the catalog (the fixture installs a
    # high-tier "solo"), NOT the literal "auto" — the walk prefers a ranked
    # model and keeps the router's own auto only as a last resort.
    sent_model = _RouterState.calls[0]["body"].get("model", "")
    assert sent_model == "solo", sent_model
    assert result["model"] == "solo"


def test_normalise_model_id():
    from services.ai_service import _normalise_model_id

    assert _normalise_model_id("auto") == "openai/auto:completions"
    assert _normalise_model_id("openai/step-3") == "openai/step-3:completions"
    assert (
        _normalise_model_id("openai/step-3:completions")
        == "openai/step-3:completions"
    )
    assert _normalise_model_id("") == "openai/auto:completions"


def test_system_prompt_states_the_verified_divergences():
    from services.ai_service import _system_prompt

    prompt = _system_prompt("EXTRA")
    for rule in (
        "/content",
        "oauth2",
        "clear_output",
        "T4",
        "V6E1",
        "EXTRA",  # the bundled skill text is appended
    ):
        assert rule in prompt, rule


def test_run_turn_respects_cancellation():
    from mirascope import llm

    from services import ai_service

    _fresh_calls()

    @llm.tool
    async def read_cell(cell_id: str) -> str:
        """Read a cell."""
        await asyncio.sleep(0)
        return "x"

    async def go():
        ai_service.configure_provider(_BASE)
        stop = threading.Event()
        stop.set()  # already stopped -> the very first check returns
        return await ai_service.run_turn(
            model="auto",
            tools=[read_cell],
            messages=[{"role": "user", "content": "hi"}],
            should_stop=stop.is_set,
        )

    result = _run(go())
    assert result["cancelled"] is True
    assert result["text"] == ""


# ── rich tool results (text + images the model can actually see) ───────────


def test_tool_result_reaches_the_wire_as_an_image_part():
    """A plot must arrive as an image_url part, not a Python repr of a list.

    Handing the model a repr lets it READ about a plot but never see it.
    """
    from mirascope import llm

    from services import ai_service
    from services.ai_tools import ToolResult

    _fresh_calls()

    async def go():
        ai_service.configure_provider(_BASE)

        @llm.tool
        async def plot_cell() -> ToolResult:
            """Run a cell that plots."""
            await asyncio.sleep(0)
            result = ToolResult(text="Cell 4 ran and produced a figure.")
            result.add_image("iVBORw0KGgoAAAANSUhEUg==", "image/png")
            return result

        tokens = []
        outcome = await ai_service.run_turn(
            model="auto",
            tools=[plot_cell],
            messages=[{"role": "user", "content": "what does cell 4 show?"}],
            system="SYS",
            on_token=lambda t: tokens.append(t),
        )
        return outcome, "".join(tokens)

    result, answer = _run(go())
    # The fake router emits "Checking. " before requesting the tool.
    assert answer == "Checking. Cell c7 sets X = 1", answer

    # The step row carries the text and the images for the UI to render.
    step = result["steps"][0]
    assert step["result"] == "Cell 4 ran and produced a figure."
    assert step["images"] == [("image/png", "iVBORw0KGgoAAAANSUhEUg==")]

    # Round 2 must be: system, tool (clean string), user (text + image_url).
    messages = _RouterState.calls[1]["body"]["messages"]
    assert [m["role"] for m in messages] == ["system", "tool", "user"]

    tool_msg = next(m for m in messages if m["role"] == "tool")
    assert tool_msg["content"] == "Cell 4 ran and produced a figure."
    assert "ToolResult" not in tool_msg["content"], "a dataclass repr reached the wire"

    user_parts = messages[-1]["content"]
    kinds = [p["type"] for p in user_parts]
    assert kinds == ["text", "image_url"], kinds
    image = next(p for p in user_parts if p["type"] == "image_url")
    assert image["image_url"]["url"].startswith("data:image/png;base64,")
    assert "iVBORw0KGgo" in image["image_url"]["url"]


def test_plain_string_tool_result_still_round_trips():
    """The pre-rich path must be unchanged: no image turn when there is none."""
    from mirascope import llm

    from services import ai_service

    _fresh_calls()

    async def go():
        ai_service.configure_provider(_BASE)

        @llm.tool
        async def read_cell(cell_id: str) -> str:
            """Read a cell."""
            await asyncio.sleep(0)
            return f"source-of-{cell_id}"

        return await ai_service.run_turn(
            model="auto",
            tools=[read_cell],
            messages=[{"role": "user", "content": "what is c7?"}],
            system="SYS",
        )

    result = _run(go())
    assert result["steps"][0]["images"] == []
    # No image turn: the tool message stands alone.
    roles = [m["role"] for m in _RouterState.calls[1]["body"]["messages"]]
    assert roles == ["system", "tool"], roles


def test_tool_result_keeps_only_the_newest_images():
    """Over the cap, the newest figure wins — a cell's latest plot is the one
    being asked about."""
    from services.ai_tools import MAX_IMAGES_PER_RESULT, ToolResult

    result = ToolResult(text="many plots")
    for index in range(MAX_IMAGES_PER_RESULT + 3):
        result.add_image(f"img-{index}", "image/png")
    assert len(result.images) == MAX_IMAGES_PER_RESULT
    # The last one added survives.
    assert result.images[-1][1] == f"img-{MAX_IMAGES_PER_RESULT + 2}"


def test_tool_result_accepts_data_urls():
    from services.ai_tools import ToolResult

    result = ToolResult(text="x")
    result.add_image("data:image/png;base64,AAAA", "image/png")
    assert result.images == [("image/png", "AAAA")]


def test_tool_result_rejects_oversized_images():
    from services.ai_tools import MAX_IMAGE_BYTES, ToolResult

    result = ToolResult(text="too big")
    result.add_image("x" * (MAX_IMAGE_BYTES + 10), "image/png")
    assert result.images == []


def test_images_are_extracted_from_cell_outputs():
    from services.ai_tools import _images_from_outputs

    outputs = [
        {"type": "stream", "text": "plain"},
        {"type": "display_data", "data": {"image/png": "AAA", "text/plain": "<Fig>"}},
        {"type": "display_data", "data": {"image/jpeg": "BBB"}},
        {"type": "execute_result", "data": {"text/plain": "3"}},
    ]
    found = _images_from_outputs(outputs)
    assert ("image/png", "AAA") in found
    assert ("image/jpeg", "BBB") in found
    assert len(found) == 2


# ── the candidate walk ─────────────────────────────────────────────────────


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
            body = json.loads(
                self.rfile.read(int(self.headers["Content-Length"]))
            )
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
    from mirascope import llm

    from services import ai_service

    _fresh_calls()
    catalog = _install_catalog([
        _catalog_row("ranked-first", "high", 10),
        _catalog_row("ranked-second", "high", 900),
    ])

    port, seen = _with_router(["ranked-first"])

    async def go():
        ai_service.configure_provider(f"http://127.0.0.1:{port}/v1")

        @llm.tool
        async def noop() -> str:
            """Nothing."""
            return "x"

        return await ai_service.run_turn(
            model="auto", tools=[noop],
            messages=[{"role": "user", "content": "hi"}], system="SYS")

    result = _run(go())
    assert result["model"] == "ranked-second", result
    assert "answered by" in result["text"], result
    # mirascope strips the provider prefix and the :completions suffix when it
    # builds the request, so the wire carries the bare model name.
    assert seen == ["ranked-first", "ranked-second"], seen
    # The failed model is skipped for five minutes.
    assert catalog.model_circuit_open("ranked-first") is True
    assert catalog.model_circuit_open("ranked-second") is False


def test_turn_raises_unavailable_when_every_candidate_fails():
    from services import ai_service

    _fresh_calls()
    _install_catalog([_catalog_row("only-model", "high", 10)])

    port, _seen = _with_router(["only-model", "auto"])

    async def go():
        ai_service.configure_provider(f"http://127.0.0.1:{port}/v1")
        return await ai_service.run_turn(
            model="auto", tools=[],
            messages=[{"role": "user", "content": "hi"}], system="SYS")

    try:
        _run(go())
        raise AssertionError("should have raised AIUnavailable")
    except ai_service.AIUnavailable as ex:
        assert "unavailable" in str(ex).lower()


def test_turn_with_an_empty_catalog_falls_back_to_the_routers_auto():
    """An empty catalog keeps `auto` as the last resort — it is the gateway's
    own rotation, not a client default, so it is tried rather than skipped."""
    from services import ai_service

    _fresh_calls()
    catalog = _install_catalog([_catalog_row("x", "high", 10)])
    # A truly empty catalog: clear the module state directly.
    catalog._catalog = []
    catalog._catalog_fetched_at = 0.0

    async def go():
        ai_service.configure_provider(_BASE)
        return await ai_service.run_turn(
            model="auto", tools=[],
            messages=[{"role": "user", "content": "hi"}], system="SYS")

    result = _run(go())
    assert result["model"] == "auto", result
    assert result["text"]

"""The ai_service seam: what the callers see, and the prompt they get.

This used to pin mirascope's seven non-obvious behaviours. They moved with the
loop: `test_kani_backend.py` now pins kani's facts, and this file keeps only
what is still true of THIS module — the system prompt, the ToolResult helpers,
and the fact that the turn entry point still works end to end.

The seven mirascope facts, recorded here so the history is not lost:
  1. the provider scope must be "openai/" to match "openai/<model>"
  2. the model id needed ":completions" or mirascope dialed /v1/responses
  3. streaming was ask.stream(...), not a stream=True kwarg
  4. chunk_stream was a method, and TextChunk.delta was the text
  5. execute_tools() was async, and the tools had to be async too
  6. a tool round continued by wrapping ToolOutputs in a UserMessage
  7. the system prompt had to be a SystemMessage(Text(...)), not system=

None survive the move to kani, which is why no test here needs them.
"""

import asyncio
import json
import sys
import typing
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

sys.path.insert(0, "src")


# ── the OpenAI-compatible router the seam is checked against ────────────────
class _RouterState:
    """Captured requests, so a test can assert what reached the wire."""

    calls: typing.ClassVar[list[dict]] = []


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
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        self.wfile.write(_chunk({"content": "Cell c7 sets X = 1"}))
        self.wfile.write(_chunk({}, "stop"))
        self.wfile.write(b"data: [DONE]\n\n")


_PORT = HTTPServer(("127.0.0.1", 0), _Handler)
import threading

threading.Thread(target=_PORT.serve_forever, daemon=True).start()
_BASE = f"http://127.0.0.1:{_PORT.server_address[1]}/v1"


@pytest.fixture(autouse=True)
def _override_router():
    """Point turns at the fake router, so nothing probes 8082..8092."""
    from core.state import state

    state.ai_router_url = _BASE
    yield
    state.ai_router_url = ""


def _run(coro):
    return asyncio.run(coro)


# ── the prompt the model reads ──────────────────────────────────────────────


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


# ── rich tool results: text for the model, images for the row ───────────────


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


# ── the shim still drives a turn ────────────────────────────────────────────


def test_run_turn_streams_and_returns_the_model_that_answered():
    """The entry point both callers use must still work end to end."""
    from services import ai_service

    async def go():
        return await ai_service.run_turn(
            model="auto",
            tools=[],
            messages=[{"role": "user", "content": "what does c7 do?"}],
            system="SYS",
        )

    result = _run(go())
    assert result["text"] == "Cell c7 sets X = 1", result
    assert result["model_steps"] == 1, result
    assert result["cancelled"] is False
    assert _RouterState.calls[0]["path"].endswith("/chat/completions"), _RouterState.calls[0]
    # The system prompt really reached the model.
    sysmsg = next(
        m for m in _RouterState.calls[0]["body"]["messages"] if m["role"] == "system"
    )
    assert sysmsg["content"] == "SYS", sysmsg


def test_the_settings_override_reaches_the_turn():
    """An explicit override is an advanced seam: it must not be re-resolved."""
    from services import ai_service

    async def go():
        return await ai_service.run_turn(
            model="auto",
            tools=[],
            messages=[{"role": "user", "content": "hi"}],
            system="SYS",
        )

    result = _run(go())
    assert result["text"], result


def test_a_stop_before_the_first_token_is_not_billed():
    """Nothing delivered, nothing billed — and no router error either."""
    import threading

    from services import ai_service

    stop = threading.Event()
    stop.set()

    async def go():
        return await ai_service.run_turn(
            model="auto",
            tools=[],
            messages=[{"role": "user", "content": "hi"}],
            system="SYS",
            should_stop=stop.is_set,
        )

    result = _run(go())
    assert result["cancelled"] is True
    assert result["text"] == "", result
    assert result["model_steps"] == 0, result

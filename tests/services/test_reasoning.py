"""The reasoning tap — what the user sees the model thinking.

Ported from DDGS `src/services/reasoning.py` (the same file lm-router ships), so
these pin the parts that would go dark silently rather than loudly: kani reads
`delta.content` only and throws every reasoning field away, which means a broken
tap does not raise — it just shows an empty Thinking block.
"""

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from services.reasoning import (
    ReasoningEngine,
    ThoughtTap,
    _reasoning_from_frame,
    build_thought_client,
)

# ── the frame shapes providers actually send ────────────────────────────────


def test_reasoning_is_read_from_every_field_seen_in_the_wild():
    for key in ("reasoning_content", "reasoning", "reasoning_details"):
        payload = {"choices": [{"delta": {key: "thinking"}}]}
        assert _reasoning_from_frame(payload) == "thinking", key


def test_reasoning_details_as_a_list_of_parts():
    """`reasoning_details` is sometimes structured parts, not a string."""
    payload = {
        "choices": [{"delta": {"reasoning_details": [{"text": "a"}, {"text": "b"}]}}]
    }
    assert _reasoning_from_frame(payload) == "ab"


def test_the_responses_api_typed_event_is_read():
    payload = {
        "type": "response.reasoning_summary_text.delta",
        "delta": {"text": "summary"},
    }
    assert _reasoning_from_frame(payload) == "summary"


def test_plain_content_is_not_mistaken_for_reasoning():
    """The answer must never leak into the thinking block."""
    assert _reasoning_from_frame({"choices": [{"delta": {"content": "answer"}}]}) == ""


def test_a_non_stream_message_on_the_stream_is_read():
    payload = {"choices": [{"message": {"reasoning_content": "late"}}]}
    assert _reasoning_from_frame(payload) == "late"


def test_a_callback_that_raises_does_not_kill_the_turn():
    """A UI hiccup must not take the turn with it — but it must be logged."""
    calls = []

    def boom(_text):
        calls.append(True)
        raise RuntimeError("widget released")

    tap = ThoughtTap(boom)
    tap.feed("thinking")  # must not raise
    assert calls == [True]


# ── over a real SSE stream, with kani's bytes untouched ─────────────────────


def _chunk(delta) -> bytes:
    return (
        "data: "
        + json.dumps(
            {
                "id": "1",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "served-model",
                "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
            }
        )
        + "\n\n"
    ).encode()


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        self.wfile.write(_chunk({"reasoning_content": "Let me think. "}))
        self.wfile.write(_chunk({"reasoning_details": [{"text": "Two."}]}))
        self.wfile.write(_chunk({"content": "2"}))
        self.wfile.write(b"data: [DONE]\n\n")


@pytest.fixture
def router():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    server.server_close()


def test_reasoning_reaches_the_callback_while_kani_still_gets_the_answer(router):
    """The whole point: the tap tees bytes, it does not consume them.

    kani reads `delta.content` and discards the reasoning fields, so if the tap
    altered the stream the answer would break instead of the thinking block.
    """
    import asyncio

    import httpx
    import openai
    from kani import ChatMessage

    seen: list[str] = []
    tap = ThoughtTap(seen.append)

    async def go():
        timeout = httpx.Timeout(20.0, connect=4.0)
        client = openai.AsyncOpenAI(
            api_key="any",
            base_url=router,
            max_retries=0,
            timeout=timeout,
            http_client=build_thought_client(timeout=timeout, max_retries=0, tap=tap),
        )
        engine = ReasoningEngine(
            client=client,
            model="m",
            api_type="chat_completions",
            max_context_size=4096,
        )
        out = []
        async for piece in engine.stream(messages=[ChatMessage.user("hi")]):
            out.append(str(piece))
        return "".join(out)

    answer = asyncio.run(go())
    assert "".join(seen) == "Let me think. Two.", seen
    assert answer.startswith("2"), answer
    # And the tap recorded the id the router actually served.
    assert tap.last_model == "served-model", tap.last_model


def test_an_error_frame_is_recorded_not_swallowed():
    """A dead upstream arrives as HTTP 200 with an error object in a frame.

    The openai SDK turns that frame into `APIError`, which our walk maps to
    "try the next model" — correct, but it says nothing about why. The tap keeps
    the upstream's own words so the walk can log them instead of "said nothing".
    """
    calls: list[str] = []
    tap = ThoughtTap(calls.append)

    class _ErrHandler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(
                (
                    "data: "
                    + json.dumps({"error": {"message": "upstream died"}})
                    + "\n\n"
                ).encode()
            )
            self.wfile.write(b"data: [DONE]\n\n")

    import asyncio

    import httpx
    import openai
    from kani import ChatMessage

    server = HTTPServer(("127.0.0.1", 0), _ErrHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/v1"

    async def go():
        timeout = httpx.Timeout(20.0, connect=4.0)
        client = openai.AsyncOpenAI(
            api_key="any",
            base_url=base,
            max_retries=0,
            timeout=timeout,
            http_client=build_thought_client(timeout=timeout, max_retries=0, tap=tap),
        )
        engine = ReasoningEngine(
            client=client,
            model="m",
            api_type="chat_completions",
            max_context_size=4096,
        )
        async for _ in engine.stream(messages=[ChatMessage.user("hi")]):
            pass

    try:
        # The SDK raises `openai.APIError` for that frame; the walk maps it to
        # "try the next model". What matters here is only that the tap kept the
        # cause on its way past.
        with pytest.raises(openai.APIError):
            asyncio.run(go())
    finally:
        server.server_close()

    # Whatever the SDK did with it, the tap kept the cause.
    assert tap.last_error == {"message": "upstream died"}, tap.last_error

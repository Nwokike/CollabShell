"""A real Kiri Router, small enough to trust in a test.

Neither reference calls a live gateway from its tests. DDGS writes a
contract-complete engine source to a tmp path and points `engine_cache_path` at
it (`tests/test_engine_service.py:22-36`); lm-router goes further and binds a
real HTTP server speaking the contract (`tests/fixture_engine.py`). This is that
second pattern, sized to what CollabShell's router actually consumes.

It exists to exercise the one path nothing else covers: `load_engine()` ->
`acquire_server()` binding a real port. Every other router test probes with a
monkeypatched `httpx`, and `test_router_engine.py` covers download / validate /
load in isolation. **Nothing has ever bound a port**, which is the behaviour the
owner requires: the app runs its own server, and when the port is taken it uses
the next one.

The model is scripted, not intelligent. It answers with text, or asks for a tool
call, based only on what is in the request — the same mechanism `test_kani_backend`'s
fake routers use, so it is a known-good shape. That makes the turn assertions
deterministic: the *plumbing* (embed, ports, SSE protocol, meter, gate) is what
this proves, not a model's judgement.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = "9.9.9"
START_TIME = time.time()

_CATALOG = [
    {
        "id": "auto",
        "object": "model",
        "created": int(START_TIME),
        "owned_by": "kiri",
        "endpoint_type": "chat.completion",
        "is_free": True,
        "status": "active",
        "latency_ms": None,
        "rate_hint": {
            "tier": "variable",
            "approx_per_hour": None,
            "label": "Free tier, rotates across available models",
        },
    },
    {
        "id": "fixture-model",
        "object": "model",
        "created": int(START_TIME),
        "owned_by": "kiri",
        "endpoint_type": "chat.completion",
        "is_free": True,
        "status": "active",
        "latency_ms": 10,
        "rate_hint": {"tier": "high", "approx_per_hour": 40, "label": "high tier"},
    },
]

# Everything the scripted model has produced, newest last. Tests read it to
# assert on what actually reached the wire.
REQUESTS: list[dict] = []


def reset() -> None:
    """Forget every request seen, so a test starts from a clean transcript."""
    REQUESTS.clear()


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

    def do_GET(self):
        if self.path.startswith("/health"):
            body = {
                "status": "ok",
                "adapter": "kiri-router",
                "version": VERSION,
                "uptime_sec": time.time() - START_TIME,
                "upstream": "kiri",
                "mode": "local",
            }
        elif self.path.startswith("/v1/models"):
            body = {"object": "list", "data": _CATALOG}
        elif self.path.startswith("/account-limits"):
            body = {"models": {row["id"]: row["rate_hint"] for row in _CATALOG}}
        else:
            self.send_response(404)
            self.end_headers()
            return
        payload = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        if not self.path.startswith("/v1/chat/completions"):
            self.send_response(404)
            self.end_headers()
            return
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        REQUESTS.append(body)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        has_tool = any(m.get("role") == "tool" for m in body.get("messages") or [])
        if has_tool:
            # The tool already ran; answer from its result.
            self.wfile.write(_chunk({"content": "Fixture answer after the tool."}))
            self.wfile.write(_chunk({}, "stop"))
        else:
            tools = body.get("tools") or []
            self.wfile.write(_chunk({"content": "Checking. "}))
            if tools:
                name = tools[0]["function"]["name"]
                self.wfile.write(
                    _chunk(
                        {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": name, "arguments": "{}"},
                                }
                            ]
                        }
                    )
                )
                self.wfile.write(_chunk({}, "tool_calls"))
            else:
                self.wfile.write(_chunk({}, "stop"))
        self.wfile.write(b"data: [DONE]\n\n")


class _Server(ThreadingHTTPServer):
    """No address reuse — a taken port must genuinely fail to bind.

    `HTTPServer` sets `allow_reuse_address = 1`, and on Windows a second socket
    with SO_REUSEADDR can then bind a port another listener ALREADY HOLDS. With
    it on, the "port in use, use the next one" path never runs and the fixture
    silently passes while occupying a port that is not ours — which is the exact
    production failure this test exists to catch. socketserver's default is off.
    """

    daemon_threads = True
    allow_reuse_address = False


def start(port: int = 0) -> tuple[_Server, int]:
    """Bind a fixture router on `port` (0 = any free) and serve it."""
    server = _Server(("127.0.0.1", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def acquire_server(want: int, span: int = 10):
    """Bind `want`, or report the existing owner when it is taken.

    The contract `services/router.py` depends on: `(server, port)` on success,
    `(None, port)` when the bind failed, which is the race branch that attaches
    instead of embedding. Falling forward through the span is what makes "the
    port is in use, so use the next one" real rather than aspirational.
    """
    port = want
    for _ in range(span + 1):
        try:
            server = _Server(("127.0.0.1", port), _Handler)
        except OSError:
            port += 1
            continue
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server, server.server_address[1]
    return None, port


if __name__ == "__main__":  # pragma: no cover - mirrors the real engine guard
    srv, bound = acquire_server(8082)
    print(f"fixture router on {bound}")
    if srv is not None:
        srv.serve_forever()

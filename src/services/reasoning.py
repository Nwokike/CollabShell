"""Reasoning capture for kani turns: the stream teed, bytes untouched.

Ported verbatim from DDGS `src/services/reasoning.py`, which is the same file in
lm-router — one implementation both apps ship. kani flattens the upstream stream
to answer text: its chat-completions path reads `delta.content` and throws
`reasoning_content` / `reasoning` / `reasoning_details` deltas away, so without
this the Thinking block would go dark. kani discards them silently; it does not
error.

The capture happens on the SSE bytes themselves: an httpx transport tees
`text/event-stream` responses, pulls the reasoning fields out of each `data:`
frame, and passes the original bytes through untouched — kani still sees exactly
the stream the router sent.

The tap is shared by reference with the engine, so a new turn retargets its
callback without rebuilding the HTTP client. It also records the served-model id
the router stamps on frames (it rewrites `auto` to the real model) and any error
frame, because a dead upstream arrives as HTTP 200 with an error object inside
an SSE frame and no content at all.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

import httpx
from kani.engines.openai import OpenAIEngine

from core.constants import APP_VERSION

logger = logging.getLogger("reasoning")

ThoughtCB = Callable[[str], None]

# Same UA rule as the engine fetch: router.kiri.ng answers 403 to default
# library user-agents.
USER_AGENT = f"CollabShell/{APP_VERSION}"

# Fields seen in the wild, across providers.
_REASONING_KEYS = ("reasoning_content", "reasoning", "reasoning_details")


def _flatten(value: Any) -> str:
    """reasoning_details is sometimes a list of structured parts."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for item in value:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                if item.get("text"):
                    out.append(str(item["text"]))
            else:
                text = getattr(item, "text", None)
                if text:
                    out.append(str(text))
        return "".join(out)
    if isinstance(value, dict):
        return str(value.get("text") or "")
    return str(value)


def _reasoning_from_frame(payload: dict) -> str:
    """Extract reasoning text from one decoded SSE frame."""
    # Responses-API typed events, e.g. "response.reasoning_summary_text.delta".
    kind = str(payload.get("type") or "")
    if "reasoning" in kind and not payload.get("choices"):
        delta = payload.get("delta") or {}
        text = delta.get("text") if isinstance(delta, dict) else None
        return _flatten(text if text is not None else payload.get("text"))

    for choice in payload.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        delta = choice.get("delta") or {}
        if not isinstance(delta, dict):
            continue
        for key in _REASONING_KEYS:
            value = delta.get(key)
            if value:
                return _flatten(value)
        # Non-stream style payload occasionally rides the stream.
        message = choice.get("message") or {}
        if isinstance(message, dict):
            for key in _REASONING_KEYS:
                value = message.get(key)
                if value:
                    return _flatten(value)
    return ""


class ThoughtTap:
    """Mutable holder so a new turn can retarget the callback in place."""

    def __init__(self, callback: ThoughtCB | None = None) -> None:
        self.callback = callback
        # The router rewrites `auto` to the served model on every frame; the
        # receipt row shows this id.
        self.last_model = ""
        # A dead upstream arrives as HTTP 200 with an error object inside an SSE
        # frame and no content at all - the tap records it so the candidate walk
        # logs the real cause instead of "said nothing".
        self.last_error: dict | None = None

    def feed(self, text: str) -> None:
        if not text or self.callback is None:
            return
        try:
            self.callback(text)
        except Exception as exc:
            # A UI hiccup must never kill the turn, but never swallow it
            # silently either: that is how a Thinking block "disappears".
            logger.warning("reasoning callback failed: %s", exc)


class _TeeStream(httpx.AsyncByteStream):
    """Pass-through byte stream that scans SSE frames for reasoning."""

    def __init__(self, inner: httpx.AsyncByteStream, tap: ThoughtTap) -> None:
        self._inner = inner
        self._tap = tap
        self._buffer = b""

    async def __aiter__(self):
        async for chunk in self._inner:
            self._buffer += chunk
            # SSE frames are separated by a blank line.
            while b"\n\n" in self._buffer:
                frame, self._buffer = self._buffer.split(b"\n\n", 1)
                self._scan(frame)
            yield chunk  # unchanged: kani must see the original bytes
        self._scan(self._buffer)
        self._buffer = b""

    def _scan(self, frame: bytes) -> None:
        for line in frame.split(b"\n"):
            if not line.startswith(b"data:"):
                continue
            raw = line[5:].strip()
            if not raw or raw == b"[DONE]":
                continue
            try:
                payload = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(payload, dict):
                continue
            model = payload.get("model")
            if isinstance(model, str) and model:
                self._tap.last_model = model
            error = payload.get("error")
            if isinstance(error, dict):
                self._tap.last_error = error
            self._tap.feed(_reasoning_from_frame(payload))

    async def aclose(self) -> None:
        await self._inner.aclose()


class ThoughtTapTransport(httpx.AsyncHTTPTransport):
    """httpx transport that tees SSE reasoning without altering the stream."""

    def __init__(self, tap: ThoughtTap, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._tap = tap

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await super().handle_async_request(request)
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type.lower():
            response.stream = _TeeStream(response.stream, self._tap)
        return response


class ReasoningEngine(OpenAIEngine):
    """OpenAIEngine wired to a reasoning tap.

    A subclass so the engine still IS a kani engine (kani's isinstance checks
    keep working) and so `on_thought` can be retargeted per turn without
    rebuilding the HTTP client.
    """

    def __init__(
        self, *args: Any, tap: ThoughtTap | None = None, **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self.tap = tap if tap is not None else ThoughtTap()

    @property
    def on_thought(self) -> ThoughtCB | None:
        return self.tap.callback

    @on_thought.setter
    def on_thought(self, value: ThoughtCB | None) -> None:
        self.tap.callback = value


def build_thought_client(
    *,
    timeout: httpx.Timeout,
    max_retries: int,
    tap: ThoughtTap,
) -> httpx.AsyncClient:
    """An httpx client whose streams are scanned for reasoning.

    The base_url lives on the openai.AsyncOpenAI client that wraps this one; the
    transport only tees bytes.

    `max_retries` is a parameter but deliberately not forwarded: httpx has no
    such client option, and the retry that matters rides on
    `openai.AsyncOpenAI(max_retries=...)`.
    """
    return httpx.AsyncClient(
        transport=ThoughtTapTransport(tap),
        timeout=timeout,
        headers={"User-Agent": USER_AGENT},
    )


__all__ = [
    "ReasoningEngine",
    "ThoughtCB",
    "ThoughtTap",
    "ThoughtTapTransport",
    "build_thought_client",
]

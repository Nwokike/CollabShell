"""Kiri Router client — OpenAI-compatible chat, streaming, zero key.

Every request exits from the user's own IP and needs no Authorization
header, so the app ships no AI credential to leak. `/v1/models` lists each
model with its `rate_hint`, and the picker shows that hint next to the
model so users see "roughly 200 requests/hour" before picking, not after
hitting a 429.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass

import httpx

logger = logging.getLogger("ai.router")

ROUTER_BASE_URL = "https://router.kiri.ng"
DEFAULT_MODEL = "auto"

# Endpoint shapes verified to produce a usable chat reply. Kiri advertises
# other shapes alongside them, but `response`/`responses` models answer
# "Model ... is not supported" and `systemone` does not return an
# OpenAI-shaped body at all — offering those is offering a dead end.
# Verified 2026-09-24 against the live catalog and against the LM Router
# app, which reaches the same conclusion independently.
CHAT_CAPABLE_ENDPOINTS = frozenset({"chat.completion", "chat.completions", "chat"})


def is_chat_eligible(model: dict) -> bool:
    """Active, chat-capable, and something we can actually render."""
    if not model or not model.get("id"):
        return False
    if model.get("status") not in (None, "active"):
        return False
    if model.get("id") == DEFAULT_MODEL:
        return True  # the router composes a chat-shaped answer
    endpoint = str(model.get("endpoint_type") or "").strip().lower()
    # A row with no endpoint_type at all predates the field; trust it.
    return not endpoint or endpoint in CHAT_CAPABLE_ENDPOINTS


# Reasoning can take a while; the read timeout has to outlast it or long
# thinking models look dead. The connect timeout stays short.
_TIMEOUT = httpx.Timeout(connect=15.0, read=240.0, write=60.0, pool=30.0)


class RouterBusy(Exception):
    """The free tier is rate-limited right now (HTTP 429)."""


class RouterUnavailable(Exception):
    """The router could not be reached, or answered with an error."""


def _details_text(details) -> str:
    """Flatten a structured `reasoning_details` stream into plain text.

    Some upstreams stream reasoning as typed segments
    (`[{"type": "text", "text": ...}, ...]`) rather than a string.
    """
    if isinstance(details, str):
        return details
    if isinstance(details, list):
        parts = [
            item.get("text") or ""
            for item in details
            if isinstance(item, dict) and item.get("text")
        ]
        return "".join(parts)
    return ""


@dataclass(frozen=True)
class AiModel:
    """One model the router currently serves."""

    id: str
    rate_hint: str = ""
    latency_ms: int | None = None
    # The router's own per-model cap, when it publishes one. Preferred over
    # parsing the label: it is a number, and numbers do not drift.
    cap_per_hour: int | None = None

    @property
    def is_auto(self) -> bool:
        return self.id == DEFAULT_MODEL

    @property
    def looks_capped(self) -> bool:
        """A published cap under 200/hour — worth not suggesting."""
        return self.cap_per_hour is not None and self.cap_per_hour < 200


class KiriRouter:
    def __init__(self, base_url: str = ROUTER_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None
        # The last catalog we saw, so a 429 can be explained in terms of
        # the model the user actually picked.
        self._catalog: list[AiModel] = []

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def list_models(self) -> list[AiModel]:
        """Active, chat-capable models only.

        Two filters, and the second one matters more than it looks. Every
        row Kiri serves is `status: active`, so a status check alone still
        offers models whose endpoint cannot answer a chat request — as of
        2026-09-24 three of the 48 served models are `systemone` or
        `response`, and picking one returns an empty reply or a 401
        (verified in the LM Router app's own catalog, which documents the
        same conclusion). The picker must never offer a dead model, so both
        are filtered here.
        """
        try:
            resp = await self._get_client().get(f"{self.base_url}/v1/models")
            resp.raise_for_status()
        except Exception as e:
            logger.warning("Model discovery failed: %s", e)
            raise RouterUnavailable("Could not reach Kiri Router.") from e

        models: list[AiModel] = []
        for raw in resp.json().get("data") or []:
            if raw.get("status") not in (None, "active"):
                continue
            if not is_chat_eligible(raw):
                logger.debug("Skipping non-chat endpoint: %s", raw.get("id"))
                continue
            hint = (raw.get("rate_hint") or {}).get("label", "")
            cap = (raw.get("rate_hint") or {}).get("approx_per_hour")
            try:
                cap = int(cap) if cap is not None else None
            except (TypeError, ValueError):
                cap = None
            models.append(
                AiModel(
                    id=raw.get("id", ""),
                    rate_hint=hint,
                    latency_ms=raw.get("latency_ms"),
                    cap_per_hour=cap,
                )
            )
        # auto first, then alphabetical — auto is the default, not a peer.
        models.sort(key=lambda m: (not m.is_auto, m.id.lower()))
        self._catalog = models
        return models

    def advice_for_rate_limit(self, model_id: str) -> str:
        """What to say when a model is capped, using what we know about it.

        "Rate limited. Try again." reads like something is broken. The
        router publishes a per-model cap and a pool of alternatives, so
        the message can name the cap and point at a model that is not
        capped — the difference between a dead end and a next step.
        """
        if not self._catalog:
            return "Kiri's free tier is busy right now — try again shortly."
        row = next((m for m in self._catalog if m.id == model_id), None)
        if model_id == DEFAULT_MODEL:
            hint = row.rate_hint if row else ""
            return (
                f"Rate limited right now. {hint} Try again shortly, or pick a "
                "specific model."
                if hint
                else "Rate limited right now. Try again shortly, or pick a specific model."
            )
        alternatives = [m for m in self._catalog if m.id != model_id]
        # Prefer a model whose own published cap says it can take the load.
        alternatives.sort(
            key=lambda m: (m.looks_capped, m.cap_per_hour or 10**9, m.id.lower())
        )
        suggestion = f" Try {alternatives[0].id} instead." if alternatives else ""
        hint = row.rate_hint if row else ""
        if hint:
            return (
                f"Rate limited. {hint}.{suggestion}"
                if suggestion
                else f"Rate limited. {hint}."
            )
        return (
            f"Rate limited by this model.{suggestion}"
            if suggestion
            else ("Rate limited by this model. Try again in a moment.")
        )

    async def stream_chat(
        self,
        messages: list[dict],
        model: str = DEFAULT_MODEL,
        on_delta: Callable[[str], None] | None = None,
        on_reasoning: Callable[[str], None] | None = None,
        tools: list[dict] | None = None,
    ) -> tuple[str, list[dict]]:
        """Stream one reply. Returns (model that answered, tool calls).

        Tool calls arrive as OpenAI `delta.tool_calls` fragments
        (index/name/arguments streamed across chunks) and are reassembled
        here. Raises RouterBusy on 429 so the caller can refund and say so.
        """
        payload: dict = {"model": model, "messages": messages, "stream": True}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        answered_by = model
        raw_calls: dict[int, dict] = {}
        try:
            async with self._get_client().stream(
                "POST", f"{self.base_url}/v1/chat/completions", json=payload
            ) as resp:
                if resp.status_code == 429:
                    raise RouterBusy("Kiri is busy right now.")
                if resp.status_code >= 400:
                    raise RouterUnavailable(
                        f"Kiri Router returned HTTP {resp.status_code}."
                    )
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("model"):
                        answered_by = chunk["model"]
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        for frag in delta.get("tool_calls") or []:
                            index = frag.get("index", 0)
                            slot = raw_calls.setdefault(
                                index,
                                {
                                    "id": "",
                                    "type": "function",
                                    "name": "",
                                    "arguments": "",
                                },
                            )
                            if frag.get("id"):
                                slot["id"] = frag["id"]
                            fn = frag.get("function") or {}
                            if fn.get("name"):
                                slot["name"] = fn["name"]
                            if fn.get("arguments"):
                                slot["arguments"] += fn["arguments"]
                        text = delta.get("content") or ""
                        # Kiri Router streams reasoning through untouched,
                        # but the dialect differs per upstream: most send
                        # `reasoning`, one family sends `reasoning_content`,
                        # structured ones send `reasoning_details` segments.
                        # Read all three, prefer whichever arrived.
                        reasoning = (
                            delta.get("reasoning")
                            or delta.get("reasoning_content")
                            or _details_text(delta.get("reasoning_details"))
                        )
                        if not reasoning and text.startswith("[Reasoning:"):
                            # Safety net for the rare aggregated reply that
                            # still folds thinking into a text prefix.
                            head, _, rest = text.partition("]")
                            reasoning = head.removeprefix("[Reasoning:").strip()
                            text = rest
                        if reasoning and on_reasoning:
                            on_reasoning(reasoning)
                        if text and on_delta:
                            on_delta(text)
        except (RouterBusy, RouterUnavailable):
            raise
        except httpx.HTTPError as e:
            raise RouterUnavailable("Lost the connection to Kiri Router.") from e
        return answered_by, list(raw_calls.values())

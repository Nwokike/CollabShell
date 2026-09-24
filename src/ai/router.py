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

# Reasoning can take a while; the read timeout has to outlast it or long
# thinking models look dead. The connect timeout stays short.
_TIMEOUT = httpx.Timeout(connect=15.0, read=240.0, write=60.0, pool=30.0)


class RouterBusy(Exception):
    """The free tier is rate-limited right now (HTTP 429)."""


class RouterUnavailable(Exception):
    """The router could not be reached, or answered with an error."""


@dataclass(frozen=True)
class AiModel:
    """One model the router currently serves."""

    id: str
    rate_hint: str = ""
    latency_ms: int | None = None

    @property
    def is_auto(self) -> bool:
        return self.id == DEFAULT_MODEL


class KiriRouter:
    def __init__(self, base_url: str = ROUTER_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def list_models(self) -> list[AiModel]:
        """Active models only — the picker must never offer a dead one."""
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
            hint = (raw.get("rate_hint") or {}).get("label", "")
            models.append(
                AiModel(
                    id=raw.get("id", ""),
                    rate_hint=hint,
                    latency_ms=raw.get("latency_ms"),
                )
            )
        # auto first, then alphabetical — auto is the default, not a peer.
        models.sort(key=lambda m: (not m.is_auto, m.id.lower()))
        return models

    async def stream_chat(
        self,
        messages: list[dict],
        model: str = DEFAULT_MODEL,
        on_delta: Callable[[str], None] | None = None,
        on_reasoning: Callable[[str], None] | None = None,
    ) -> str:
        """Stream one reply. Returns the name of the model that answered —
        the real one when the router reports it, else whatever was asked.
        Raises RouterBusy on 429 so the caller can refund and say so."""
        payload = {"model": model, "messages": messages, "stream": True}
        answered_by = model
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
                        text = delta.get("content") or ""
                        reasoning = delta.get("reasoning") or ""
                        if not reasoning and text.startswith("[Reasoning:"):
                            # Aggregated (non-streaming) replies fold the
                            # thinking into a text prefix; split it back out
                            # so the UI can keep it collapsible.
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
        return answered_by

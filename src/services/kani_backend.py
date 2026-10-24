"""The kani backend: the agent loop is kani's, wrapped not rebuilt.

Ported from DDGS `src/services/kani_backend.py`. Owner decision (recorded in
project memory): kani[openai] speaks the OpenAI wire our embedded router uses;
the gateway fallback is DROPPED — the router is the single AI source. The outer
contracts CollabShell already has are kept exactly: the emit protocol, credits
per model step, the approval gate, step rows, the candidate walk.

The five non-obvious things kani's shape forces, all verified against the
installed kani 1.10.0 (`kani/kani.py:_full_round`, `kani/streaming.py`):

1. **A billable step is one model stream.** `full_round_stream` yields a
   `StreamManager` per model round and a `DummyStream` (role FUNCTION) per tool
   result. Only the ASSISTANT rounds reserve and charge — counting the FUNCTION
   yields would double-bill every tool round.
2. **kani runs a tool batch with `asyncio.gather`**, while this app's tools are
   sequential — one download, one ordered step row. A per-batch `asyncio.Lock`
   in `build_functions` keeps that contract; without it step rows interleave.
3. **Step rows come from inside the tool.** kani runs the batch in its own
   `asyncio.gather`, so no outside hook knows a call started; `tool_specs`
   wraps each body to emit its row. `Kani` is used unmodified.
4. **`tokenizer` must be passed.** kani's `OpenAIEngine.tokenizer` is a lazy
   property that loads tiktoken on the first `message_len`; that BPE download
   has no timeout and stalls a turn. A counting tokenizer is injected instead.
5. **Tool bodies must be wrapped, not replaced.** Step rows are emitted from
   inside the tool (`tool_specs` below), because kani runs the batch in its own
   gather and there is no outside hook that knows a call started.

`_map_failure` splits model-level misses from endpoint misses: a 429 or a hung
upstream walks to the next candidate, because switching models can help; only a
connection failure marks the router down, because every candidate shares the
endpoint. One dead model must never black out the whole router for 60s.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx
import openai
from kani import AIFunction, ChatMessage, Kani
from kani.engines.base import BaseCompletion
from kani.engines.openai import OpenAIEngine
from kani.models import ChatRole

logger = logging.getLogger("kani_backend")

# The router serves chat completions to models whose context windows we do not
# know (`auto`, the free catalog). This budget is far above what a transcript
# reaches, so kani never evicts history.
DEFAULT_CONTEXT = 131072

# Per-candidate patience. The walk only works if every candidate has to prove it
# is alive fast: 12s to the first token, 20s of dead air mid-stream. The outer
# turn wall-clock stays the boss; a healthy model answers its first token in
# 1-2s, so these caps only ever trip on hung upstreams.
CANDIDATE_TTFB_S = 12.0
CANDIDATE_READ_S = 20.0


class RouterModelFailed(Exception):
    """One candidate model failed; the turn should try the next one.

    Never a terminal error: the outer handler maps this onto the
    next-candidate path, so a single dead model can never end a turn.
    """


@dataclass(frozen=True)
class ToolSpec:
    """One tool as the app defines it: schema for the model, code for us.

    `run` receives the parsed arguments and returns the exact text the model
    sees. It never raises — every failure becomes an error payload, so one bad
    call cannot kill a turn.
    """

    name: str
    desc: str
    parameters: dict
    run: Callable[..., Awaitable[str]]


class _CountingTokenizer:
    """A tokenizer that never downloads.

    kani loads tiktoken lazily on the first `message_len`, and that BPE fetch
    has no timeout, so it stalls a turn on a cold cache. Word counting is a
    heuristic that *under*counts a real BPE for code (which splits far below
    word boundaries), so it reads a prompt as shorter than it is — the honest
    consequence is that the oversized-prompt error surfaces from the wire
    rather than as a graceful eviction. At this app's context budget that is
    fine: a transcript is a few thousand tokens, nowhere near the ceiling.
    """

    def encode(self, text: str, **_kw) -> list[str]:
        if not text:
            return []
        return text.split()

    def decode(self, tokens, **_kw):
        if isinstance(tokens, str):
            return tokens
        return " ".join(str(t) for t in tokens)

    def encode_batch(self, texts, **_kw):
        return [self.encode(t) for t in texts]


def tool_specs(
    specs: list[ToolSpec], *, on_step: Callable[[str, dict], None] | None = None
) -> list[ToolSpec]:
    """Adapt tool specs so each call emits its step row.

    kani runs the tool batch inside its own `asyncio.gather`, so there is no
    outside hook that knows a call started. The row is therefore emitted from
    here, around `run`.

    ``on_step(event, payload)`` is how the caller's emit protocol learns about
    it; the tool body itself is untouched. The payload is
    ``{"name", "id", "args", "result", "error"}`` — ``id`` is kani's own
    ``tool_call_id`` (see :func:`call_id`), because a step row is only
    closed by the id that opened it.
    """
    out: list[ToolSpec] = []
    for spec in specs:
        run = spec.run

        async def wrapped(spec: ToolSpec = spec, run=run, **kwargs: Any) -> str:
            payload = {
                "name": spec.name,
                "id": call_id(),
                "args": dict(kwargs),
                "result": "",
                "error": None,
            }
            if on_step is not None:
                on_step("start", dict(payload))
            try:
                text = await run(**kwargs)
                payload["result"] = text
                return text
            except Exception as ex:
                # A tool body that raises would reach kani as a
                # WrappedCallException, and kani would put its own error text
                # in the transcript and force another model turn
                # (`handle_function_call_exception`, kani/kani.py:618-651,
                # gated by `attempt < retry_attempts`, so at the 1 we pass it
                # costs no extra round). We catch it here for the step row:
                # our payload's `error` is what turns the row red, and kani's
                # path would close it with none.
                logger.debug("tool %s raised: %r", spec.name, ex)
                text = f"(the {spec.name} tool failed: {ex})"
                payload["result"] = text
                payload["error"] = str(ex)
                return text
            finally:
                if on_step is not None:
                    on_step("done", payload)

        out.append(
            ToolSpec(name=spec.name, desc=spec.desc, parameters=spec.parameters, run=wrapped)
        )
    return out


def build_functions(specs: list[ToolSpec]) -> list[AIFunction]:
    """kani AIFunctions from our specs, executing one at a time.

    kani runs a tool batch with asyncio.gather; our tools are sequential (one
    download, one ordered step row), so a per-batch lock keeps that contract.
    Schemas go through verbatim: json_schema is the same `parameters` document
    the OpenAI tool payload sends.

    The active ``tool_call_id`` is published to a ContextVar for the duration
    of the call (``_call_id``), because it is the only identity kani leaves for
    matching a step row that is opened here to the row that closes when the
    batch finishes.

    `auto_truncate` is kani's own, and it is only PARTLY paragraph-aware: kani
    tries dividers in order `"\n\n"`, `"\n"`, `". "`, `", "`, `" "`
    (`kani/kani.py:706`) and falls back to a hard chop of `max_len - 3` chars
    plus `"..."` (`kani/kani.py:727-731`). So it can still cut tool JSON at a
    comma, and a very long single chunk mid-token. It is still better than our
    old blind slice, which had no dividers at all — but the guarantee is "cuts
    sooner at a natural boundary", not "never cuts a payload".
    """
    from services.ai_tools import TOOL_OUTPUT_CAP

    lock = asyncio.Lock()
    out: list[AIFunction] = []
    for spec in specs:

        async def inner(spec: ToolSpec = spec, **kwargs: Any) -> str:
            async with lock:
                token = _call_id.set(_current_call_id.get())
                try:
                    return await spec.run(**kwargs)
                finally:
                    _call_id.reset(token)

        out.append(
            AIFunction(
                inner,
                name=spec.name,
                desc=spec.desc,
                json_schema=spec.parameters,
                auto_truncate=TOOL_OUTPUT_CAP,
            )
        )
    return out


# The tool_call_id of the call currently executing, and "" outside one. Set by
# DDGSKani.do_function_call, which is the only place kani exposes it.
_call_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "collabshell_call_id", default=""
)
# Set by the same override right before the call runs, so build_functions can
# re-publish it inside the lock. Each of kani's gather children gets its own
# copy of the context, so a value set here is visible to the call it precedes
# and to nothing after it.
_current_call_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "collabshell_current_call_id", default=""
)


def call_id() -> str:
    """The tool_call_id of the call currently executing ("" outside one)."""
    return _call_id.get()


class DDGSKani(Kani):
    """Kani plus call identity for the step rows.

    kani runs the tool batch in its own ``asyncio.gather``, so nothing outside
    a tool knows which call is running. Overriding ``do_function_call`` is the
    one hook that sees ``tool_call_id`` before the body starts; it is published
    so the step row opened inside the tool carries the same id the batch will
    report. `Kani`'s round loop and batch gather are used as shipped — only
    call identity is added here.
    """

    async def do_function_call(self, call, tool_call_id: str | None = None):
        token = _current_call_id.set(tool_call_id or "")
        try:
            return await super().do_function_call(call, tool_call_id=tool_call_id)
        finally:
            # Without the reset a value could outlive its call and a later
            # tool would report a stale id, closing the wrong row.
            _current_call_id.reset(token)


# Kani's round loop and batch gather are its own and neither needs changing for
# anything this app does; only call identity is added, above.
CollabShellKani = DDGSKani


def _chat_messages(items: list[dict], *, limit: int | None = None) -> list[ChatMessage]:
    """OpenAI-dict transcript -> kani messages."""
    out: list[ChatMessage] = []
    window = items if limit is None else (items or [])[-limit:]
    for item in window:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        role = str(item.get("role") or "")
        if role == "user":
            out.append(ChatMessage.user(content))
        elif role == "assistant":
            out.append(ChatMessage.assistant(content))
    return out


async def _build_engine(
    model: str,
    base_url: str | None = None,
    *,
    on_thought: Callable[[str], None] | None = None,
) -> OpenAIEngine:
    """One engine per candidate: router base, bounded timeouts, no SDK retries.

    ``base_url`` is the router the caller already resolved — a Settings
    override, or the app's own attach/embed decision. Passing it keeps the
    router decision in one place instead of re-running the attach path here.

    ``on_thought`` receives the model's reasoning as it streams. kani throws
    those deltas away (it reads `delta.content` only), so the capture has to
    happen on the SSE bytes: the client is built over a transport that tees
    `text/event-stream` frames and passes the originals through untouched
    (`services/reasoning.py`, the same file DDGS and lm-router ship). Without
    it the Thinking block goes dark and the user sees an answer appear from
    nowhere.

    `max_retries=0` on the SDK because the candidate walk IS the retry for HTTP
    misses — the SDK's own backoff delayed every walk by retrying the same dead
    model first. `api_type` is explicit because `auto` and the free catalog
    match no known model prefix.
    """
    from services import router
    from services.ai_service import AIUnavailable
    from services.reasoning import ReasoningEngine, ThoughtTap, build_thought_client

    base = base_url or await router.router_base()
    if base is None:
        raise AIUnavailable("No local model router is running, and none could be started.")
    timeout = httpx.Timeout(CANDIDATE_READ_S, connect=4.0)
    tap = ThoughtTap(on_thought)
    client = openai.AsyncOpenAI(
        api_key="any",
        base_url=base,
        max_retries=0,
        timeout=timeout,
        # The tapping client replaces the SDK's default one; max_retries is not
        # forwarded because httpx has no such option and the SDK owns it.
        http_client=build_thought_client(
            timeout=timeout, max_retries=0, tap=tap
        ),
    )
    return ReasoningEngine(
        client=client,
        model=model,
        api_type="chat_completions",
        max_context_size=DEFAULT_CONTEXT,
        tokenizer=_CountingTokenizer(),
        tap=tap,
    )


def _map_failure(exc: BaseException, *, delivered: bool) -> Exception:
    """openai's exception ladder -> one of ours. Returns, never raises.

    The distinction that matters: a **model-level** miss (429/5xx/refused/
    timeout) becomes `RouterModelFailed`, so the turn walks to the next
    candidate — switching models can help. Only a **connection** miss calls
    `_mark_router_failed`, because every candidate shares that endpoint and
    switching models cannot help. A single dead model must never black out the
    whole router for 60 seconds.
    """
    from services import router as router_service
    from services.ai_service import AIMidStream, AIUnavailable

    if isinstance(exc, (AIUnavailable, AIMidStream, RouterModelFailed)):
        return exc
    if isinstance(exc, openai.APIStatusError):
        if exc.status_code == 429:
            return RouterModelFailed(
                "Kiri's free tier is busy right now. Trying another model."
            )
        if exc.status_code >= 500:
            return RouterModelFailed(
                "The Assistant had a server problem. Trying another model."
            )
        return RouterModelFailed(
            "The Assistant refused that request. Trying another model."
        )
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        # Our own per-candidate cap (`asyncio.wait_for` on the first token), or
        # a transport-level timeout. The router answered the connect; the
        # candidate upstream is hung, so walk on without a blackout.
        return RouterModelFailed("A model timed out. Trying another model.")
    if isinstance(exc, openai.APITimeoutError):
        # The router answered; one of its upstream models hung. The router
        # itself is healthy — walk to the next candidate, no blackout.
        return RouterModelFailed("A model timed out. Trying another model.")
    if isinstance(exc, openai.APIConnectionError):
        # Refused/DNS: every candidate shares this endpoint, so switching
        # models cannot help — the router itself is gone.
        router_service._mark_router_failed()
        if delivered:
            # The user already read part of the answer before the connection
            # dropped, so the turn ends with what it got rather than walking
            # (there is nowhere to walk to) or discarding it.
            return AIMidStream(str(exc))
        return AIUnavailable("Could not reach the Assistant.")
    if isinstance(exc, openai.APIError):
        return RouterModelFailed(
            "The Assistant had a server problem. Trying another model."
        )
    return exc


async def run_turn(
    user_text: str,
    history: list[dict],
    *,
    system_prompt: str,
    specs: list[ToolSpec],
    cancel: asyncio.Event,
    on_token: Callable[[str], None],
    on_thought: Callable[[str], None] | None = None,
    on_round_reset: Callable[[], None] | None = None,
    on_model_step: Callable[[], Awaitable[None]] | None = None,
    should_stop: Callable[[], bool] | None = None,
    base_url: str | None = None,
    model: str | None = None,
    max_rounds: int = 6,
    timeout_s: float = 240.0,
    max_tokens: int = 2048,
) -> dict:
    """Run one agent turn through kani's `full_round_stream`.

    Returns `{"text", "model_steps", "model"}` — the facts the metering layer
    bills. `model_steps` counts ASSISTANT rounds only, which is the same floor
    rule `ai_credits` implements; step rows are emitted through `on_step`.

    The candidate loop carries the failed candidate's transcript forward (tool
    results included), so the next model continues from what already ran
    instead of repeating it.
    """
    from services.ai_service import AIMidStream, AIUnavailable
    from services.model_catalog import mark_model_failed, turn_candidates

    candidates = turn_candidates(model if model is not None else _model_name())
    if not candidates:
        raise AIUnavailable("No models are available from the router.")

    functions = build_functions(specs) if specs else None
    base_history = _chat_messages(history)

    t0 = time.monotonic()
    model_steps = 0
    collected: list[str] = []
    round_parts: list[str] = []
    history_msgs = list(base_history)
    last_model = candidates[0]

    # The stop check is polled here rather than sampled once by the caller:
    # "Stop immediately" has to land between tokens, and a model streaming at
    # 40 tokens a second would otherwise stream its whole answer first.
    def _stopped() -> bool:
        if should_stop is not None and should_stop():
            cancel.set()
            return True
        return cancel.is_set()

    for candidate in candidates:
        if _stopped():
            break
        last_model = candidate
        try:
            engine = await _build_engine(candidate, base_url, on_thought=on_thought)
        except AIUnavailable:
            raise
        except Exception as exc:
            # A run-once engine miss is also a dead candidate: without the mark
            # it leads every later turn too.
            logger.warning("AI: engine build failed for %s: %r", candidate, exc)
            mark_model_failed(candidate)
            continue

        # Past the model-call budget the candidate gets exactly one more round
        # with the tools stripped, so an over-cap turn still answers from what
        # it gathered instead of failing at the boundary.
        at_cap = 0 < max_rounds <= model_steps
        kani = CollabShellKani(
            engine,
            system_prompt=system_prompt or None,
            chat_history=list(history_msgs),
            functions=None if at_cap else functions,
            # One attempt only. A higher number lets kani spend another model
            # round re-asking after a tool error, which is a billable step the
            # user did not choose to buy for a bad argument.
            retry_attempts=1,
        )
        # Every candidate starts from its own answer, not from a dead one's
        # partial text: a walk after delivery discards that text rather than
        # splicing two models' words into one bubble.
        collected.clear()
        round_parts.clear()
        if on_round_reset is not None:
            on_round_reset()
        giving_final_answer = at_cap  # this candidate's first round is its last

        try:
            async for manager in kani.full_round_stream(
                None if history_msgs else user_text,
                # One more tool round than our own budget, deliberately: the
                # boundary below is what stops the turn, and it strips the tools
                # for the rescue round. kani's own cap returning first would end
                # an over-cap turn with the model's preamble instead of its
                # answer.
                max_function_rounds=max_rounds,
                max_tokens=max_tokens,
                # Absent under "auto", so the gateway decides. A depth the
                # router does not know is ignored upstream rather than fatal.
                **(
                    {"reasoning_effort": _thinking_depth()}
                    if _thinking_depth()
                    else {}
                ),
            ):
                if _stopped():
                    break
                if time.monotonic() - t0 > timeout_s:
                    break

                if manager.role is not ChatRole.ASSISTANT:
                    # Tool result: its body already ran inside kani's gather
                    # and emitted its own step row. Consuming the message only
                    # closes the row — it makes no request.
                    await manager.message()
                    # A tool round's text never belongs to the final answer:
                    # it is the "let me check that…" before the call. The
                    # caller drops its display buffer here too.
                    collected.clear()
                    round_parts.clear()
                    if on_round_reset is not None:
                        on_round_reset()
                    continue

                if model_steps >= max_rounds:
                    if giving_final_answer:
                        # The stripped final round is spent. The next manager
                        # has made no request yet, so stopping here is free.
                        break
                    # Strip the tools and let the model answer once from what
                    # it gathered. The manager is yielded before its request,
                    # so emptying the function map costs no HTTP. kani keeps a
                    # name -> AIFunction dict, so it is emptied, not replaced.
                    kani.functions = {}
                    giving_final_answer = True

                if model_steps and on_model_step is not None:
                    await on_model_step()
                model_steps += 1

                delivered = False
                stopped_mid_stream = False
                stream = manager.__aiter__()
                while True:
                    try:
                        if delivered:
                            chunk = await stream.__anext__()
                        else:
                            # First token: a candidate that cannot produce
                            # anything in CANDIDATE_TTFB_S is hung.
                            chunk = await asyncio.wait_for(
                                stream.__anext__(), CANDIDATE_TTFB_S
                            )
                    except StopAsyncIteration:
                        break
                    if isinstance(chunk, BaseCompletion):
                        continue
                    token = str(chunk)
                    if not token:
                        continue
                    if _stopped():
                        # A stop that lands mid-stream: the tokens already
                        # delivered are billed, nothing after them is.
                        stopped_mid_stream = True
                        break
                    delivered = True
                    collected.append(token)
                    round_parts.append(token)
                    on_token(token)

                if stopped_mid_stream:
                    # The stream is abandoned, so `manager.message()` would
                    # wait on an event the abandoned generator never sets and
                    # the turn would hang. The partial is the answer.
                    break
                message = await manager.message()
                if not getattr(message, "tool_calls", None):
                    answer = "".join(collected)
                    if not answer.strip():
                        # A round that said nothing is a silent candidate, not
                        # an answer: hand the turn to the next one. Returning
                        # here would bill a step for an empty bubble.
                        logger.info(
                            "AI: candidate %s said nothing; trying next", candidate
                        )
                        mark_model_failed(candidate)
                        history_msgs = list(kani.chat_history)
                        continue
                    return {
                        "text": answer,
                        "model_steps": model_steps,
                        "model": candidate,
                    }
                # Carry the candidate's own transcript (tool results included)
                # forward so the next model continues rather than repeats.
                history_msgs = list(kani.chat_history)
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            delivered = bool("".join(round_parts).strip())
            mapped = _map_failure(exc, delivered=delivered)
            if isinstance(mapped, AIMidStream):
                # The endpoint dropped after this candidate answered part of
                # the turn. The user already read those tokens, so the partial
                # IS the turn's answer — walking would splice two models' text
                # into one bubble, and there is nowhere healthy to walk to.
                logger.info("AI: %s dropped mid-answer; ending the turn", candidate)
                break
            if isinstance(mapped, RouterModelFailed):
                # This candidate model is the problem, not the router: skip it
                # for the circuit TTL so the next turn does not lead with it,
                # and walk on to the next candidate.
                mark_model_failed(candidate)
                # The reasoning tap keeps the upstream's own words from an error
                # frame, which is the difference between "glm-5.3-flash failed"
                # and why. A dead upstream arrives as HTTP 200 with the error
                # inside the stream, so the SDK's own message would be generic.
                upstream = getattr(getattr(engine, "tap", None), "last_error", None)
                served = getattr(getattr(engine, "tap", None), "last_model", "")
                logger.info(
                    "AI: %s failed for this turn; trying next%s%s",
                    candidate,
                    f" (served as {served})" if served else "",
                    f": {upstream.get('message') or upstream}" if upstream else "",
                )
                continue
            raise mapped from exc

    text = "".join(collected)
    if not text.strip():
        # A cancelled turn delivered nothing on purpose. Reporting it as
        # "unavailable" would make the caller show a router error the user
        # never had — and ai_credits reads AIUnavailable as exactly that.
        if cancel.is_set():
            return {"text": "", "model_steps": model_steps, "model": last_model}
        raise AIUnavailable("The Assistant did not answer. Try again.")
    return {"text": text, "model_steps": model_steps, "model": last_model}


def _model_name() -> str:
    from core.state import state

    return str(getattr(state, "ai_model", "") or "").strip()


def _thinking_depth() -> str | None:
    """The reading depth to ask for, or None to leave the router's own.

    Read live, like the model name, so a Settings change applies to the next
    turn without threading another parameter through three layers.

    "auto" returns None on purpose: the request then carries no
    `reasoning_effort` at all and the gateway decides, which is what both
    reference apps do (`DDGS/src/services/chat_agent.py:512-515`).
    """
    from core.state import state

    depth = str(getattr(state, "ai_thinking", "auto") or "auto").strip().lower()
    if depth in ("", "auto"):
        return None
    from core.constants import THINKING_DEPTHS

    return depth if depth in THINKING_DEPTHS else None

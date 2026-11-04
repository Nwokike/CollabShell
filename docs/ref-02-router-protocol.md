# Router Protocol Reference — CollabShell Client Contract

This document specifies the **exact protocol** the CollabShell client must speak to interoperate with the Kiri Router family (`lm-router` desktop app and `kiri-router` Cloudflare Worker gateway). It is derived from source inspection of both server implementations and the CollabShell client at HEAD `76a9d4b`.

---

## 1. HTTP API Contract

### 1.1 Endpoint Inventory

| Method | Path | Purpose | Auth | Server Source |
|--------|------|---------|------|---------------|
| `GET` | `/health` | Liveness + adapter identification | none | `kiri-router/src/routes.js:283-291` |
| `GET` | `/v1/models` | Model catalog (OpenAI list format) | `api_key` (any string) | `kiri-router/src/routes.js:227-251` |
| `GET` | `/account-limits` | Per-model rate hints + gateway metadata | `api_key` (any string) | `kiri-router/src/routes.js:253-281` |
| `GET` | `/v1/status` | Counts only (models/sources) | none | `kiri-router/src/routes.js:296-310` |
| `POST` | `/v1/chat/completions` | Chat completions (SSE + non-stream) | `api_key` (any string) | `kiri-router/src/routes.js:77-165` |
| `POST` | `/v1/responses` | OpenAI Responses API | `api_key` (any string) | `kiri-router/src/routes.js:167-203` |
| `POST` | `/v1/systemone` | TypeSafe passthrough (non-OpenAI shape) | `api_key` (any string) | `kiri-router/src/routes.js:205-225` |
| `POST` | `/acquire` | Embedded server: claim a port | internal | `lm-router/src/services/engine.py:295-308` |
| `POST` | `/release` | Embedded server: release a port | internal | `lm-router/src/services/engine.py` (via `run.py`) |

> **Note**: `lm-router` embeds `kiri-router`'s `run.py` as its gateway engine (fetched live from `router.kiri.ng`). The HTTP surface is identical. CollabShell's router client (`src/services/router.py`, `router_engine.py`) speaks this same API.

### 1.2 Request/Response Schemas

#### `GET /health`
```json
// Response 200
{
  "status": "ok",
  "adapter": "kiri-router",           // REQUIRED — client MUST verify this
  "version": "1.0.0",                  // gateway version string
  "uptime_sec": 1234,                  // seconds since gateway start
  "upstream": "kiri"
}
```
**Client contract**: A port is only a valid Kiri router if `status == "ok"` AND `adapter == "kiri-router"`. See `kiri-router/src/routes.js:283-291` and `lm-router/src/services/engine.py:124-134` (`_health` probe).

#### `GET /v1/models`
```json
// Request: Authorization: Bearer <any-string>
// Response 200
{
  "object": "list",
  "data": [
    {
      "id": "auto",                    // special rotating model
      "object": "model",
      "created": 1720000000,
      "owned_by": "kiri",
      "endpoint_type": "chat.completion",
      "is_free": true,
      "status": "active",
      "latency_ms": 850,
      "rate_hint": {
        "tier": "high",
        "approx_per_hour": null,
        "label": "High · No time cap; long wait after a limit, a VPN resets it"
      }
    },
    {
      "id": "gpt-4o-mini-free",
      "object": "model",
      "created": 1720000000,
      "owned_by": "kiri",
      "endpoint_type": "response",
      "is_free": true,
      "status": "active",
      "latency_ms": 1200,
      "rate_hint": { "tier": "medium", "approx_per_hour": 200, "label": "Medium · roughly 200 requests/hour" }
    }
    // ... more models
  ]
}
```
**Source**: `kiri-router/src/routes.js:227-251`. The catalog is sorted by `compareCatalog` (health rank → case-insensitive id) per `ids.js:69-80`.

#### `GET /account-limits`
```json
// Request: Authorization: Bearer <any-string>
// Query: ?format=json (default) or ?format=table
// Response 200 (format=json)
{
  "adapter_version": "1.0.0",
  "uptime_seconds": 1234,
  "total_models_available": 42,
  "free_models_available": 42,
  "free_models": [
    { "id": "auto", "endpoint": "chat.completion", "status": "active", "latency_ms": 850, "rate_hint": { ... } },
    { "id": "gpt-4o-mini-free", "endpoint": "response", "status": "active", "latency_ms": 1200, "rate_hint": { ... } }
  ],
  "zero_auth_supported": true
}
```
**Source**: `kiri-router/src/routes.js:253-281`. The `rate_hint` per model is the **authoritative** rate limit signal — the client must never synthesize its own.

#### `GET /v1/status`
```json
// Response 200
{
  "status": "ok",
  "models": { "total": 42, "active": 38, "degraded": 3, "failed": 1 },
  "sources": { "responsive": 3, "total": 4 },
  "last_discovery_sec": 45,
  "uptime_sec": 1234
}
```
**Source**: `kiri-router/src/routes.js:296-310`. Counts only — no source names, no model IDs (per `docs/decisions.md D11`).

#### `POST /v1/chat/completions`
```json
// Request (OpenAI Chat Completions format)
{
  "model": "auto",
  "messages": [
    { "role": "system", "content": "..." },
    { "role": "user", "content": "Hello" }
  ],
  "stream": true,
  "tools": [ { "type": "function", "function": { "name": "shell", ... } } ],
  "stream_options": { "include_usage": true }
}

// Streaming Response (SSE)
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":123,"model":"auto","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":123,"model":"auto","choices":[{"index":0,"delta":{"reasoning":"thinking..."},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":123,"model":"auto","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":10,"completion_tokens":20,"total_tokens":30}}

data: [DONE]

// Non-stream Response
{
  "id": "chatcmpl-123",
  "object": "chat.completion",
  "created": 123,
  "model": "auto",
  "choices": [{
    "index": 0,
    "message": { "role": "assistant", "content": "Hello!", "reasoning": "thinking..." },
    "logprobs": null,
    "finish_reason": "stop"
  }],
  "usage": { "prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30 }
}
```
**Source**: `kiri-router/src/routes.js:77-165`, `aggregate.js:1-68`. Key behaviors:
- The gateway **rewrites the echoed `model` field to the public ID** (never raw upstream ID) in both streaming and non-streaming responses (`aggregate.js:83-110`).
- `reasoning` / `reasoning_content` delta fields are supported and aggregated into `message.reasoning`.
- The gateway injects placeholder tools (`shell`, `read`) on every free-tier request; callers must include them or the request returns 429 (`convert.js:83-100`).
- The gateway prepends a harness system prompt (`injectHarnessSystem` in `convert.js:102-122`); a generic system prompt answers 429.

#### `POST /v1/responses`
```json
// Request (OpenAI Responses API format)
{
  "model": "gpt-4o-mini-free",
  "input": "USER: Hello\n\nASSISTANT: Hi there",
  "stream": true,
  "tools": [ { "type": "function", "name": "shell", ... } ],
  "max_output_tokens": 1000
}

// Streaming Response (SSE)
data: {"type":"response.output_text.delta","delta":"Hello","response":{"id":"resp-123","model":"gpt-4o-mini-free"}}

data: {"type":"response.completed","response":{"id":"resp-123","model":"gpt-4o-mini-free","usage":{"input_tokens":10,"output_tokens":20}}}

data: [DONE]
```
**Source**: `kiri-router/src/routes.js:167-203`. The gateway translates Chat Completions `messages` → Responses `input` via `convertToResponses` (`convert.js:124-160`). It **drops `max_tokens`** (Chat parameter) — native `max_output_tokens` passes through but budgets <16 are dropped (`dropTinyResponseBudget` in `convert.js:172-177`).

#### `POST /v1/systemone`
```json
// Request (TypeSafe format — NOT OpenAI shaped)
{
  "model": "jev-model",
  "messages": [ { "role": "user", "content": "test" } ],
  "stream": true
}

// Response: passthrough from upstream (TypeSafe shape)
```
**Source**: `kiri-router/src/routes.js:205-225`. **Not usable for chat** — body shape is completely different. The gateway translates `messages` → `state` + `questions` via `convertToSystemOne` (`convert.js:188-203`).

### 1.3 Authentication
- **Header**: `Authorization: Bearer <any-string>` — the gateway is **keyless by design** (`router_guide.py:14-15`).
- The client must send a non-empty string; `"any"` is conventional.
- No JWT, no OAuth, no validation on the gateway side.

### 1.4 Error Codes
| HTTP | Scenario | Client Action |
|------|----------|---------------|
| `400` | Invalid JSON, missing `model`, malformed payload | Log, don't retry |
| `429` | Rate limited (per-model or gateway) | **Model-level**: try next candidate. **Gateway-level**: back off. |
| `500` | Upstream error | Try next candidate |
| `503` | No route available (cold isolate) | Retry after `Retry-After: 2` |
| `502/504` | Upstream timeout | Try next candidate |

**Critical distinction** (`kani_backend.py:420-456`):  
- **Model-level failure** (429, 5xx, timeout on a specific upstream) → `RouterModelFailed` → walk to next candidate.  
- **Connection failure** (refused, DNS, TCP reset) → `_mark_router_failed()` → blackout entire router for 60s (`ROUTER_STICKY_COOLDOWN`).

### 1.5 `endpoint_type` Mapping
| `endpoint_type` | Kani `api_type` | Chat Capable | Notes |
|-----------------|-----------------|--------------|-------|
| `chat.completion` | `chat_completions` | ✅ | Primary path |
| `chat.completions` | `chat_completions` | ✅ | Alias |
| `chat` | `chat_completions` | ✅ | Alias |
| `response` | `responses` | ❌ | Upstream rejects; kani Responses path broken |
| `responses` | `responses` | ❌ | Same |
| `systemone` | `None` | ❌ | Non-OpenAI shape entirely |
| `messages` | `None` | ❌ | Anthropic Messages (Zen fallback) |
| `google` | `None` | ❌ | Gemini |

**Source**: `lm-router/src/core/catalog.py:14-35` (`ENDPOINTS`, `CHAT_CAPABLE_ENDPOINTS`). Only `chat.completion*` endpoints are verified end-to-end for chat.

---

## 2. Server Lifecycle Protocol

### 2.1 Port Acquisition (Embedded Server)
**Port range**: 8082–8092 inclusive (11 ports). **Source**: `constants.py:69-70` (`ROUTER_BASE_PORT=8082`, `ROUTER_SPAN=10`).

**Acquisition algorithm** (`lm-router/src/services/engine.py:295-308`, `run.py:2398-2415`):
1. Scan ports 8082..8092 for a listening Kiri router (`/health` + `adapter == "kiri-router"`).
2. If found: **adopt** it — return `(None, port)`, mark as foreign-owned.
3. If none: bind first free port, start `run.py` server, return `(server, port)`.
4. If all ports busy: raise `SystemExit` (no port available).

**CollabShell client implementation** (`router.py:277-331`, `router_engine.py:295-297`):
- `ensure_router()` orchestrates attach-or-embed.
- `probe_router()` scans with adapter check (critical — see Finding #3 in audit).
- `_router_server` module state tracks **only embedded** instance; foreign servers are never stopped.

### 2.2 Embedded vs Attached at Boot
| Scenario | Behavior |
|----------|----------|
| No router on 8082..8092 | Embed own `run.py` on first free port |
| Kiri router already running | **Adopt** it — attach, don't embed |
| Foreign service on 8082 (not Kiri) | Skip, continue scan — never adopt |

**Boot sequence** (`router_watchdog.py:131-160`):
1. Watchdog starts, calls `ensure_router()` **once** at boot.
2. On success: fetches catalog so header pill can show a model immediately.
3. On failure: logs at `info`, keeps watching (does not remove Start button).

**Critical bug** (audit Finding #4): Boot failure does not call `_publish_status("unavailable", None)`, so UI shows "Starting gateway…" indefinitely until first probe tick (up to 3s).

### 2.3 Watchdog / Heartbeat
**Interval**: 3s foreground, 30s background (`constants.py:77-78`).

**Watchdog loop** (`router_watchdog.py:162-209`):
1. `probe_router()` → gets `(status, port)`.
2. Compares against last published state.
3. On transition: calls `router._publish_status(status, port)` → updates `state.ai_router_status` / `state.ai_router_port`.
4. Wakes on `wake()` event (e.g., after `ensure_router()` succeeds).

**Health probe** (`router.py:121-134`, `engine.py:124-134`):
```python
async def _health(port):
    resp = await client.get(f"http://127.0.0.1:{port}/health", timeout=2.0)
    if resp.status_code == 200 and resp.json().get("adapter") == "kiri-router":
        return resp.json()
    return None
```

### 2.4 Release Semantics
- **Only embedded router is ever stopped** (`router.py:169-185`): `stop_router()` checks `_router_server is not None`.
- Foreign router (user-started) is **left alone** — app attaches and releases reference on exit only.
- `atexit` handler calls `shutdown()` → `stop_router()`.

---

## 3. Ledger / Credits Protocol

### 3.1 Turn Charging (Floor Rule)
**Source**: `ai_credits.py:85-92`, `credit_service.py:146-165`.

```python
def charged_steps(model_steps: int, text: str) -> int:
    """Floor rule: if ANY text delivered, bill at least 1 step."""
    delivered = bool((text or "").strip())
    return max(model_steps, 1) if delivered else model_steps
```

| Scenario | `model_steps` | `text` | Billed |
|----------|---------------|--------|--------|
| Normal completion | 1 | "Hello" | 1 |
| Tool round (model→tool→model) | 2 | "Result" | 2 |
| User stops mid-stream | 1 | "Partial" | 1 (floor) |
| Model error, no text | 0 | "" | 0 (hold refunded) |
| Connection drop after text | 1 | "Partial" | 1 (floor, `AIMidStream`) |

**Key invariant**: A hold is taken at turn start (`reserve(COST_STEP)`). If turn delivers text, floor rule ensures ≥1 step. If nothing delivered, hold is refunded.

### 3.2 Three-Phase Settlement
| Phase | Method | When |
|-------|--------|------|
| **Reserve** | `credits.reserve(COST_STEP)` | Turn start (best-effort; fails at balance 1) |
| **Extend** | `credits.reserve_more(tx, COST_STEP)` | Each additional model step |
| **Commit** | `credits.commit(tx, steps)` | Turn succeeds — charges exact steps |
| **Rollback** | `credits.rollback(tx)` | Turn cancelled/failed — releases hold |

**Idempotency**: `commit` ignores already-settled transactions (`credit_service.py:146-165`). Double-settle cannot double-charge.

### 3.3 Hold Expiry
- `ROLLBACK_SECONDS = 240` (`credit_service.py:28`).
- `sweep_expired_holds()` releases holds older than 240s **and marks them settled** so late `commit` becomes no-op.
- Age uses original `opened_at` — extending a hold does **not** reset the clock (prevents long turns from starving sweep).

### 3.4 Balance Endpoints
| Method | Description |
|--------|-------------|
| `get_balance(is_premium)` | Remaining today (refills to cap at 00:00 UTC) |
| `available(is_premium)` | `balance - sum(holds)` — spendable now |
| `daily_cap(is_premium)` | 50 (free) / 500 (premium) |
| `add_credits(amount)` | Ad top-up (2 credits, 30s cooldown) |

### 3.5 Client MUST-DO for Ledger Balance
1. **Always call `reserve()` before `run_turn()`** — but note audit Finding #5: current code reserves before router reachability known.
2. **Track `model_steps` per streamed round** (ASSISTANT role only — tool rounds are FUNCTION role, not billed).
3. **On any exception**: compute `charged_steps(model_steps + current_step_delivered, streamed_text)` and `_settle()`.
4. **On `CancelledError`**: same settlement, then re-raise.
5. **Never let a turn run without a hold** — if `reserve()` returns `None`, run hold-less and `charge()` directly on settle.

---

## 4. Model Catalog Protocol

### 4.1 Catalog Row Fields
From `GET /v1/models` (`kiri-router/src/routes.js:227-251`):
```json
{
  "id": "auto",                          // public ID (suffix-stripped)
  "object": "model",
  "created": 1720000000,
  "owned_by": "kiri",
  "endpoint_type": "chat.completion",   // chat.completion | response | systemone | messages | google
  "is_free": true,
  "status": "active",                   // active | untested (rate limited) | slow | failed
  "latency_ms": 850,
  "rate_hint": {
    "tier": "high",                     // high | medium | low | minimal
    "approx_per_hour": 200,             // null for unbounded
    "label": "High · No time cap..."    // GATEWAY'S OWN LABEL — display verbatim
  }
}
```

### 4.2 Special Model: `auto`
- **Rotating model** — gateway ranks healthy candidates, prefers tool-capable when tools present, rotates stickily per conversation (`catalog.py:4-11`).
- Always eligible when active (`catalog.py:65-66`).
- **Client must treat `auto` as a first-class model ID** — send `model: "auto"` to `/chat/completions`.

### 4.3 Client Selection Algorithm
**Source**: `model_catalog.py:121-165` (`candidate_models`, `turn_candidates`).

```python
# Ranked pool (tier → latency → id)
def candidate_models(exclude=None):
    for entry in catalog:
        if not is_active(entry): continue
        if not _is_chat_row(entry): continue      # endpoint_type must be chat.completion*
        if tier_of(entry) not in PICKABLE_TIERS: continue  # high/medium only
        if model_circuit_open(entry.id): continue
        yield (tier_rank, latency_ms, id)

# Turn walk order
def turn_candidates(chosen):
    if chosen and chosen != "auto":
        return [chosen] + [m for m in pool if m != chosen]
    return pool  # auto goes last implicitly (not in pool)
```

**PICKABLE_TIERS** = `("high", "medium")` — low/minimal excluded unless pool empty (fallback).

**Circuit breaker**: Failed model skipped for 300s (`MODEL_CIRCUIT_TTL`).

### 4.4 Default / Fastest Model Selection
- `serving_model()` → user's saved pick if still in pool, else `candidate_models()[0]` (highest tier, lowest latency).
- `adopt_default_model()` persists this after catalog refresh so pill shows real model.

---

## 5. Streaming Protocol

### 5.1 SSE Format (Chat Completions)
**Source**: `kiri-router/src/aggregate.js:1-68`, `rewriteModelStream` in same file.

```
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":123,"model":"auto","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":123,"model":"auto","choices":[{"index":0,"delta":{"reasoning":"thinking..."},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":123,"model":"auto","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":10,"completion_tokens":20,"total_tokens":30}}

data: [DONE]
```

**Key fields for client**:
- `choices[0].delta.content` → incremental text
- `choices[0].delta.reasoning` OR `choices[0].delta.reasoning_content` → reasoning/thinking (both supported, aggregated into `message.reasoning`)
- `usage` in final chunk → token counts
- `model` field is **rewritten to public ID** by gateway (`rewriteModelStream`)

### 5.2 SSE Format (Responses API)
```
data: {"type":"response.output_text.delta","delta":"Hello","response":{"id":"resp-123","model":"gpt-4o-mini-free"}}

data: {"type":"response.completed","response":{"id":"resp-123","model":"gpt-4o-mini-free","usage":{"input_tokens":10,"output_tokens":20}}}

data: [DONE]
```

### 5.3 Client Consumption (CollabShell)
**Source**: `kani_backend.py:540-620` — uses kani's `full_round_stream` with custom `ReasoningEngine` that tees SSE frames:
- `on_token` callback receives content deltas
- `on_thought` callback receives reasoning deltas (via `ThoughtTap` in `reasoning.py`)
- Per-candidate timeouts: `CANDIDATE_TTFB_S=12s` (first token), `CANDIDATE_READ_S=20s` (dead air)

---

## 6. CollabShell Client Compliance Audit

### 6.1 HTTP API Compliance

| Endpoint | CollabShell Implementation | Status | Severity |
|----------|---------------------------|--------|----------|
| `GET /health` | `router.py:121-134` `_health()` — **checks `adapter`** | ✅ Match | — |
| `GET /v1/models` | `model_catalog.py:311-362` `refresh_catalog()` | ⚠️ Diverges | High |
| `GET /account-limits` | `model_catalog.py:356-375` `_fetch_rate_hints()` — folds hints by ID | ✅ Match | — |
| `GET /v1/status` | Not used directly (watchdog uses `/health`) | — | Info |
| `POST /chat/completions` | Via kani `OpenAIEngine` → `kani_backend.py:299-351` `_build_engine()` | ⚠️ Diverges | Critical |
| `POST /responses` | Not used (chat_completions only) | — | Info |
| `POST /systemone` | Not used | — | Info |

**Critical Divergence #1** (`kani_backend.py:328-351`): `_build_engine(model, base_url, ...)` ignores passed `base_url` when falsy, re-calls `router.router_base()` causing redundant probe/embed. **Fix**: Remove fallback; require non-None `base_url`.

**High Divergence #2** (`model_catalog.py:327-330`): `refresh_catalog` accepts invalid/empty URL, returns stale catalog silently. **Fix**: Require valid URL; raise `AIUnavailable` if router unreachable.

**Critical Divergence #3** (`router.py:158-165`): `probe_router()` for held port checks only HTTP 200, **not `adapter`**. Foreign service returning 200 reported as "ready". **Fix**: Apply same adapter check as `_probe_existing_router`.

### 6.2 Server Lifecycle Compliance

| Behavior | CollabShell Implementation | Status | Severity |
|----------|---------------------------|--------|----------|
| Port scan 8082..8092 | `router.py:105-134` `_probe_existing_router()` | ✅ Match | — |
| Adapter verification on scan | `router.py:121-124` — checks `adapter == "kiri-router"` | ✅ Match | — |
| Adapter verification on held port | `router.py:158-165` — **MISSING** | ❌ Missing | Critical |
| Attach foreign, don't stop | `router.py:169-185` `stop_router()` checks `_router_server` | ✅ Match | — |
| Boot-time attach/embed | `router_watchdog.py:131-160` | ⚠️ Silent failure | Medium |
| Watchdog interval 3s/30s | `router_watchdog.py:202-206` | ✅ Match | — |
| Health probe every tick | `router_watchdog.py:175-180` | ✅ Match | — |

**Medium Divergence #4** (`router_watchdog.py:145-160`): Boot failure swallows exception, no `_publish_status("unavailable", None)`. UI shows "Starting gateway…" indefinitely. **Fix**: Publish unavailable on boot failure.

### 6.3 Ledger / Credits Compliance

| Rule | CollabShell Implementation | Status | Severity |
|------|---------------------------|--------|----------|
| Floor rule (≥1 if text) | `ai_credits.py:85-92` `charged_steps()` | ✅ Match | — |
| Reserve before turn | `ai_credits.py:146` — **before router check** | ⚠️ Wrong order | Medium |
| Reserve_more per step | `ai_credits.py:152-155` `_model_step_started()` | ✅ Match | — |
| Commit/rollback on settle | `ai_credits.py:169-192` `_settle()` | ✅ Match | — |
| Idempotent commit | `credit_service.py:146-165` | ✅ Match | — |
| Hold expiry 240s | `credit_service.py:28, 189-210` | ✅ Match | — |

**Medium Divergence #5** (`ai_credits.py:146`): `reserve()` called before `_ensure_router_for_turn()`. If router unavailable, hold taken then refunded — round-trip waste. **Fix**: Move reserve after router resolution.

### 6.4 Model Catalog Compliance

| Behavior | CollabShell Implementation | Status | Severity |
|----------|---------------------------|--------|----------|
| Tier from `rate_hint.tier` | `model_catalog.py:73-83` `tier_of()` | ✅ Match | — |
| Chat-eligible = chat.completion* | `model_catalog.py:85-87` `_is_chat_row()` | ✅ Match | — |
| `auto` always eligible | `model_catalog.py:65-66` `is_chat_eligible()` | ✅ Match | — |
| Ranked: tier → latency → id | `model_catalog.py:145-165` `candidate_models()` | ✅ Match | — |
| Circuit breaker 300s | `model_catalog.py:175-185` | ✅ Match | — |
| `adopt_default_model` on refresh | `model_catalog.py:350-354` | ⚠️ Edge case | Low |

**Low Divergence #9** (`model_catalog.py:107-119`): `adopt_default_model` could persist model when catalog empty (theoretical). **Fix**: Assert model in `candidate_models()` before persist.

### 6.5 Streaming Compliance

| Feature | CollabShell Implementation | Status |
|---------|---------------------------|--------|
| Content deltas via `on_token` | `kani_backend.py:580-590` | ✅ |
| Reasoning deltas via `on_thought` | `reasoning.py` `ThoughtTap` + `kani_backend.py:550-555` | ✅ |
| Model ID rewrite handled by gateway | `aggregate.js:83-110` (server-side) | ✅ |
| Per-candidate timeouts | `kani_backend.py:540-545` `CANDIDATE_TTFB_S/READ_S` | ✅ |

---

## 7. Perfect Client Checklist

A fully compliant CollabShell client MUST:

### HTTP API
- [ ] **Verify `adapter == "kiri-router"` on ALL `/health` probes** (scan + held port)
- [ ] Send `Authorization: Bearer <any>` on all `/v1/*` requests
- [ ] Handle `429` as model-level (walk candidates) vs connection-level (blackout router)
- [ ] Respect `Retry-After: 2` on `503` (cold isolate)
- [ ] Use public model ID from catalog (gateway rewrites in stream)
- [ ] Never call `/v1/responses` or `/v1/systemone` for chat (not chat-capable)

### Server Lifecycle
- [ ] Scan 8082..8092 on startup, adopt existing Kiri router
- [ ] Embed own `run.py` only if no Kiri router found
- [ ] Never stop a foreign router
- [ ] Watchdog: probe `/health` every 3s (fg) / 30s (bg), publish on transition
- [ ] Boot failure → publish `"unavailable"` immediately, not after first tick

### Ledger / Credits
- [ ] Reserve **after** router reachability confirmed
- [ ] Track `model_steps` = count of ASSISTANT stream rounds only
- [ ] Apply floor rule: `max(model_steps, 1)` if any text delivered
- [ ] Settle on ALL paths: success, cancel, exception, connection drop
- [ ] Idempotent commit (guard against double-settle)
- [ ] Sweep holds >240s, mark settled so late commit no-ops

### Model Catalog
- [ ] Filter: `status == "active"` AND `endpoint_type` starts with `chat.completion`
- [ ] Rank: tier (high→medium) → latency_ms (asc) → id (asc)
- [ ] `auto` model: eligible when active, goes last in turn walk
- [ ] Circuit breaker: skip failed model for 300s
- [ ] Display gateway's `rate_hint.label` verbatim — never synthesize

### Streaming
- [ ] Consume `delta.content` for text, `delta.reasoning` / `delta.reasoning_content` for thinking
- [ ] Handle both SSE formats (chat completions + responses) if used
- [ ] Per-candidate timeouts: 12s first token, 20s dead air
- [ ] On stop mid-stream: bill floor rule, don't walk candidates

---

## 8. Severity Summary

| # | Area | Finding | Severity |
|---|------|---------|----------|
| 1 | HTTP API | `_build_engine` ignores `base_url`, re-probes | **Critical** |
| 2 | HTTP API | `refresh_catalog` accepts invalid URL | **High** |
| 3 | HTTP API | `probe_router` lacks adapter check on held port | **Critical** |
| 4 | Lifecycle | Watchdog boot failure silent | **Medium** |
| 5 | Ledger | Reserve before router check | **Medium** |
| 6 | Lifecycle | Verify path doesn't re-check foreign health | **Medium** |
| 7 | Engine | Fixed 1s retry backoff | Low |
| 8 | UI | Settings reload doesn't re-probe | Low |
| 9 | Catalog | `adopt_default_model` edge case | Low |
| 10 | API | `router_base_url` falls back to 8082 | Info |
| 11 | Perf | New HTTP client per candidate | Info |
| 12 | Config | Router constants hardcoded | Info |

---

## 9. Source References

### Kiri Router (Gateway)
- `kiri-router/src/routes.js` — All HTTP handlers
- `kiri-router/src/discovery.js` — Model discovery, health enrichment
- `kiri-router/src/aggregate.js` — SSE aggregation, model rewrite
- `kiri-router/src/convert.js` — Payload conversion, tool injection, harness
- `kiri-router/src/ids.js` — Public ID projection, catalog ordering
- `kiri-router/src/sources.js` — Upstream adapters, rate profiles
- `kiri-router/src/upstream.js` — Endpoints, headers, TLS profile

### LM Router (Desktop App — Embeds Kiri Router)
- `lm-router/src/services/engine.py` — Engine download, `acquire_server`, health probe
- `lm-router/src/services/http.py` — Shared HTTP client with retries
- `lm-router/src/core/catalog.py` — Endpoint vocabulary, chat eligibility, tier styling
- `lm-router/src/services/router_guide.py` — System prompt for model
- `lm-router/src/services/router_tools.py` — Gateway status/tools for agent

### CollabShell Client
- `src/services/router.py` — Probe, attach/embed, lifecycle
- `src/services/router_engine.py` — Engine download, validation, cache
- `src/services/router_watchdog.py` — Status loop, boot attach
- `src/services/model_catalog.py` — Catalog fetch, ranking, circuit breaker
- `src/services/ai_service.py` — Turn entry point, router resolution
- `src/services/kani_backend.py` — Agent loop, candidate walk, failure mapping
- `src/services/ai_credits.py` — Metering, floor rule, settlement
- `src/services/credit_service.py` — Balance, holds, daily cap
- `src/core/constants.py` — All router constants

---

*Generated from source inspection of `lm-router`, `kiri-router`, and CollabShell at HEAD `76a9d4b`. This document is the authoritative protocol reference for CollabShell's router client.*

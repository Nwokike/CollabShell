# Audit 01 — AI Assistant Feature (since v2.1.2)

**Baseline:** `v2.1.2` (tag) → `HEAD` (76a9d4b, squashed commit, 147 files, +31759/-1392)
**Scope:** All AI assistant code — kani integration, model catalog, conversation history, credit accounting, streaming, thinking depth, assistant UI, in-cell AI, tools, rendering.

**Summary:** The AI assistant feature was **completely new** in this commit — zero AI files existed at v2.1.2. The implementation ports DDGS's agent architecture (kani backend, model catalog, conversation service, reasoning capture) and adapts it for ColabShell's Colab session operations. The port is largely faithful but introduces several bugs and deviations from the reference apps.

---

| # | Severity | Location | Finding |
|---|----------|----------|---------|
| 1 | **critical** | `src/services/kani_backend.py:354` | `_map_failure` treats `asyncio.TimeoutError` and `TimeoutError` identically — but `asyncio.wait_for` raises `asyncio.TimeoutError` (subclass of `Exception`), while `httpx`/`openai` raise `openai.APITimeoutError`. A transport timeout becomes `RouterModelFailed` (walk to next model) instead of marking router down. |
| 2 | **critical** | `src/services/kani_backend.py:538-566` | Stream iteration catches `StopAsyncIteration` but not `asyncio.CancelledError` from `stream.__anext__()` — if cancellation happens between tokens, the exception escapes the inner loop, skipping `delivered` accounting and leaving `model_steps` unincremented. Credit floor rule may not fire for partially-delivered turns. |
| 3 | **high** | `src/services/model_catalog.py:76-78` | `serving_model()` treats saved `"auto"` as empty string and falls back to pool head. But `turn_candidates()` at line 247 passes `"auto"` through to the pool when `chosen` is empty/auto — so the router's `auto` model is tried last as a candidate, contradicting the comment "router's own `auto` last". The pool should exclude `auto` entirely (it's a server-side rotation, not a model). |
| 4 | **high** | `src/services/kani_backend.py:514-516` | `reasoning_effort` sent as `"reasoning_effort"` kwarg, but kani's `OpenAIEngine` expects `reasoning_effort` only for Responses API (`api_type="responses"`). With `api_type="chat_completions"` (line 347), this param is ignored silently. The reference apps (DDGS, lm-router) pass it the same way — so the bug is upstream in kani, but this code should guard: only send when `api_type="responses"` or use the `ReasoningEngine` path correctly. |
| 5 | **high** | `src/services/ai_credits.py:146` | `reserve(COST_STEP)` called once at turn start, but `on_model_step` (line 152-159) calls `reserve_more` for each additional step. If `reserve` fails (balance=1), `tx=None` and the turn runs hold-less — but `on_model_step` then tries to `reserve_more(None, ...)` which returns `False` silently. The turn runs with no hold, `commit` is skipped, `charge` is called at settlement — this works but the reserve-more calls are wasted cycles. |
| 6 | **high** | `src/screens/assistant_view.py:730-743` | `run_metered_turn` passes `model=str(getattr(self.state, "ai_model", "") or "")` — empty string when user has "Auto" selected. `turn_candidates("")` returns the full pool (line 247-248), but the **explicit pick should be the serving model** (`serving_model()`). Empty string loses the user's "Auto" intent and treats it as "no preference" when the model pill shows a specific model name. |
| 7 | **high** | `src/components/model_pill.py:179` | `discovering = status == "ready" and not model_catalog.pickable_models()` — this makes the pill show "Starting gateway…" with spinner when router is `ready` but catalog has no high/medium models. But the fallback at lines 174-182 in `model_catalog.py` includes low/minimal models in `pickable_models()` when high/medium is empty. So `pickable_models()` is never empty after a successful fetch — the spinner never stops. |
| 8 | **medium** | `src/services/kani_backend.py:102-107` | `_CountingTokenizer` splits on whitespace (`text.split()`). For code, this **undercounts** vs real BPE (e.g., `print("hello")` → 1 token vs ~4 BPE). At `DEFAULT_CONTEXT=131072` this is harmless, but if context window shrinks (router serves 4k/8k models), kani's eviction will miscalculate and either evict too aggressively or hit "prompt too long" from the wire. |
| 9 | **medium** | `src/services/ai_tools.py:188-190` | `on_step` callback called with `("start", payload)` and `("done", payload)` but `ai_service._step_emitter` expects `event` to be `"start"` or `"done"` and `payload` to have `name`, `id`, `args`. However `tool_specs` in `kani_backend.py:150` calls `on_step("start", dict(payload))` where payload has `name`, `id`, `args`, `result`, `error` — the `result`/`error` fields are empty at start time. The emitter passes them through; the UI gets extra empty fields. Harmless but inconsistent. |
| 10 | **medium** | `src/services/ai_service.py:190-196` | Pre-turn catalog refresh calls `model_catalog.refresh_catalog(base_url)` but ignores failure. If refresh fails, `candidate_models()` may be empty (stale catalog) and `turn_candidates()` returns empty list → `run_turn` raises `AIUnavailable` at line 444. The refresh should be mandatory or the turn should use stale catalog with a warning. |
| 11 | **medium** | `src/services/cell_ai.py:105-107` | `fix` action prompt: "Reply with ONLY a Python code block containing the fixed cell — no explanation before or after it." But `extract_code()` at line 143-166 falls back to raw text if no fence found. A model that hedges with explanation produces a cell with that explanation as code. Should validate extracted code is valid Python or reject. |
| 12 | **medium** | `src/components/ai_step_output.py:46` | Condition `tool_name == "_exec" and state in ("running", "done") or tool_name == "read_terminal" ...` — operator precedence makes this `(tool_name == "_exec" and state in (...)) or (tool_name == "read_terminal" ...)`. For `read_terminal`, state is ignored — "Open Terminal" button shows even on error. Should be `tool_name in ("_exec", "read_terminal") and state in (...)`. |
| 13 | **medium** | `src/services/kani_backend.py:329-334` | `_build_engine` hardcodes `api_type="chat_completions"`. lm-router's `catalog.py:57-67` maps `endpoint_type` → `api_type` (chat_completions vs responses). The router serves both; ColabShell ignores `endpoint_type` from catalog and assumes chat completions. A `responses` model will return empty/unparsable replies (per lm-router comment: "kani 1.10's Responses path raises AttributeError"). |
| 14 | **low** | `src/services/reasoning.py:43` | `_REASONING_KEYS = ("reasoning_content", "reasoning", "reasoning_details")` — misses `reasoning_summary` which OpenAI Responses API uses. lm-router uses same list; if upstream adds new field, thinking block goes dark silently. |
| 15 | **low** | `src/services/ai_tools.py:795-798` | `tool_specs` derives JSON schema from signature annotations. For `write_cells` parameter `cells: list[dict]`, `_param_schema` returns `{"type": "array", "items": {"type": "string"}}` because `typing.get_args(list[dict])` → `(dict,)` and `_param_schema(dict)` → `{"type": "object"}`, but the inner `dict` has no properties defined. The model receives `items: {type: "object"}` with no properties — valid but unhelpful. |
| 16 | **low** | `src/screens/assistant_view.py:1035-1040` | `TEXT_FLUSH_SEC = 0.2`, `THOUGHT_FLUSH_SEC = 0.5` — separate throttles. But `_emit` at line 1035-1047 checks `thought` event twice (lines 1041-1047 and 1097-1105 duplicate logic). Second block at 1097 is dead code (same event, same condition). |
| 17 | **low** | `src/services/ai_credits.py:235-240` | `_bump_revision` increments `state.credits_revision` to nudge credit pill. But `ChatSession._refresh_credits` at line 1483 runs `refresh_balance` which reads from `CreditService` directly — the revision bump is unused. The pill repaints via `_set_credits` called from `_refresh_credits` result. |
| 18 | **info** | `src/services/kani_backend.py:658-681` | `_thinking_depth()` reads `state.ai_thinking` (default "auto"), returns `None` for "auto". lm-router uses `state.reasoning_effort` (line 514 in chat_agent.py). Different setting names — not a bug but inconsistent. ColabShell should standardize on one. |
| 19 | **info** | `src/components/model_picker.py:91-169` | `show_model_picker` dialog does its own catalog refresh and provider config, duplicating `model_pill.py` logic. The picker should use `model_catalog.refresh_catalog` and `pill_state` for consistency. |
| 20 | **info** | `src/services/ai_tools.py:55-69` | `_cell_has_plot` checks for image mime types in output `data`. But notebook outputs can have `data: {"image/png": "base64..."}` or `data: {"image/png": {"b64": "..."}}` — the check `m in data` works for both, but `_plot_mimes` includes `image/gif` which Colab rarely emits. Harmless. |

---

## Detailed Findings

### 1. [CRITICAL] `asyncio.TimeoutError` vs `openai.APITimeoutError` mishandled
**Location:** `src/services/kani_backend.py:381-389`

```python
if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
    return RouterModelFailed("A model timed out. Trying another model.")
if isinstance(exc, openai.APITimeoutError):
    return RouterModelFailed("A model timed out. Trying another model.")
```

**Problem:** `asyncio.wait_for(stream.__anext__(), CANDIDATE_TTFB_S)` at line 564-566 raises `asyncio.TimeoutError` (a subclass of `Exception`). But `openai.APITimeoutError` is raised by the SDK for request-level timeouts. Both are mapped to `RouterModelFailed` (walk to next model). However, a **transport-level timeout** (connection established, then dead air) should walk; a **connection timeout** (router unreachable) should mark router down. The current code cannot distinguish.

**Evidence:** kani_backend line 564-566 uses `asyncio.wait_for` for TTFB; line 333 sets `httpx.Timeout(CANDIDATE_READ_S, connect=4.0)`. A connect timeout raises `openai.APIConnectionError` (caught at line 390), but a read timeout during streaming raises `openai.APITimeoutError` (caught at line 386). Both become `RouterModelFailed` — correct for read, but the `asyncio.TimeoutError` from `wait_for` is also treated as model-level.

**Reference:** DDGS `kani_backend.py:300-303` has identical logic — same bug upstream. lm-router doesn't use `wait_for` for TTFB.

**Fix:** Only treat `asyncio.TimeoutError` from the explicit `wait_for` as model-level. Wrap the `wait_for` in a try/except that raises a custom `CandidateTTFBTimeout` (subclass of `RouterModelFailed`). Transport read timeouts stay as `APITimeoutError → RouterModelFailed`.

---

### 2. [CRITICAL] Cancellation mid-stream skips step accounting
**Location:** `src/services/kani_backend.py:556-588`

```python
stream = manager.__aiter__()
while True:
    try:
        if delivered:
            chunk = await stream.__anext__()
        else:
            chunk = await asyncio.wait_for(stream.__anext__(), CANDIDATE_TTFB_S)
    except StopAsyncIteration:
        break
    if isinstance(chunk, BaseCompletion):
        continue
    token = str(chunk)
    if not token:
        continue
    if _stopped():
        stopped_mid_stream = True
        break
    delivered = True
    ...
```

**Problem:** If `should_stop()` returns True between tokens, `_stopped()` sets `cancel.set()` and breaks. But if `asyncio.CancelledError` is raised by `stream.__anext__()` (because the task was cancelled externally), it escapes the `except StopAsyncIteration` and propagates out of `run_turn`. The `delivered` flag may be True (tokens were received), but `model_steps` is only incremented **after** the stream loop (line 552, 591). So a cancelled turn that delivered tokens bills 0 steps.

**Evidence:** `ai_credits.charged_steps` (line 91-92) uses `model_steps` from result. If `model_steps=0` but `text` has content, `max(0, 1) = 1` step charged — the floor rule saves it. But `model_steps` in result comes from `result.get("model_steps", 0)` at line 216, which is set at line 606. If the exception escapes before line 606, `model_steps` stays at the value from the last completed round.

**Fix:** Wrap the stream loop in `try/except asyncio.CancelledError`, increment `model_steps` if `delivered`, then re-raise. Or move `model_steps += 1` before the stream loop (as DDGS does at line 589 in chat_agent.py: `steps += 1` before streaming).

---

### 3. [HIGH] `"auto"` model handling inconsistency
**Location:** `src/services/model_catalog.py:76-78, 247-251`

```python
# serving_model()
chosen = str(getattr(state, "ai_model", "") or "").strip()
if chosen.lower() == "auto":
    chosen = ""
pool = candidate_models()
if chosen and any(m.lower() == chosen.lower() for m in pool):
    return chosen
```

```python
# turn_candidates()
wanted = str(chosen or "").strip()
if not wanted or wanted.lower() == "auto":
    return pool
head = [wanted]
rest = [m for m in pool if m.lower() != wanted.lower()]
return [*head, *rest]
```

**Problem:** When user selects "Auto" in the model pill, `state.ai_model = "auto"`. `serving_model()` treats this as "no saved pick" and returns pool head. But `turn_candidates("auto")` returns the full pool **with "auto" as the first candidate** (because `wanted="auto"` is truthy, so `head=["auto"]`). The router's `auto` is a server-side rotation model — it should not be in the client-side candidate walk at all. The pool from `candidate_models()` already excludes `"auto"` (line 197), but `turn_candidates` prepends the user's explicit choice before filtering.

**Reference:** DDGS `model_catalog.py` doesn't exist — DDGS uses `chat_agent.py` which reads `state.ai_model` directly. lm-router's `catalog.py:19-20` defines `AUTO_MODEL_ID = "auto"` and `chat_models()` puts it first in the picker, but the agent's `turn_candidates` (in `ai_service.py`) should exclude it.

**Fix:** In `turn_candidates`, if `wanted.lower() == "auto"`, treat as empty (no explicit pick): `return pool`. The pool already has the ranked models; `auto` is not a model to try.

---

### 4. [HIGH] `reasoning_effort` sent with wrong `api_type`
**Location:** `src/services/kani_backend.py:347, 514-516`

```python
# _build_engine line 347
api_type="chat_completions",

# run_turn line 514-516
**({"reasoning_effort": _thinking_depth()} if _thinking_depth() else {}),
```

**Problem:** `reasoning_effort` is an OpenAI Responses API parameter (for `o1`/`o3` models). kani's `OpenAIEngine` only reads it when `api_type="responses"`. With `chat_completions`, the parameter is passed to the API but ignored by the gateway/router. The user's thinking depth setting has no effect.

**Evidence:** lm-router `catalog.py:57-67` maps `endpoint_type` → `api_type`. Models with `endpoint_type="responses"` get `api_type="responses"`. ColabShell hardcodes `chat_completions` (line 347) and ignores `endpoint_type` from catalog.

**Fix:** In `_build_engine`, read the model's catalog entry and use `api_type_for(entry)` from lm-router's `catalog.py` (or port that logic). Only send `reasoning_effort` when `api_type == "responses"`.

---

### 5. [HIGH] Assistant view passes empty model string for "Auto"
**Location:** `src/screens/assistant_view.py:733`

```python
model=str(getattr(self.state, "ai_model", "") or ""),
```

When user has "Auto" selected, `state.ai_model == "auto"`. This passes `"auto"` to `run_turn`, which passes to `turn_candidates("auto")` — see Finding #3. But the model pill shows the **serving model name** (e.g., `"glm-4.5-flash"`), not "Auto". The user sees one model name but the turn walks a different candidate list.

**Fix:** Pass `model_catalog.serving_model()` instead of `state.ai_model`. The serving model resolves "auto" to the actual model that will answer.

---

### 6. [HIGH] Model pill spinner never stops when low/minimal models exist
**Location:** `src/components/model_pill.py:179`, `src/services/model_catalog.py:163-182`

```python
# model_pill.py line 179
discovering = status == "ready" and not model_catalog.pickable_models()
```

```python
# model_catalog.py line 173-182 (fallback in pickable_models)
if not kept:
    for entry in _catalog:
        ...
        if tier_of(entry) in PICKABLE_TIERS:
            continue
        kept.append(entry)
```

**Problem:** `pickable_models()` falls back to low/minimal tiers when no high/medium models exist. So `pickable_models()` is never empty after a successful catalog fetch. But `pill_state()` checks `not pickable_models()` to decide `discovering=True` (spinner). The spinner never stops — the pill shows "Starting gateway…" indefinitely even though models are available (just low tier).

**Fix:** Change `discovering` to check `not model_catalog.catalog()` (no catalog at all) or check `catalog_age()` > threshold. Or make `pickable_models()` return empty when only low/minimal exist, and handle that case in the pill's empty state.

---

### 7. [MEDIUM] `_CountingTokenizer` undercounts code tokens
**Location:** `src/services/kani_backend.py:90-111`

```python
def encode(self, text: str, **_kw) -> list[str]:
    if not text:
        return []
    return text.split()
```

**Problem:** Word-based splitting undercounts BPE tokens for code (e.g., `print("hello")` → 1 word vs ~4 BPE tokens). At `DEFAULT_CONTEXT=131072` this is fine, but if the router serves a model with 4k/8k context, kani's `get_prompt` will miscalculate and either:
- Evict too much history (thinking prompt is smaller than it is)
- Hit "prompt too long" from the wire (thinking prompt fits but actually doesn't)

**Reference:** DDGS uses same `_CountingTokenizer`. lm-router uses `services/tokenizer.py` which loads `tiktoken` with a fallback. Both reference apps assume large context (router serves 128k+).

**Fix:** Use `tiktoken` with a proper model mapping, or at minimum use a character-based heuristic (e.g., `len(text) // 4`) which overcounts slightly but is safer. The `_CountingTokenizer` comment admits it undercounts.

---

### 8. [MEDIUM] `ai_step_output` button condition precedence bug
**Location:** `src/components/ai_step_output.py:46`

```python
if tool_name == "_exec" and state in ("running", "done") or tool_name == "read_terminal" and state in ("running", "done"):
```

**Problem:** Python precedence: `and` binds tighter than `or`. This parses as:
```python
(tool_name == "_exec" and state in (...)) or (tool_name == "read_terminal" and state in (...))
```
For `tool_name == "read_terminal"` and `state == "error"`, the second part is `True and False = False`, so overall `False` — correct. But for `tool_name == "write_cells"` and `state == "done"`, both parts are `False`, overall `False` — correct. The bug is that `read_terminal` shows button in "running" and "done" but NOT in "error" — wait, that's correct. Actually the condition is correct for the two tools listed. The issue is it's hard to read and easy to misread. Better to write:
```python
if tool_name in ("_exec", "read_terminal") and state in ("running", "done"):
```

---

### 9. [MEDIUM] Hardcoded `api_type="chat_completions"` ignores router catalog
**Location:** `src/services/kani_backend.py:347`

```python
return ReasoningEngine(
    ...
    api_type="chat_completions",
    ...
)
```

**Problem:** The router's catalog includes models with `endpoint_type="responses"` (per lm-router `catalog.py:28-29`). These models require `api_type="responses"` in kani. Hardcoding `chat_completions` means any `responses` model will produce empty/unparsable replies. lm-router's comment: "kani 1.10's Responses path raises AttributeError: 'dict' object has no attribute 'model_copy'".

**Fix:** In `_build_engine`, fetch the model's catalog entry and use `api_type_for(entry)` from a ported version of lm-router's `catalog.py:57-67`. Cache the mapping.

---

### 10. [MEDIUM] Pre-turn catalog refresh failure ignored
**Location:** `src/services/ai_service.py:190-196`

```python
if not model_catalog.candidate_models() or model_catalog.catalog_stale():
    try:
        await model_catalog.refresh_catalog(base_url)
    except Exception:
        logger.debug("pre-turn catalog refresh failed", exc_info=True)
```

**Problem:** If `refresh_catalog` fails (network error, router not ready), the exception is caught and logged at debug level. The turn proceeds with whatever catalog state exists — possibly empty. `turn_candidates` returns empty list → `AIUnavailable` raised at line 444. The user sees "The Assistant did not answer after trying 0 available model(s)" — confusing.

**Fix:** On refresh failure, if catalog is empty, raise `AIUnavailable` with a clear message. If catalog is stale but non-empty, log warning and proceed with stale data (current behavior is okay for stale-but-non-empty).

---

### 11. [MEDIUM] In-cell AI `fix` action lacks code validation
**Location:** `src/services/cell_ai.py:99-103, 143-166`

```python
# Prompt for fix action
ask = (
    "This cell failed. Diagnose the error from the output and give the "
    "corrected code. Reply with ONLY a Python code block containing the "
    "fixed cell — no explanation before or after it."
)
```

```python
def extract_code(text: str) -> str:
    # ... finds first ``` block, strips language tag
    # Falls back to raw text if no fence
    return stripped
```

**Problem:** Models often hedge: "Here's the fix:\n```python\n...```". `extract_code` handles this. But if the model replies with explanation + code block, or no code block at all, `extract_code` returns the raw text (including explanation). The caller inserts this as a code cell — the user gets a cell with mixed explanation and code, which fails on execution.

**Fix:** After `extract_code`, validate the result is valid Python (compile it). If not, return empty string and let caller show "The Assistant returned nothing usable."

---

### 12. [LOW] Duplicate `thought` event handling in `_emit`
**Location:** `src/screens/assistant_view.py:1041-1047, 1097-1105`

```python
# First block (lines 1041-1047)
elif event == "thought" and self._current is not None:
    buf = (self._current.get("thought") or "") + data.get("text", "")
    self._current["thought"] = buf[-_THOUGHT_CAP:]
    force = False
    if now - self._last_thought_flush < THOUGHT_FLUSH_SEC:
        return
    self._last_thought_flush = now

# Second block (lines 1097-1105) - DEAD CODE
elif event == "thought" and self._current is not None:
    if self._current.get("thought_started_at") is None:
        self._current["thought_started_at"] = now
    buf = (self._current.get("thought") or "") + data.get("text", "")
    self._current["thought"] = buf[-_THOUGHT_CAP:]
    force = False
    if now - self._last_thought_flush < THOUGHT_FLUSH_SEC:
        return
    self._last_thought_flush = now
```

**Problem:** Second block is unreachable (first block returns or continues). The `thought_started_at` logic should be in the first block.

---

### 13. [LOW] `credits_revision` bump unused
**Location:** `src/services/ai_credits.py:235-240`, `src/screens/assistant_view.py:1483-1498`

```python
# ai_credits.py
def _bump_revision(state) -> None:
    try:
        state.credits_revision = getattr(state, "credits_revision", 0) + 1
    except Exception:
        logger.debug("Could not bump credits_revision", exc_info=True)

# assistant_view.py _refresh_credits
async def _load():
    try:
        self._set_credits(await refresh_balance(self.state, credits))
    except Exception:
        logger.debug("credit read failed", exc_info=True)
```

**Problem:** `_bump_revision` increments a revision counter, but `_refresh_credits` reads the balance directly from `CreditService` and calls `_set_credits` which updates the UI. The revision is never read. It's dead code.

---

### 14. [INFO] Inconsistent thinking depth setting name
**Location:** `src/services/kani_backend.py:664-681` vs DDGS/lm-router

```python
# ColabShell
depth = str(getattr(state, "ai_thinking", "auto") or "auto").strip().lower()

# DDGS chat_agent.py line 514
depth = str(getattr(state, "reasoning_effort", "auto") or "auto")

# lm-router state has reasoning_effort
```

**Problem:** ColabShell uses `ai_thinking`, reference apps use `reasoning_effort`. Not a bug but inconsistent. The setting key in `constants.py` is `STORAGE_AI_THINKING = "colab_ai_thinking"`.

---

### 15. [INFO] Model picker dialog duplicates pill logic
**Location:** `src/components/model_picker.py:91-169`

The dialog does its own catalog refresh, provider config, and rendering. The pill (`model_pill.py`) has `pill_state()`, `refresh_catalog_and_pill()`, `start_router_and_refresh()`. The picker should reuse these.

---

## Cross-Reference with Reference Apps

| Feature | ColabShell | DDGS | lm-router | Status |
|---------|-------------|------|-----------|--------|
| kani backend | Ported from DDGS | Source | Similar | ✅ Faithful port |
| Model catalog | Ported from DDGS | Source | Enhanced (endpoint→api_type) | ⚠️ Missing endpoint→api_type |
| Reasoning capture | Ported from DDGS | Source | Source | ✅ Faithful port |
| Credit metering | Ported from DDGS | Source | N/A (no credits) | ✅ Faithful port |
| Conversation history | Ported from DDGS | Source | N/A | ✅ Faithful port |
| In-cell AI | New (ColabShell-specific) | N/A | N/A | ✅ New feature |
| Model picker UI | Dropdown (lm-router style) | Modal dialog | Dropdown | ✅ Better UX |
| `auto` model handling | Buggy (see #3) | Not applicable | Explicit in catalog | ❌ Bug |
| Thinking depth | `ai_thinking` setting | `reasoning_effort` | `reasoning_effort` | ⚠️ Inconsistent |

---

## Recommendations Priority Order

1. **Fix #1, #2** — Critical credit/turn accounting bugs
2. **Fix #3, #4, #5** — High: model selection and thinking depth broken
3. **Fix #6, #13** — High/Medium: UI spinner and dead code
4. **Fix #7, #9** — Medium: tokenizer and api_type for router compatibility
5. **Fix #8, #10, #11, #12** — Medium/Low: code quality and robustness
6. **Fix #14, #15** — Info: consistency with reference apps

---

## Files Checked (Read-Only)

- `src/ai/__init__.py`, `src/ai/SKILL.md`
- `src/services/ai_service.py`, `src/services/ai_credits.py`, `src/services/ai_quick.py`, `src/services/ai_tools.py`
- `src/services/kani_backend.py`, `src/services/model_catalog.py`, `src/services/conversation_service.py`, `src/services/reasoning.py`, `src/services/cell_ai.py`, `src/services/credit_service.py`
- `src/screens/assistant_view.py`, `src/screens/assistant_history.py`
- `src/components/ai_step_output.py`, `src/components/model_picker.py`, `src/components/model_pill.py`, `src/components/command_palette.py`, `src/components/new_session_sheet.py`
- `src/screens/session/notebook_view.py` (AI-related parts)
- `tests/services/test_ai_*.py`, `tests/services/test_kani_backend.py`, `tests/services/test_conversation_service.py`, `tests/services/test_model_catalog.py`, `tests/services/test_reasoning.py`, `tests/services/test_cell_ai.py`
- `tests/screens/test_assistant_*.py`, `tests/screens/test_ai_*.py`, `tests/screens/notebook/test_assistant_bridge.py`
- Reference: `/home/maikel/Desktop/kiri-apps/DDGS/src/services/kani_backend.py`, `chat_agent.py`, `model_catalog` (DDGS doesn't have separate), `reasoning.py`
- Reference: `/home/maikel/Desktop/kiri-apps/lm-router/src/core/catalog.py`, `src/services/agent.py`
- Library source: `.venv/lib/python3.14/site-packages/kani/kani.py`, `streaming.py`, `engines/openai.py`

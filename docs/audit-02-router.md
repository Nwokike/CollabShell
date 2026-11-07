# Audit: LM-Router Client Stack (since v2.1.2)

**Baseline:** tag `v2.1.2` (50fe98b) → HEAD `76a9d4b` (squashed 61 commits)  
**Scope:** `src/services/router.py`, `router_engine.py`, `router_watchdog.py`, `src/screens/settings/ai_section.py`, `src/core/channel.py`, `tests/e2e/test_router_acquire.py`, `tests/e2e/test_turn_ledger.py`, `tests/fixture_router.py`, `tests/test_phase5_regression.py`, `tests/services/test_router.py`, `tests/services/test_router_engine.py`, `tests/services/test_router_watchdog.py`, `src/services/ai_service.py`, `src/services/ai_credits.py`, `src/services/model_catalog.py`, `src/services/kani_backend.py`

---

## Summary Table

| # | Severity | Location | Finding |
|---|----------|----------|---------|
| 1 | critical | `src/services/kani_backend.py:328-351` | `_build_engine` ignores `base_url` parameter when `None`, re-calls `router.router_base()` causing redundant probe/embed |
| 2 | high | `src/services/model_catalog.py:311-362` | `refresh_catalog` ignores `router_url` protocol check; passes empty string to `_http_client` on invalid URL |
| 3 | high | `src/services/router.py:138-168` | `probe_router` returns `("ready", port)` for attached foreign router without verifying `/health` responds with `adapter: "kiri-router"` |
| 4 | medium | `src/services/router_watchdog.py:145-160` | Boot-time `ensure_router()` swallows all exceptions; router failure at boot leaves no visible error in UI |
| 5 | medium | `src/services/ai_credits.py:146` | `reserve(COST_STEP)` called before router reachability known; hold taken even if router unavailable |
| 6 | medium | `src/services/router.py:244-331` | `ensure_router(verify=True)` does not re-verify foreign router health after `_probe_miss_until` cleared |
| 7 | low | `src/services/router_engine.py:74-91` | Engine download retry uses fixed 1s backoff; no exponential backoff for transient failures |
| 8 | low | `src/screens/settings/ai_section.py:181-199` | `_reload_router_status` only bumps revision; does not trigger actual re-probe |
| 9 | low | `src/services/model_catalog.py:107-119` | `adopt_default_model` persists model even when catalog empty; can save invalid model |
| 10 | info | `src/services/router.py:334-344` | `router_base_url` falls back to `AI_DEFAULT_ROUTER_URL` (8082) when no router; misleading for UI |
| 11 | info | `src/services/kani_backend.py:299-351` | `_build_engine` creates new `httpx` client per candidate; no connection pooling |
| 12 | info | `src/core/constants.py:66-89` | Router constants hardcoded; no config file / env override for `ENGINE_URL`, `ROUTER_BASE_PORT`, `ROUTER_SPAN` |

---

## Detailed Findings

### 1. `_build_engine` ignores passed `base_url`, re-probes router unnecessarily
**Location:** `src/services/kani_backend.py:328-351`  
**Changed since 2.1.2:** Yes (new file)  
**Problem:** `_build_engine(model, base_url, ...)` accepts `base_url` but at line 328 does `base = base_url or await router.router_base()`. When caller passes a valid URL (e.g., from `ai_service._ensure_router_for_turn()`), it is used. However, the fallback `router.router_base()` re-triggers the entire attach/embed logic including probe scan, engine download, and server bind. This defeats the purpose of resolving the router once per turn.  
**Evidence:**  
- `ai_service.py:179` calls `base_url = await _ensure_router_for_turn()` which returns resolved URL  
- `ai_service.py:229` passes `base_url=base_url` to `kani_backend.run_turn`  
- `kani_backend.py:470` passes `base_url` to `_build_engine`  
- But `_build_engine:328` ignores it if falsy, re-calling `router.router_base()`  
**Better way:** Remove the fallback. Require `base_url` to be non-None (caller already guarantees this). If `None`, raise `AIUnavailable` immediately.

---

### 2. `refresh_catalog` accepts invalid/empty router URL, sends malformed request
**Location:** `src/services/model_catalog.py:311-362`  
**Changed since 2.1.2:** Yes (new file)  
**Problem:** `refresh_catalog(router_url)` at line 327-330 checks `if not base.startswith(("http://", "https://"))` but then returns `pickable_models()` silently. The caller `ai_service.run_turn` (line 194) calls `refresh_catalog(base_url)` where `base_url` comes from `_ensure_router_for_turn()` which can return `None` (line 69). Passing `None` → `""` → fails protocol check → returns stale catalog without logging a clear error.  
**Evidence:**  
- `model_catalog.py:327-330`: `base = (router_url or "").strip().rstrip("/")` then protocol check  
- `ai_service.py:179-184`: `_ensure_router_for_turn` returns `None` when no router  
- `ai_service.py:192-196`: calls `refresh_catalog(base_url)` with potentially `None`  
**Better way:** Make `refresh_catalog` require valid URL; raise `AIUnavailable` if router unreachable. Or make `_ensure_router_for_turn` raise instead of returning `None`.

---

### 3. `probe_router` trusts attached foreign router without `adapter` verification
**Location:** `src/services/router.py:138-168`  
**Changed since 2.1.2:** Yes (new file)  
**Problem:** `probe_router()` at lines 150-157: when `_router_port` is set (attached foreign router), it does a single `/health` GET and returns `("ready", port)` on *any* 200 response. It does **not** verify `resp.json().get("adapter") == "kiri-router"`. Contrast with `_probe_existing_router` (lines 121-124) which correctly checks the adapter field. A foreign service returning 200 on `/health` would be reported as "ready".  
**Evidence:**  
- `router.py:158-165`: probe on held port checks only `status_code == 200`  
- `router.py:121-124`: `_probe_existing_router` checks `adapter == "kiri-router"`  
- `kiri-router/src/routes.js:283-291`: `/health` returns `{"adapter": "kiri-router", ...}`  
**Better way:** Apply same adapter check in `probe_router` for held ports.

---

### 4. Watchdog swallows boot-time router failures silently
**Location:** `src/services/router_watchdog.py:145-160`  
**Changed since 2.1.2:** Yes (new file)  
**Problem:** The watchdog's `_loop()` at boot (lines 145-160) calls `router.ensure_router()` and catches *all* exceptions, logging only at `info` level: `"AI router: not started at boot (%s); will keep watching"`. No status is published to UI (`_publish_status` not called on failure). The pill shows "Starting gateway…" indefinitely because `ai_router_status` remains "starting" (boot default).  
**Evidence:**  
- `router_watchdog.py:145-160`: try/except swallows exception, no `_publish_status` call  
- `router.py:51-74`: `_publish_status` only called on success paths  
- Commit 5a81883: "watchdog never published" — this is the bug  
**Better way:** On boot failure, call `_publish_status("unavailable", None)` so UI shows honest state. Keep watching but surface the failure.

---

### 5. Credit hold taken before router reachability confirmed
**Location:** `src/services/ai_credits.py:146`  
**Changed since 2.1.2:** Yes (new file)  
**Problem:** `run_metered_turn` at line 146 calls `await credits.reserve(COST_STEP, is_premium)` *before* `ai_service.run_turn` which calls `_ensure_router_for_turn`. If router is unavailable, the turn fails at `ai_service.py:180-184` raising `AIUnavailable`, but the hold was already taken. The `except Exception` block at line 202-214 calls `_settle(steps)` which rolls back the hold — but this is a round-trip that could be avoided.  
**Evidence:**  
- `ai_credits.py:134-143`: balance check, then line 146 `reserve`  
- `ai_service.py:179-184`: router resolution, raises `AIUnavailable` if None  
- `ai_credits.py:202-214`: exception handler rolls back  
**Better way:** Move `reserve` inside `try` block after `run_turn` succeeds, or make `_ensure_router_for_turn` synchronous and call before reserve.

---

### 6. `ensure_router(verify=True)` doesn't re-verify foreign router after miss-TTL cleared
**Location:** `src/services/router.py:244-331`  
**Changed since 2.1.2:** Yes (new file)  
**Problem:** At line 260, `ensure_router(verify=True)` calls `probe_router()` which for a foreign-attached port ( `_router_server is None`) only checks HTTP 200 (finding #3). If that passes, it returns the port. But if the foreign router died *after* the miss-TTL expired (line 270: `_probe_miss_until = 0.0`), the next `verify=True` call would re-probe — but `probe_router` doesn't verify `adapter` field. A dead foreign router returning 200 with wrong body would be trusted.  
**Evidence:**  
- `router.py:257-270`: verify path calls `probe_router`, clears miss-TTL on failure  
- `router.py:158-165`: probe on held port lacks adapter check  
**Better way:** Fix #3; then verify path works correctly.

---

### 7. Engine download retry uses fixed 1s backoff
**Location:** `src/services/router_engine.py:74-91`  
**Changed since 2.1.2:** Yes (new file)  
**Problem:** `_download` at line 88-90 does `await asyncio.sleep(1.0)` on first failure. No exponential backoff, no jitter. DDGS's `engine.py:62-63` uses `time.sleep(1.0)` same. Upstream `router.kiri.ng` may rate-limit; fixed retry can hammer.  
**Evidence:**  
- `router_engine.py:75-91`: two attempts, fixed 1s sleep  
- `lm-router/src/services/engine.py:49-63`: same pattern (sync)  
**Better way:** Exponential backoff with jitter: `await asyncio.sleep(1.0 * (2 ** attempt) + random.uniform(0, 0.5))`.

---

### 8. Settings "Reload" button doesn't trigger actual router re-probe
**Location:** `src/screens/settings/ai_section.py:181-199`  
**Changed since 2.1.2:** Yes (modified)  
**Problem:** `_reload_router_status` (lines 190-199) only increments `router_status_revision` to force UI rebuild. It does **not** call `router.probe_router()` or `ensure_router(verify=True)`. The watchdog ticks every 3s anyway, so the button is redundant — but if user clicks it during the 3s interval, nothing happens.  
**Evidence:**  
- `ai_section.py:190-199`: only bumps revision counter  
- `router_watchdog.py:162-209`: loop probes every 3s  
**Better way:** Call `router.ensure_router(verify=True)` in `_reload_router_status` and await it, then bump revision.

---

### 9. `adopt_default_model` persists model when catalog is empty
**Location:** `src/services/model_catalog.py:107-119`  
**Changed since 2.1.2:** Yes (new file)  
**Problem:** `adopt_default_model` (lines 89-104) calls `serving_model()` which returns `candidate_models()[0]` if pool non-empty. But if catalog is empty (router not started), `candidate_models()` returns `[]`, `serving_model()` returns `""`, and line 102-103: `if model and model != state.ai_model: state.ai_model = model` — the `model` is `""` (falsy), so it doesn't overwrite. However, `apply_catalog` (line 354) calls `adopt_default_model()` *after* installing rows. If `rows` is empty (line 304-306), it returns early **without** calling `adopt_default_model`. But if rows exist but all filtered out (e.g., no active chat models), `apply_catalog` installs empty `_catalog`, then `adopt_default_model` sees empty pool and does nothing — correct. The bug is theoretical: if a non-chat model slips through, it could be saved.  
**Evidence:**  
- `model_catalog.py:300-308`: `apply_catalog` early-returns on empty input  
- `model_catalog.py:350-354`: `adopt_default_model` called after successful apply  
**Better way:** Add assertion that `model` is in `candidate_models()` before persisting.

---

### 10. `router_base_url` falls back to hardcoded 8082 when no router
**Location:** `src/services/router.py:334-344`  
**Changed since 2.1.2:** Yes (new file)  
**Problem:** `router_base_url(port=None)` at line 342-343 returns `constants.AI_DEFAULT_ROUTER_URL` ("http://127.0.0.1:8082/v1") when `_router_port is None`. This URL is used by `model_catalog.router_url_for_read()` (line 61) as last resort. If router never started, catalog refresh hits 8082 (connection refused), logs "catalog refresh skipped: no usable router URL", returns stale catalog. Misleading because 8082 may not be the actual port.  
**Evidence:**  
- `router.py:342-343`: fallback to `AI_DEFAULT_ROUTER_URL`  
- `model_catalog.py:53-61`: `router_url_for_read` priority: override → live port → default  
- `constants.py:55`: `AI_DEFAULT_ROUTER_URL = "http://127.0.0.1:8082/v1"`  
**Better way:** Return `None` when no router; let callers handle absent router explicitly.

---

### 11. `_build_engine` creates new HTTP client per candidate (no pooling)
**Location:** `src/services/kani_backend.py:299-351`  
**Changed since 2.1.2:** Yes (new file)  
**Problem:** Each candidate model creates a new `openai.AsyncOpenAI` client with its own `httpx` transport (line 335-342). The candidate walk tries multiple models sequentially; each gets a fresh connection pool. No reuse across candidates.  
**Evidence:**  
- `kani_backend.py:335-342`: `openai.AsyncOpenAI` created per `_build_engine` call  
- `kani_backend.py:470`: called per candidate in loop  
**Better way:** Share a single `httpx.AsyncClient` with connection pooling across candidates. Pass `http_client=shared_client` to `AsyncOpenAI`.

---

### 12. Router constants hardcoded; no config/env override
**Location:** `src/core/constants.py:66-89`  
**Changed since 2.1.2:** Yes (modified)  
**Problem:** `ENGINE_URL`, `ROUTER_BASE_PORT`, `ROUTER_SPAN`, `ROUTER_PROBE_TIMEOUT`, `ROUTER_HEALTH_TIMEOUT`, `PROBE_MISS_TTL`, `ROUTER_STICKY_COOLDOWN`, `ROUTER_STATUS_INTERVAL_S`, `ROUTER_STATUS_INTERVAL_BG_S`, `ROUTER_START_TIMEOUT_S`, `ENGINE_USER_AGENT` are all hardcoded constants. No mechanism to override via config file, environment variable, or Settings UI. Enterprise/air-gap deployments cannot point to internal engine mirror or change port range.  
**Evidence:**  
- `constants.py:66-89`: all router constants hardcoded  
- `router.py`: uses constants directly  
- `router_engine.py`: uses `constants.ENGINE_URL`, `constants.ENGINE_USER_AGENT`  
**Better way:** Add `src/core/config.py` with `Config` class reading from `~/.collabshell/config.toml` and env vars (`COLLABSHELL_ROUTER_ENGINE_URL`, `COLLABSHELL_ROUTER_BASE_PORT`, etc.). Settings UI could expose advanced options.

---

## Protocol Compliance Check (Client ↔ kiri-router)

| Endpoint | Client Expectation | kiri-router Actual | Match |
|----------|-------------------|-------------------|-------|
| `GET /health` | `{"adapter": "kiri-router", ...}` | ✅ `routes.js:283-291` | ✅ |
| `GET /v1/models` | `{"object": "list", "data": [...]}` | ✅ `routes.js:227-251` | ✅ |
| `GET /account-limits` | `free_models[]` with `rate_hint` | ✅ `routes.js:253-281` | ✅ |
| `GET /v1/status` | counts only | ✅ `routes.js:296-310` | ✅ |
| `POST /v1/chat/completions` | OpenAI SSE `data: {...}\n\n` | ✅ `routes.js:77-165` | ✅ |
| `POST /v1/responses` | OpenAI Responses API | ✅ `routes.js:167-203` | ✅ |
| `POST /v1/systemone` | TypeSafe passthrough | ✅ `routes.js:205-225` | ✅ |
| Auth | `api_key="any"` accepted | ✅ `router_guide.py:14-15` | ✅ |
| Port scan | 8082..8092, check `adapter` | ✅ `run.py:2366-2415` | ✅ |
| `acquire_server` | `(server, port)` or `(None, port)` | ✅ `run.py:2398-2415` | ✅ |

---

## Turn Ledger Balance Verification

**Floor Rule** (`ai_credits.py:85-92`): `charged_steps(model_steps, text)` returns `max(model_steps, 1)` if `text` non-empty, else `model_steps`.  
- Text delivered → at least 1 step billed ✅  
- No text, model_steps=0 → 0 steps (hold rolled back) ✅  
- No text, model_steps>0 → model_steps billed ✅  

**Hold/Commit/Rollback** (`ai_credits.py:169-176`):  
- `steps <= 0` → `rollback` (refund hold) ✅  
- `steps > 0` with `tx` → `commit(tx, steps)` ✅  
- `steps > 0` without `tx` → `charge(steps)` ✅  

**Exception paths** (`ai_credits.py:194-214`):  
- `CancelledError` → `charged_steps(model_steps + current_step_delivered, text)` ✅  
- Other exceptions → same settlement ✅  

**Test coverage** (`tests/e2e/test_turn_ledger.py`):  
- Text-only: 1 step ✅  
- Tool round: 2 steps (model→tool, tool→answer) ✅  
- Stop mid-stream: 1 step (floor rule) ✅  
- Rejected approval: balances ✅  
- All candidates fail: 0 cost, hold refunded ✅  

**Verdict:** Ledger is balanced. No double-spend, refunds on failure work.

---

## Watchdog Status Publishing (Commit 5a81883)

**Commit claim:** "watchdog never published"  
**Code analysis:** `router_watchdog.py:194-197` calls `router._publish_status(status, port)` on transition. `router.py:51-74` writes to `state.ai_router_status` and `state.ai_router_port`.  
**Bug found:** Boot failure path (lines 145-160) does **not** call `_publish_status`. Watchdog starts, `ensure_router()` fails, exception caught, logged, loop continues with `_last = None`. First probe returns `("unavailable", None)`, compared against boot belief `("starting", None)` → transition detected → `_publish_status("unavailable", None)` called. **So it does publish, but only after first probe tick (up to 3s).** The "never published" refers to immediate boot failure not being surfaced. Finding #4 addresses this.

---

## Attach-at-Boot Race (Commit b710839)

**Code:** `router_watchdog.py:131-160` runs `ensure_router()` once at boot before loop. `router.py:244-331` uses `_router_lock` for port access. `router_engine.py:295-297` calls `engine.acquire_server()` which binds port.  
**Race window:** Two processes starting simultaneously could both pass `is_kiri_running()` check (run.py:2366-2383) and both try to bind. `acquire_server` handles this: `is_kiri_running` checks for "Local Console" marker; if both are ColabShell, second sees first's console → returns `(None, port)` → attaches. If foreign server, `port_open` detects → tries next port.  
**Verdict:** Race-free for same-app; foreign server handled by port scan.

---

## Tool Schema from Router (Commit a6881c4)

**Claim:** "tool schema derived from the router"  
**Reality:** Tools are defined in `src/services/ai_tools.py` (local schemas). `kani_backend.py:116-186` wraps them for step emission. The router's `/v1/models` returns `endpoint_type` but **no tool schemas**. The kiri-router injects its own placeholder tools (`PLACEHOLDER_TOOLS_ANTHROPIC`, `injectTools` in `convert.js`) for free-tier gating. ColabShell tools are client-side only (Colab exec, file ops, terminal).  
**Verdict:** Commit message misleading. Tool schemas are **not** derived from router; they are local. Router only provides model catalog + endpoint routing.

---

## Files Checked (No Issues Found)

- `src/core/channel.py` — build marker only, no router code
- `tests/services/test_ai_router*.py` — do not exist
- `tests/test_router_engine.py` — covered by `tests/services/test_router_engine.py`

---

## Recommendations Priority

1. **Fix #1, #3** — Core protocol bugs causing wrong router attachment
2. **Fix #4** — Watchdog boot failure visibility (commit 5a81883)
3. **Fix #2, #5** — Error handling / credit hold ordering
4. **Fix #6** — Verify path completeness
5. **Fix #8, #12** — UX and configurability
6. **Fix #7, #9, #10, #11** — Polish and performance
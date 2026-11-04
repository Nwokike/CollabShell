# CollabShell Master Findings — Baseline v2.1.2 → 76a9d4b

**Baseline:** tag `v2.1.2` (50fe98b) → HEAD `76a9d4b` (squashed commit of all changes since v2.1.2, **147 files, +31,759 / -1,392 lines**).

**How to read:** Each finding lists **Severity**, `path:line`, **one-line problem**, **fix**, and **source doc(s)**. Deduplicated across all 18 audit/dep/ref/research docs — e.g., the `page.update()`-in-`use_effect` finding appears in `audit-06`, `dep-01`, `dep-02`; kept once with all sources cited.

**Top 10 Critical Fixes First** table at top. Then Section A–H sorted Critical → High → Medium → Low → Info.

---

## TOP 10 CRITICAL FIXES (do these first)

| # | Severity | Location | Problem | Fix | Source |
|---|----------|----------|---------|-----|--------|
| 1 | **critical** | `src/services/ad_service.py:294-350` | `show_rewarded_interstitial` calls `on_close` (grants credits) for premium/desktop/no-ads — **free credits without ad** | Remove `on_close` call entirely when returning `False`; match DDGS exactly | audit-03 #1, ref-01 §1.6, research-02 §3.4 |
| 2 | **critical** | `src/services/license_service.py:73-81` | `status_refusal` includes HTTP 400 — a client bug revokes a valid license | Exclude 400: `return code in (402, 403, 404)` — DDGS deliberately excludes 400 | audit-03 #2, ref-01 §6.4 |
| 3 | **critical** | `src/services/kani_backend.py:354` | `_map_failure` treats `asyncio.TimeoutError` and `TimeoutError` identically; transport timeout becomes `RouterModelFailed` (walk) instead of marking router down | Only treat `asyncio.TimeoutError` from explicit `wait_for` as model-level; wrap in try/except raising custom `CandidateTTFBTimeout` | audit-01 #1 |
| 4 | **critical** | `src/services/kani_backend.py:538-566` | Stream iteration catches `StopAsyncIteration` but not `asyncio.CancelledError`; cancellation mid-stream skips `model_steps` accounting, floor rule may not fire | Wrap stream loop in `try/except asyncio.CancelledError`, increment `model_steps` if `delivered`, then re-raise | audit-01 #2 |
| 5 | **critical** | `src/services/colab/terminal_client.py:33-65` | Terminal uses wrong WebSocket endpoint (`/terminals/websocket/` vs library's `/colab/tty/`) — incompatible with upstream | Adopt `colab_cli.console.connect_console(session_state)` or fix endpoint to `/colab/tty` | audit-04 #1, dep-03 #18 |
| 6 | **critical** | `src/services/colab/session_ops.py:69-207` | `keep_alive` parameter removed without replacement; upstream has no built-in keep-alive | Document as breaking change; verify on-demand token heal (`load_session_fresh`) covers all paths | audit-04 #2 |
| 7 | **critical** | `src/app_shell.py:153,182,225,238,260` | `page.update()` inside `ft.use_effect` callbacks (`_sync_navigation_bar`, `_sync_assistant_fab`) — forbidden during render phase | Remove all `page.update()` calls from effects; observable state deps already trigger re-renders | audit-06 #1, dep-01 #1-2, dep-02 #1-2 |
| 8 | **critical** | `src/screens/session/__init__.py:281,289` | `page.update()` inside `ft.use_effect` callback (`_sync_fab` / `_cleanup_fab`) — forbidden during render phase | Remove both `page.update()` calls; FAB assignment picked up on next scheduled update | audit-06 #2, dep-01 #3, dep-02 #3 |
| 9 | **critical** | `.github/workflows/build-all.yml` | Android notification patch steps from commit 50b1fb1 are **missing** — `flet build apk/aab` will fail on Gradle desugaring error | Restore three-step sequence (first pass → `flet-notifications-patch` → second pass) for both APK and AAB jobs | audit-07 #1 |
| 10 | **critical** | `src/services/kani_backend.py:328-351` | `_build_engine` ignores passed `base_url` when falsy, re-calls `router.router_base()` causing redundant probe/embed per candidate | Remove fallback; require non-None `base_url` (caller guarantees this); raise `AIUnavailable` if None | audit-02 #1, ref-02 §6.1 |

---

## A. Ads / Credits / Premium / License

| # | Severity | Location | Problem | Fix | Source |
|---|----------|----------|---------|-----|--------|
| A1 | **critical** | `src/services/ad_service.py:294-350` | `show_rewarded_interstitial` grants credits via `on_close` for premium/desktop/no-ads — **free credits without ad** | Remove `on_close` call entirely when returning `False`; match DDGS exactly | audit-03 #1, ref-01 §1.6, research-02 §3.4 |
| A2 | **critical** | `src/services/license_service.py:73-81` | `status_refusal` includes HTTP 400 — client bug revokes valid license | Exclude 400: `return code in (402, 403, 404)` | audit-03 #2, ref-01 §6.4 |
| A3 | **high** | `src/screens/settings/premium_section.py:184-239` | Status row treats `"active"` as a lapse (no `_STATUS_COPY` entry) → paid users see free pitch on first load | Add `"active": ("Premium active", "...")` to `_STATUS_COPY` and ensure first branch catches it | audit-03 #3, ref-01 §2.1 |
| A4 | **high** | `src/services/premium_service.py:241-255` | `_notify_premium_unlocked` uses `page.platform.is_mobile()` which raises `FletUnsupportedPlatformException` on desktop | Use `page_has_ads(page)` helper (already in `premium_section.py:76-91`) or wrap in try/except | audit-03 #4, ref-01 §6.8 |
| A5 | **high** | `src/services/ad_service.py:133-165` | `get_banner_ad` imports `core.tokens` at runtime inside `try`; on desktop/web `BannerAd` ctor raises before import runs (fragile) | Move `from core import tokens` to module top, or use hardcoded 320×50 like DDGS | audit-03 #5, ref-01 §1.5, research-02 §3.4 |
| A6 | **medium** | `src/services/license_token.py:190-217` | `verify_token` adds scope validation, payload size limits, clock skew, `nbf`, `paid_through` type check — not in DDGS; breaks Worker compat if token structure changes | Decide: document as deliberate hardening + ensure Worker matches, OR align with DDGS | audit-03 #6, #14, ref-01 §6.5 |
| A7 | **medium** | `src/services/premium_service.py:105-134` | `reconcile` does not stamp `_last_reconcile_at` on early return (Play channel) → debounce loops forever on failure | Stamp clock in `finally` block or on all early returns | audit-03 #7 |
| A8 | **medium** | `src/services/credit_service.py:194-218` | `sweep_expired_holds` marks expired holds settled — prevents late `commit` from charging a legitimately long turn (>240s) | If intentional, document trade-off; else extend `ROLLBACK_SECONDS` or warn instead of auto-settling | audit-03 #9 |
| A9 | **medium** | `src/services/ad_service.py:346-350` | `show_rewarded_interstitial` calls `on_close` in `except` block — grants credits on error | Remove `on_close` call from error path; only call on actual ad close | audit-03 #10, research-02 §3.4 |
| A10 | **low** | `src/services/license_service.py:147-170` | `apply_cached_token` returns current `_unlocked` on storage read failure instead of propagating — storage failure on premium device drops to free until next read | Consistent with DDGS; log warning and keep current verdict (already done) | audit-03 #10 |
| A11 | **low** | `src/screens/settings/premium_section.py:315-340` | `_load_prices` uses global `_PRICES_ATTEMPTED` — stays `True` on fetch failure, never retries automatically until process restart | Set `_PRICES_ATTEMPTED = False` in `except` block (DDGS pattern) | audit-03 #11, ref-01 §2.2 |
| A12 | **low** | `src/services/usage_cache.py:43-51` | `is_fresh` returns `False` on `fetched_at` parse error — corrupt cache forces refetch storm | Log parse error once; treat missing/invalid `fetched_at` as age=0 (fresh) | audit-03 #13 |
| A13 | **low** | `src/services/ad_service.py:241-292` | `show_interstitial` returns `True` when `_pending_interstitial` set but gap not spent — caller may skip loading next ad | Document return value: "True if ad shown or queued to occur" (DDGS identical) | audit-03 #12 |
| A14 | **info** | `src/services/license_token.py` | Enhanced verification (strict SPKI, scope, size limits, clock skew, `nbf`, `paid_through` type) — more secure but diverges from DDGS | Document as deliberate hardening; ensure Worker updated to match | audit-03 #14, ref-01 §6.5 |
| A15 | **info** | `src/services/credit_service.py`, `src/services/ai_credits.py` | Credit ledger math matches DDGS: 3-phase settlement, soft metering, floor rule, idempotent commit, 240s auto-rollback | **Verified correct — no action needed** | audit-03 #16 |
| A16 | **info** | `src/services/usage_cache.py` | Cache logic correct: 24h TTL, read-through with fallback, writes only on fresh non-cached response | **Verified correct — no action needed** | audit-03 #17 |
| A17 | **info** | `src/components/credit_pill.py`, `src/components/usage_chip.py` | Reactive components match DDGS pattern (context + use_state + use_effect) | **Verified correct — no action needed** | audit-03 #18 |
| A18 | **info** | — | No dead code from "Notifications removed" / "Pro placeholder removed" — these commits not in CollabShell history | **Verified — no action needed** | audit-03 #19 |

---

## B. AI Assistant & Router Client

| # | Severity | Location | Problem | Fix | Source |
|---|----------|----------|---------|-----|--------|
| B1 | **critical** | `src/services/kani_backend.py:354` | `_map_failure` treats `asyncio.TimeoutError` and `TimeoutError` identically; transport timeout becomes `RouterModelFailed` (walk) instead of marking router down | Only treat `asyncio.TimeoutError` from explicit `wait_for` as model-level; wrap in try/except raising custom `CandidateTTFBTimeout` | audit-01 #1 |
| B2 | **critical** | `src/services/kani_backend.py:538-566` | Stream iteration catches `StopAsyncIteration` but not `asyncio.CancelledError`; cancellation mid-stream skips `model_steps` accounting | Wrap stream loop in `try/except asyncio.CancelledError`, increment `model_steps` if `delivered`, then re-raise | audit-01 #2 |
| B3 | **critical** | `src/services/kani_backend.py:328-351` | `_build_engine` ignores passed `base_url` when falsy, re-calls `router.router_base()` causing redundant probe/embed per candidate | Remove fallback; require non-None `base_url`; raise `AIUnavailable` if None | audit-02 #1, ref-02 §6.1 |
| B4 | **high** | `src/services/model_catalog.py:76-78, 247-251` | `"auto"` model handling inconsistent: `serving_model()` treats `"auto"` as empty, but `turn_candidates("auto")` prepends `"auto"` to pool — router's `auto` tried as candidate | In `turn_candidates`, if `wanted.lower() == "auto"`, treat as empty: `return pool` | audit-01 #3, audit-02 #2 |
| B5 | **high** | `src/services/kani_backend.py:347, 514-516` | `reasoning_effort` sent as kwarg but `api_type="chat_completions"` hardcoded — parameter ignored silently for chat completions | In `_build_engine`, read model's catalog entry and use `api_type_for(entry)` from lm-router; only send `reasoning_effort` when `api_type == "responses"` | audit-01 #4, audit-02 #11, dep-04 #3, #16 |
| B6 | **high** | `src/screens/assistant_view.py:730-743` | `run_metered_turn` passes empty string for `"Auto"` model; should pass `serving_model()` which resolves "auto" to actual model | Pass `model_catalog.serving_model()` instead of `state.ai_model` | audit-01 #5, #6 |
| B7 | **high** | `src/components/model_pill.py:179` | Pill spinner never stops when low/minimal models exist — `pickable_models()` falls back to low tier, never empty, but `discovering = not pickable_models()` | Change `discovering` to check `not model_catalog.catalog()` or `catalog_age() > threshold` | audit-01 #7, audit-02 #9 |
| B8 | **high** | `src/services/model_catalog.py:311-362` | `refresh_catalog` accepts invalid/empty router URL, returns stale catalog silently — no clear error | Require valid URL; raise `AIUnavailable` if router unreachable | audit-02 #2 |
| B9 | **high** | `src/services/router.py:138-168` | `probe_router` returns `("ready", port)` for attached foreign router without verifying `adapter == "kiri-router"` | Apply same adapter check as `_probe_existing_router` | audit-02 #3, ref-02 §6.1 |
| B10 | **medium** | `src/services/kani_backend.py:102-107` | `_CountingTokenizer` splits on whitespace — undercounts code tokens vs BPE; at small context windows causes mis-eviction or "prompt too long" | Use `tiktoken` with model mapping, or char-based heuristic (`len(text)//4`) | audit-01 #8, dep-04 #12 |
| B11 | **medium** | `src/services/ai_tools.py:188-190` | `on_step` callback called with `result`/`error` fields at start time (empty); UI gets extra empty fields | Call `on_step("start", {"name":..., "id":..., "args":...})` without `result`/`error` | audit-01 #9 |
| B12 | **medium** | `src/services/ai_service.py:190-196` | Pre-turn catalog refresh failure ignored; if catalog empty, `turn_candidates` returns empty → `AIUnavailable` with confusing message | On refresh failure, if catalog empty raise `AIUnavailable` with clear message; if stale but non-empty, warn and proceed | audit-01 #10 |
| B13 | **medium** | `src/services/cell_ai.py:105-107, 143-166` | In-cell AI `fix` action lacks code validation — model hedging with explanation produces cell with explanation as code | After `extract_code`, validate result is valid Python (`compile()`); if not, return empty string | audit-01 #11 |
| B14 | **medium** | `src/components/ai_step_output.py:46` | Button condition precedence bug: `tool_name == "_exec" and state in (...) or tool_name == "read_terminal" ...` parses incorrectly | Rewrite as `tool_name in ("_exec", "read_terminal") and state in ("running", "done")` | audit-01 #12 |
| B15 | **medium** | `src/services/kani_backend.py:329-334` | `_build_engine` hardcodes `api_type="chat_completions"` — ignores router catalog `endpoint_type`; `responses` models return empty replies | Fetch model's catalog entry; use `api_type_for(entry)` from lm-router's `catalog.py:57-67` | audit-01 #13, audit-02 #11, dep-04 #16 |
| B16 | **medium** | `src/services/router_watchdog.py:145-160` | Boot-time `ensure_router()` swallows all exceptions; router failure at boot leaves no visible error in UI (pill shows "Starting gateway…" indefinitely) | On boot failure, call `_publish_status("unavailable", None)` so UI shows honest state | audit-02 #4, ref-02 §6.2 |
| B17 | **medium** | `src/services/ai_credits.py:146` | `reserve(COST_STEP)` called before router reachability known; hold taken even if router unavailable (round-trip waste) | Move `reserve` after `run_turn` succeeds, or make `_ensure_router_for_turn` synchronous and call before reserve | audit-02 #5 |
| B18 | **medium** | `src/services/router.py:244-331` | `ensure_router(verify=True)` doesn't re-verify foreign router health after miss-TTL cleared (depends on B9 fix) | Fix B9; then verify path works correctly | audit-02 #6 |
| B19 | **low** | `src/services/router_engine.py:74-91` | Engine download retry uses fixed 1s backoff; no exponential backoff/jitter for transient failures | Exponential backoff with jitter: `await asyncio.sleep(1.0 * (2**attempt) + random.uniform(0, 0.5))` | audit-02 #7 |
| B20 | **low** | `src/screens/settings/ai_section.py:181-199` | "Reload" button only bumps revision; does not trigger actual re-probe | Call `router.ensure_router(verify=True)` in `_reload_router_status` and await it | audit-02 #8 |
| B21 | **low** | `src/services/model_catalog.py:107-119` | `adopt_default_model` persists model even when catalog empty (theoretical) | Assert model in `candidate_models()` before persisting | audit-02 #9 |
| B22 | **low** | `src/services/kani_backend.py:299-351` | `_build_engine` creates new `httpx.AsyncClient` per candidate — no connection pooling across candidate walk | Share single `httpx.AsyncClient` with connection pooling across candidates | audit-02 #11, dep-04 #13 |
| B23 | **low** | `src/core/constants.py:66-89` | Router constants hardcoded; no config file/env override for `ENGINE_URL`, `ROUTER_BASE_PORT`, etc. | Add `src/core/config.py` reading from `~/.collabshell/config.toml` and env vars | audit-02 #12 |
| B24 | **info** | `src/services/reasoning.py:43` | `_REASONING_KEYS` misses `reasoning_summary` used by OpenAI Responses API | Add `reasoning_summary` to tuple | audit-01 #14 |
| B25 | **info** | `src/services/ai_tools.py:795-798` | `tool_specs` derives JSON schema from signatures; for `list[dict]` returns `items: {type: "object"}` with no properties — valid but unhelpful | Use kani's `AIFunction.create_json_schema()` as single source of truth instead of hand-rolled | audit-01 #15, dep-04 #10, #11 |
| B26 | **info** | `src/screens/assistant_view.py:1035-1047, 1097-1105` | Duplicate `thought` event handling in `_emit` — second block dead code | Merge logic; remove dead block | audit-01 #16 |
| B27 | **info** | `src/services/ai_credits.py:235-240` | `_bump_revision` increments `credits_revision` but `_refresh_credits` reads balance directly — revision bump unused | Remove dead code or use revision for UI nudge | audit-01 #17 |
| B28 | **info** | `src/services/kani_backend.py:658-681` | Inconsistent thinking depth setting name: `ai_thinking` vs DDGS/lm-router `reasoning_effort` | Standardize on one name (prefer `reasoning_effort` for parity) | audit-01 #18 |
| B29 | **info** | `src/components/model_picker.py:91-169` | Model picker dialog duplicates pill logic (catalog refresh, provider config) | Reuse `model_catalog.refresh_catalog` and `pill_state` | audit-01 #19 |
| B30 | **info** | `src/services/ai_tools.py:55-69` | `_cell_has_plot` includes `image/gif` which Colab rarely emits — harmless | Remove `image/gif` or keep as-is | audit-01 #20 |

---

## C. Colab Sessions, Execution, Terminal, Idle/Keep-Alive

| # | Severity | Location | Problem | Fix | Source |
|---|----------|----------|---------|-----|--------|
| C1 | **critical** | `src/services/colab/terminal_client.py:33-65` | Terminal uses wrong WebSocket endpoint (`/terminals/websocket/` vs library's `/colab/tty/`) — incompatible with upstream | Adopt `colab_cli.console.connect_console(session_state)` or fix endpoint | audit-04 #1, dep-03 #18 |
| C2 | **critical** | `src/services/colab/session_ops.py:69-207` | `keep_alive` parameter removed without replacement; upstream has no built-in keep-alive | Document as breaking change; verify on-demand token heal covers all paths | audit-04 #2 |
| C3 | **high** | `src/services/colab/auth.py:29-107` | ADC auth provider not exposed to users; library supports both OAUTH2 and ADC | Add `auth_method` parameter ("oauth2" \| "adc") to auth service; expose "Use Application Default Credentials" in UI | audit-04 #3, dep-03 #1-3 |
| C4 | **high** | `src/services/colab/execution.py:69-70` | Default timeout changed 60s → 30s without migration path or config option | Make timeout configurable via settings (exists in `constants.py:DEFAULT_TIMEOUT=30`) and pass from UI | audit-04 #4 |
| C5 | **high** | `src/services/colab/files_ops.py:198-289` | Folder download reimplemented by running `zip` on VM; upstream has no such API — custom, fragile | Add checksum verification, streaming download, progress callback; consider upstream PR for `download_folder` | audit-04 #5, dep-03 #14 |
| C6 | **medium** | `src/services/colab/auth.py:75-158` | Token refresh logic duplicated from upstream instead of using library's `Credentials.refresh()` | Call `colab_cli.auth.get_credentials()` directly; use returned `AuthorizedSession` | audit-04 #6, dep-03 #1-3, #25 |
| C7 | **medium** | `src/services/colab/session_ops.py:69-207` | High-RAM shape only exposed via `high_mem` flag; library's `Shape` enum not fully surfaced | Current implementation correct per upstream logic; UI correctly hides switch for single-shape accelerators | audit-04 #7 |
| C8 | **medium** | `src/services/colab/vm_ops.py:8-35` | `mount_drive` hardcodes `drive.mount()` path; library has no Drive mount API — app reimplements via `exec_code` | Only way via Colab backend; acknowledge as custom implementation | audit-04 #8 |
| C9 | **medium** | `src/services/colab/usage_ops.py:42-58` | Usage fetch swallows all exceptions, returns `None` — no distinction between auth/offline/rate-limit | Catch `ColabRequestError`, inspect `status_code` to set `reason`: 401="signed-out", 429="rate-limited", 5xx="server-error", network="offline" | audit-04 #9, dep-03 #20 |
| C10 | **medium** | `src/services/colab/terminal_client.py:68-402` | Full custom WebSocket client (Tornado) for PTY; library uses `websocket-client` with raw TTY (`/colab/tty`) — different protocols | Document difference; app's PTY approach superior for interactive use; consider contributing upstream | audit-04 #1, dep-03 #19, research-02 §2 |
| C11 | **medium** | `src/services/colab/execution.py:201-318` | `drivefs_hook` duplicates library's `drivefs_hook`; app adds retry loop (improvement) but logic duplicated | Extract to shared utility; contribute retry loop upstream | audit-04 #11, dep-03 #11 |
| C12 | **medium** | `src/services/colab/session_ops.py:59-66, 120-148` | App creates new `State()` instance per call instead of using `colab_cli.common.state` singleton — redundant auth, token loads, race conditions | Import `from colab_cli.common import state` and use `state.client`, `state.store`, `state.history` everywhere | dep-03 #24, #25 |
| C13 | **medium** | `src/services/colab/execution.py:119-134` | Env var validation regex duplicated to avoid importing `execution.py` (pulls `termios` on Windows) | Extract `_parse_env_vars`/`_build_env_prelude` to shared non-POSIX module in library | dep-03 #23 |
| C14 | **low** | `src/services/colab/execution.py:399-410` | History logs `env_keys` only (not values) — deliberate divergence from upstream which logs prelude verbatim | Document as intentional security improvement | audit-04 #10 |
| C15 | **low** | `src/services/colab/files_ops.py:53-72` | Upload uses base64 encoding (correct per upstream) but no progress callback for large files | Upstream limitation; consider chunked upload if backend supports | audit-04 #11 |
| C16 | **low** | `src/services/colab/vm_ops.py:37-95` | `install_packages_impl`, `auth_gcp_on_vm_impl` duplicate library automation code strings | Call `commands.automation.install()` / `auth()` or use shared constants | dep-03 #16, #17 |
| C17 | **low** | `src/services/colab/terminal_client.py:97-144` | Terminal client re-reads session for token refresh — duplicates `load_session_fresh` logic | Call `State().get_session(session_name)` to get fresh token | dep-03 #29 |
| C18 | **info** | `src/components/hardware_picker.py:105-130` | Hardware picker correctly mirrors library's `Accelerator` enum and `HIGH_MEM_ONLY_ACCELERATORS` logic | **Verified correct — no action needed** | audit-04 #12 |
| C19 | **info** | `src/services/colab/execution.py:20-66` | Output mapper `_to_cell_output` preserves mime bundles (images, execution_count) — fixes v2.1.2 flattening bug | **Verified correct — no action needed** | audit-04 #13 |
| C20 | **info** | `src/services/colab/terminal_client.py` | Tornado WebSocket: manual ping/timeout logic; should use built-in `ping_interval`/`ping_timeout` | Use `websocket_connect(..., ping_interval=10, ping_timeout=5)`; remove manual logic | research-02 §2.1-2.2 |
| C21 | **info** | `src/services/colab/terminal_client.py` | Tornado reconnection logic doesn't respect close codes (1000/1001=don't retry; 1006/1011=retry) | Classify close codes in reconnection logic | research-02 §2.4 |
| C22 | **info** | `src/services/colab/terminal_client.py` | Sync `requests.post` in async context — wrapped in `asyncio.to_thread`; use `httpx.AsyncClient` for consistency | Replace with `httpx.AsyncClient.post`; share client for connection pooling | research-02 §1.1 |

---

## D. Notebook, Files, Scripts, Storage, Updates/Changelog

| # | Severity | Location | Problem | Fix | Source |
|---|----------|----------|---------|-----|--------|
| D1 | **critical** | `src/services/ipynb_converter.py:140-143` | `cells_to_ipynb` derives `execution_count` from outputs only, ignores cell-level `execution_count` — round-trip loses count when outputs empty | Prefer `cell.get("execution_count")` if present; fallback to derived | audit-05 #1, dep-05 #1 |
| D2 | **critical** | `src/core/changelog.py:54-66` | `notes_for()` fallback uses `max(CHANGELOG, key=_version_key)` but `_version_key` returns `(0,)` for unparseable versions — malformed version could become "newest" | Filter to parseable versions only: `max((v for v in CHANGELOG if _version_key(v)!=(0,)), key=_version_key)` or use `packaging.version.parse` | audit-05 #2, audit-06 #4 |
| D3 | **high** | `src/services/ipynb_converter.py:276-320` | `_outputs_from_ipynb` does not validate against nbformat schema; accepts arbitrary keys in `data`/`metadata` that nbformat would reject | Call `nbformat.validate()` after constructing notebook, or strip unknown MIME types to known set | audit-05 #3, dep-05 #2, #3 |
| D4 | **high** | `src/services/file_read.py:1-72` | No binary file detection; `errors="replace"` silently corrupts binary files; 12KB cap applied after decode (not byte-wise) | Read first 512 bytes binary, check for null bytes/high-bit ratio; if binary return `"[binary file]"`; apply byte-wise limit | audit-05 #4 |
| D5 | **high** | `src/services/storage_service.py:131-233` | Legacy migration in `load_notebook` writes per-tab file but NOT tab index sidecar — restored tabs appear in list but index stale | After migration, write index: `await self.save_tab_index(session_name, [{"id": notebook_id, ...}])` | audit-05 #5 |
| D6 | **medium** | `src/services/ipynb_converter.py:117-136` | `py_to_cells` uses `uuid.uuid4()` for cell IDs on every parse; breaks output preservation when toggling script↔notebook (match on type+source not ID) | Document IDs ephemeral; always use `merge_script_cells` for round-trips | audit-05 #6, dep-05 #6 |
| D7 | **medium** | `src/services/script_runner.py:1-69` | `build_run_file_payload` strips shebang but prepends prelude; line numbers in tracebacks shift by 4 — no mapping back to original file | Option 1: Send file as-is via `colab run /content/script.py`. Option 2: Include `# line N` directives. Option 3: Post-process traceback to subtract offset | audit-05 #7 |
| D8 | **medium** | `src/components/ansi_parser.py` | `_rich_color_to_hex` maps 256-color cube correctly but truecolor (24-bit) not handled — actually handled via `color.triplet` | **Correction: not a bug** — truecolor handled at line 37-39; 256-color cube math correct | audit-05 #8 (was false positive) |
| D9 | **low** | `src/services/update_service.py` | `version.json` deleted from git (`.gitignore`); `UpdateService` reads from GitHub raw URL only — no local fallback; CI must publish before builds ship | Keep version.json in repo (tracked) but CI updates as last step after artifacts uploaded; or add local cached copy fallback | audit-05 #9 |
| D10 | **low** | `src/core/constants.py:15-16` | `APP_VERSION = "2.2.0"`, `APP_BUILD_NUMBER = 13` but `version.json` untracked — version sync test passes vacuously, CI race possible | Track version.json in git; CI updates it as last step of release workflow | audit-05 #10 |
| D11 | **low** | `src/screens/files/text_editor.py:1-96` | `download_text_file` limit 512KB (`MAX_EDITABLE_TEXT_BYTES`); large files rejected with error, no streaming/partial read option | Allow opening large files in "view-only" mode (read first 512KB, show warning) or implement pagination | audit-05 #11 |
| D12 | **info** | `src/services/ipynb_converter.py:100-105` | `cells_to_py` correctly skips empty cells per percent-format spec; round-trip documented as lossy for empty cells | **Verified correct — no action needed** | audit-05 #12 |
| D13 | **info** | `src/screens/session/script_view.py` | New file (not in v2.1.2); correctly treats script as plain text document, not projected notebook | **Verified correct — no action needed** | audit-05 #13 |
| D14 | **info** | `src/services/ipynb_converter.py` | Missing `nbformat.validate()` before export/import; no `normalize()` to sanitize | Add validation calls at export/import boundaries | dep-05 #7.1 |
| D15 | **info** | `src/components/notebook_cell/output.py:30-52` | `parse_outputs_to_controls` handles only `image/png` and `text/plain` — ignores `text/html`, `image/jpeg`, `image/svg+xml`, `application/json`, `application/javascript`, `text/markdown`, `text/latex` | Add handlers for all standard MIME types | dep-05 #19, #3, #4 |
| D16 | **info** | `src/components/notebook_cell/output.py:8-53` | Stream `text` may be string or list (nbformat); code assumes string | Use `_join_text` helper from `execution.py` or `"".join(text) if isinstance(text, list) else str(text)` | dep-05 #20 |
| D17 | **info** | `src/services/colab/execution.py:24-66` | `_to_cell_output` drops `transient` field for `display_data` — needed for `update_display_data` correlation | Preserve `transient`: `entry["transient"] = out.get("transient", {})` | dep-05 #11 |
| D18 | **info** | `src/components/notebook_cell/actions.py:169-225` | `copy_output` doesn't handle `update_display_data` or `clear_output`; assumes `text/plain` for rich outputs | Add handlers; extract all MIME types | dep-05 #24 |

---

## E. UI / Flet 1.0.4 Lifecycle & Settings

| # | Severity | Location | Problem | Fix | Source |
|---|----------|----------|---------|-----|--------|
| E1 | **critical** | `src/app_shell.py:153,182,225,238,260` | `page.update()` inside `ft.use_effect` callbacks (`_sync_navigation_bar`, `_sync_assistant_fab`) — forbidden during render phase | Remove all `page.update()` calls from effects; observable state deps trigger re-renders | audit-06 #1, dep-01 #1-2, dep-02 #1-2 |
| E2 | **critical** | `src/screens/session/__init__.py:281,289` | `page.update()` inside `ft.use_effect` callback (`_sync_fab` / `_cleanup_fab`) — forbidden during render phase | Remove both `page.update()` calls; FAB assignment picked up on next scheduled update | audit-06 #2, dep-01 #3, dep-02 #3 |
| E3 | **high** | `src/hooks/use_keyboard_shortcuts.py:27-57` | Plain function (not `@ft.component`) calls `ft.on_mounted`; works only by accident when called from within a component render | Inline hook logic into `AppShell` or restructure as proper hook called directly from component | audit-06 #3, dep-01 #4, dep-02 #4 |
| E4 | **high** | `src/core/changelog.py:52-57,73` | `_version_key` returns `(0,)` on unparseable version; `max()` can return malformed version as "newest" changelog | Filter to parseable versions or use `packaging.version.parse` | audit-06 #4, audit-05 #2 |
| E5 | **high** | `src/core/notifications.py` + `version.json` | `version.json` claims "Notifications system removed entirely" but `flet_notifications 0.1.4` installed and `src/core/notifications.py` implements SnackBar notifications | Correct release notes: "OS-level notifications removed" or "flet_notifications dependency removed" | audit-06 #5, research-02 §3 |
| E6 | **medium** | `src/screens/onboarding/__init__.py:119` | `page.update()` in handler that also mutates observable state (`state.onboarding_done = True`) — redundant, triggers double render | Remove `page.update()` at line 119; observable mutation sufficient | audit-06 #6, dep-01 #5, dep-02 #5 |
| E7 | **medium** | `src/components/usage_chip.py:51-54` | `ft.use_effect` for one-shot async load with deps; missing cleanup for in-flight task; `page_run_task` swallows `RuntimeError` | Use `ft.on_mounted` for initial load; separate `use_effect` with deps only for reload logic | audit-06 #7, dep-01 #6, dep-02 #6 |
| E8 | **medium** | `src/screens/files/__init__.py:122-124` | `ft.use_effect` with `[current_path, session_name]` deps calls `page.run_task(_fetch)` — missing cleanup for in-flight task on unmount/dep change | Return cleanup function that cancels previous task using `ft.use_ref` | audit-06 #8, dep-01 #7, dep-02 #7 |
| E9 | **medium** | `src/components/env_dialog.py:95-99,105-125` | `_rebuild()` calls `page.update()` from inside render body; `on_save`/`_on_clear` call `page.update()` after `page.pop_dialog()` | Remove `page.update()` from `_rebuild()`; rely on parent observable state write for repaint | audit-06 #9, dep-01 #9 |
| E10 | **medium** | `src/components/hardware_picker.py:43,47,82,147` | Event handlers call `e.control.page.update()` directly — bypasses component system change detection | Replace with observable state mutations (write to `state.default_gpu` etc.) | audit-06 #10, dep-01 #10 |
| E11 | **low** | `src/app_shell.py:135` | `ft.on_mounted(_register_global_shortcuts)` — `on_mounted` fires after mount; shortcuts router registration should use `use_effect(fn, [])` for consistency | Capture cleanup from `shortcuts_router.register()`; use `on_mounted` + `on_unmounted` | audit-06 #11, dep-01 #9, dep-02 #9 |
| E12 | **low** | `src/screens/session/__init__.py:108` | `ft.on_mounted(_register_session_shortcuts)` — same as above | Capture cleanup; use `on_mounted` + `on_unmounted` | audit-06 #12, dep-01 #10, dep-02 #10 |
| E13 | **low** | `src/core/theme.py:184-192` | `brand_color()` reads `page.theme.color_scheme.primary` at render time — not observable, won't trigger repaint on theme change | Make `brand_color` read from observable state (`state.theme_mode`, `state.theme_revision`) | audit-06 #13, dep-01 #12 |
| E14 | **low** | `src/core/stdin_hook.py:52-53,101,104,176,179` | Multiple `page.update()` calls inside dialog rendering and event handlers; `input_event.wait(timeout=300)` blocks event loop thread up to 5 min | Use async/await throughout; show dialog, `await` result, don't block with `threading.Event.wait()` | audit-06 stdin_hook |
| E15 | **info** | `src/screens/session/notebook_view.py:363,417` | Correct `on_mounted` + `on_unmounted` pattern inside component | **Verified correct — reference pattern** | audit-06 #15, dep-01 #11, dep-02 #11 |
| E16 | **info** | `src/components/notebook_cell/__init__.py:121` | Correct `ft.use_effect(_focus_effect, [focus_token])` with dependency array | **Verified correct — reference pattern** | audit-06 #16, dep-01 #12, dep-02 #12 |
| E17 | **info** | `src/components/credit_pill.py:92` | Correct `ft.use_effect(lambda: page.run_task(_load), [revision, is_premium])` | **Verified correct — reference pattern** | audit-06 #17, dep-01 #13, dep-02 #13 |
| E18 | **info** | `src/screens/settings/account_section.py:69-79` | Module-level `_USAGE` state survives parent rebuilds; `_USAGE_VIEW` publishes live refs — correct pattern per DDGS/ktv-player | **Verified correct — reference pattern** | audit-06 #18 |
| E19 | **info** | `src/screens/settings/__init__.py:59` | `SettingsScreen` correctly `@ft.component` — test enforces this | **Verified correct** | audit-06 #19 |
| E20 | **info** | `src/screens/settings/ai_section.py` | No router URL box (removed per DDGS parity); no assistant switches (removed per owner directive); credits line reads observable state correctly | **Verified correct** | audit-06 #20 |
| E21 | **info** | — | Flet 1.0.4 options not exposed: `ft.on_unmounted`, `ft.use_callback`, `ft.use_memo`, `Component.memoized`, `page.wait_until_visible`, `Control.is_isolated()`, `Observable` auto-wrapping, `Animation`, `Theme.extensions`, `Service` base class, `DataChannel`, `PubSubHub` | Consider adopting to simplify code or fix violations above | dep-01 §4 |

---

## F. Build / CI / Packaging / Config

| # | Severity | Location | Problem | Fix | Source |
|---|----------|----------|---------|-----|--------|
| F1 | **critical** | `.github/workflows/build-all.yml` | Android notification patch steps from commit 50b1fb1 missing — `flet build apk/aab` fails on Gradle desugaring error | Restore three-step sequence (first pass → `flet-notifications-patch` → second pass) for both APK and AAB jobs | audit-07 #1 |
| F2 | **high** | `README.md:13,34` | Stale references: Flet 0.86 badge (now 1.0.4), ARMv7 APK download link (dropped in 755b201) | Update badges to `Flet_1.0.4` and `Python-3.13`; remove ARMv7 row | audit-07 #2 |
| F3 | **high** | `pyproject.toml:71-72` | Dev dependencies unpinned: `pytest`, `ruff` — no versions, reproducible CI at risk | Pin to known-good: `pytest==8.3.3`, `ruff==0.6.9` | audit-07 #3 |
| F4 | **medium** | `.github/workflows/build-all.yml:24` | `UV_PYTHON: "3.14"` — Python 3.14 doesn't exist yet (3.13 current); will fail when 3.14 lands | Use `3.13` (or `3.12` LTS) in all 4 places: `UV_PYTHON`, `python-version`, `requires-python`, `.python-version` | audit-07 #4, #5, #8, #9 |
| F5 | **medium** | `.python-version` | Pins `3.14` — same issue | Change to `3.13` | audit-07 #5 |
| F6 | **medium** | `tests/services/test_version_sync.py:138-150` | `test_the_installed_version_satisfies_each_pin` assumes local env has `jupyter-kernel-client` installed; fails in clean CI before `uv sync` | Mark as `@pytest.mark.integration`, read from `uv.lock`/`pyproject.toml`, or skip gracefully | audit-07 #6 |
| F7 | **low** | `settings-debug.log` | Committed debug artifact — contains local Windows paths (`C:\Users\nwoki\.zcode\...`) but no secrets | Remove from git (add to `.gitignore` if needed for local debugging) | audit-07 #7 |
| F8 | **low** | `.github/workflows/build-all.yml:9` | Workflow defaults `build_version: "2.2.0"` / `build_number: "13"` — drift risk if not updated with release | Consider reading from `pyproject.toml` at workflow start, or document manual dispatch must override | audit-07 #8 |
| F9 | **info** | `pyproject.toml:6` | `requires-python = ">=3.14"` — should be `>=3.13` or `>=3.12,<3.14` until 3.14 exists | Update to `>=3.13,<3.15` or `>=3.12,<3.14` | audit-07 #8, #9 |
| F10 | **info** | `.github/workflows/build-all.yml:85,127` | Python version hardcoded to `'3.14'` in `actions/setup-python@v5` — should use `${{ env.UV_PYTHON }}` | Use `${{ env.UV_PYTHON }}` for consistency | audit-07 #9 |
| F11 | **info** | `.gitignore:36` | `version.json` correctly ignored; test handles missing file gracefully | **Verified correct — no action needed** | audit-07 #10, #11 |
| F12 | **info** | `scripts/check_elf_alignment.py` | ELF 16KB alignment gate present and correct — no regression | **Verified correct — no action needed** | audit-07 #11 |
| F13 | **info** | `.github/workflows/build-all.yml:175-178` | Windows icon step restore (d2e498b) present | **Verified correct** | audit-07 cross-ref |
| F14 | **info** | `.github/workflows/build-all.yml` | Pre-release semantics present: `IS_PRERELEASE=true`, `MAKE_LATEST=false` | **Verified correct** | audit-07 cross-ref |

---

## G. Dependency Upgrades & Unexposed Options

| # | Severity | Location | Problem | Fix | Source |
|---|----------|----------|---------|-----|--------|
| G1 | **high** | `pyproject.toml` / venv | `flet 1.0.4` → `1.0.5` available: Wakelock service stabilized, lifecycle events | Upgrade to 1.0.5; test Wakelock for terminal sessions | research-02 §2, dep-02 summary |
| G2 | **high** | `pyproject.toml` / venv | `flet_notifications 0.1.4` → `1.1.0-dev` available: adds `start_foreground_service()` for Android background keep-alive | If background keep-alive needed, upgrade when stable (1.1.0) and add `flet-notifications-patch` to CI | research-02 §2, §4.1, dep-02 §2 |
| G3 | **medium** | `pyproject.toml` / venv | `flet_ads 1.0.4` → `1.0.5` available: Google Mobile Ads SDK update; **no `RewardedAd` control** | Upgrade; but rewarded ad pattern unchanged — still no `on_reward` event | research-02 §2, §3.1, dep-02 §1 |
| G4 | **medium** | `pyproject.toml` / venv | `flet_terminal 0.3.9` → `0.4.2` available: Terminal search, themes, shortcuts, `MobileTerminal` composite | Upgrade; test new features (search bar, extra keys) | research-02 §2, dep-02 §4 |
| G5 | **medium** | `pyproject.toml` / venv | `flet_cli 1.0.4` → `1.0.5` available: Build improvements | Low priority; upgrade with flet | research-02 §2, dep-02 §6 |
| G6 | **medium** | `pyproject.toml` / venv | `google-colab-cli 0.7.4` → `0.7.5` available: maintenance release, no functional changes | Upgrade when convenient | research-01 §1 |
| G7 | **low** | `src/services/ad_service.py` | `flet_ads` lacks `RewardedAd` control — only `InterstitialAd` exists; no `on_reward` event | Wait for upstream `RewardedAd` or implement server-side reward verification; do not use current `show_rewarded_interstitial` for production rewards | research-02 §3.3, §3.4, dep-02 §1 |
| G8 | **low** | `src/services/colab/terminal_client.py` | `tornado` built-in `ping_interval`/`ping_timeout` not used; manual ping/timeout logic reimplemented | Use `websocket_connect(..., ping_interval=10, ping_timeout=5)` | research-02 §2.1-2.2 |
| G9 | **low** | `src/services/colab/terminal_client.py` | `requests` sync HTTP in async context; `httpx` already used elsewhere | Replace with `httpx.AsyncClient.post`; share client for pooling | research-02 §1.1, dep-06 #1 |
| G10 | **low** | `src/components/ansi_parser.py` | `rich` custom color maps duplicate `Color.from_ansi()` logic | Use `Color.from_ansi(n).triplet` for 16-color and 256-color | research-02 §3.2, dep-06 #3 |
| G11 | **info** | `src/screens/session/terminal_panel.py` | `flet_terminal` `ExtraKeysBar` (on-screen keys) and `TerminalSearchBar` not used | Could add for mobile UX (hardware keyboard absent) | dep-02 §4, dep-06 §4 |
| G12 | **info** | `src/services/license_token.py` | Pure-Python ECDSA P-256 verification (no `cryptography` dep) — correct for verify-only, side-channel resistance not required | **Verified correct — no action needed** | dep-06 §5, audit-03 #6, #14 |
| G13 | **info** | `src/services/colab/` | Multiple files reimplement `colab_cli` commands instead of calling library functions (`colab new`, `sessions`, `stop`, `restart-kernel`, `exec`, `ls/upload/download/rm`) | Adopt singleton `state` from `colab_cli.common`; replace reimplemented commands with library calls | dep-03 summary, #24-#25 |
| G14 | **info** | `src/services/kani_backend.py` | kani options not exposed: `desired_response_tokens`, `always_included_messages`, `retry_attempts`, `auto_retry`, `auto_truncate`, `enabled`, `after`, `json_schema` override, `api_type` selection, `organization`, `headers`, real `tokenizer`, `temperature`/`top_p`/etc hyperparams | Consider exposing via Settings for power users | dep-04 §4 |
| G15 | **info** | `src/components/notebook_cell/` | nbformat options not exposed: `validate()`, `normalize()`, `convert()`, `new_output()`, `output_from_msg()` | Add validation at export/import boundaries | dep-05 §7.1 |
| G16 | **info** | `src/services/colab/` | `jupyter_client` options not exposed: `kernel_info()`, `complete()`, `inspect()`, `history()`, `comm_info()`, `get_variable()` | Could enable autocomplete, introspection, variable explorer | dep-05 §7.2 |
| G17 | **info** | — | `watchdog` not used — no file system watching in app | Could watch `.ipynb` files for external edits | dep-05 §7.4 |

---

## H. Reference-App Patterns to Adopt (DDGS Ads/Wallet/Premium; Router Protocol Checklist)

| # | Severity | Pattern Area | DDGS Reference | CollabShell Gap | Action |
|---|----------|--------------|----------------|-----------------|--------|
| H1 | **critical** | Rewarded ad grants credits without showing ad | `ad_service.py:305-312` (returns `False`, no `on_close`) | Calls `on_close` for premium/desktop/no-ads → grants free credits | **Fix A1** — remove `on_close` call when returning `False` |
| H2 | **critical** | `status_refusal` excludes HTTP 400 | `license_service.py:73-82` | Includes 400 → client bug revokes valid license | **Fix A2** — exclude 400 |
| H3 | **high** | Premium card `_STATUS_COPY` has `"active"` entry | `sections_premium.py:51-56` | Missing `"active"` → free pitch shown to subscribers on first load | **Fix A3** — add `"active"` entry |
| H4 | **high** | `_notify_premium_unlocked` uses `page_has_ads` helper | `premium_service.py:63-80` | Calls `page.platform.is_mobile()` → crashes on desktop | **Fix A4** — use helper |
| H5 | **high** | Banner ad dimensions hardcoded (320×50) | `ad_service.py:124-128` | Imports `core.tokens` at runtime inside try → fragile | **Fix A5** — use constants |
| H6 | **medium** | License token verification — align with DDGS or document hardening | `license_token.py` (no scope/size/clock/nbf checks) | Extra validations (scope, size, skew, nbf, paid_through type) — compat risk | **Decide A6** — document or align |
| H7 | **medium** | `reconcile` stamps `_last_reconcile_at` on all early returns | `premium_service.py:267` | Play channel early return doesn't stamp → debounce loops forever | **Fix A7** — stamp on all returns |
| H8 | **low** | `_PRICES_ATTEMPTED` reset on catalog fetch failure | `sections_premium.py:176` | Stays `True` on failure → never retries automatically | **Fix A11** — reset in `except` |
| H9 | **low** | `is_fresh` handles corrupt `fetched_at` gracefully | N/A (DDGS no cache layer) | Parse error → `False` → refetch storm | **Fix A12** — treat as fresh |
| H10 | **critical** | Rewarded interstitial never calls `on_close` on error | `ad_service.py:326-333` | Calls `on_close` in except block → grants credits on error | **Fix A9** — remove `on_close` from error path |
| H11 | **high** | Router client: verify `adapter == "kiri-router"` on ALL `/health` probes | `ref-02 §7` checklist | Missing on held port probe (`probe_router`) | **Fix B9** |
| H12 | **high** | Router client: reserve after router reachability confirmed | `ref-02 §7` checklist | `reserve()` called before `_ensure_router_for_turn()` | **Fix B17** |
| H13 | **high** | Router client: boot failure → publish `"unavailable"` immediately | `ref-02 §7` checklist | Watchdog swallows exception, no `_publish_status` | **Fix B16** |
| H14 | **high** | Router client: handle `429` as model-level (walk) vs connection-level (blackout) | `ref-02 §7` checklist | `_map_failure` needs distinction | **Fix B1** |
| H15 | **high** | Router client: respect `Retry-After: 2` on `503` (cold isolate) | `ref-02 §7` checklist | Not implemented | Add handling in `_map_failure` |
| H16 | **high** | Router client: use public model ID from catalog (gateway rewrites in stream) | `ref-02 §7` checklist | `kani_backend` should trust gateway rewrite | Verify |
| H17 | **high** | Router client: never call `/v1/responses` or `/v1/systemone` for chat | `ref-02 §7` checklist | `_build_engine` hardcodes `chat_completions` | **Fix B15** |
| H18 | **high** | Server lifecycle: scan 8082..8092 on startup, adopt existing Kiri router | `ref-02 §7` checklist | Implemented correctly | **Verified** |
| H19 | **high** | Server lifecycle: embed own `run.py` only if no Kiri router found | `ref-02 §7` checklist | Implemented correctly | **Verified** |
| H20 | **high** | Server lifecycle: never stop a foreign router | `ref-02 §7` checklist | `stop_router()` checks `_router_server` | **Verified** |
| H21 | **high** | Watchdog: probe `/health` every 3s/30s, publish on transition | `ref-02 §7` checklist | Implemented correctly | **Verified** |
| H22 | **high** | Ledger: track `model_steps` = count of ASSISTANT stream rounds only | `ref-02 §7` checklist | Implemented correctly in `kani_backend` | **Verified** |
| H23 | **high** | Ledger: apply floor rule `max(model_steps, 1)` if any text delivered | `ref-02 §7` checklist | Implemented correctly in `ai_credits.charged_steps` | **Verified** |
| H24 | **high** | Ledger: settle on ALL paths (success, cancel, exception, connection drop) | `ref-02 §7` checklist | Implemented correctly in `ai_credits._settle` | **Verified** |
| H25 | **high** | Ledger: idempotent commit (guard against double-settle) | `ref-02 §7` checklist | Implemented correctly in `credit_service.commit` | **Verified** |
| H26 | **high** | Ledger: sweep holds >240s, mark settled so late commit no-ops | `ref-02 §7` checklist | Implemented correctly (trade-off documented) | **Verified** |
| H27 | **high** | Model catalog: filter `status=="active"` AND `endpoint_type` starts with `chat.completion` | `ref-02 §7` checklist | Implemented correctly in `model_catalog._is_chat_row` | **Verified** |
| H28 | **high** | Model catalog: rank tier→latency→id; `auto` eligible when active, goes last | `ref-02 §7` checklist | Implemented correctly in `candidate_models`/`turn_candidates` | **Verified** (except B4) |
| H29 | **high** | Model catalog: circuit breaker skip failed model for 300s | `ref-02 §7` checklist | Implemented correctly | **Verified** |
| H30 | **high** | Model catalog: display gateway's `rate_hint.label` verbatim — never synthesize | `ref-02 §7` checklist | Implemented correctly | **Verified** |
| H31 | **high** | Streaming: consume `delta.content` for text, `delta.reasoning`/`delta.reasoning_content` for thinking | `ref-02 §7` checklist | Implemented via `ThoughtTap` + `on_thought` | **Verified** |
| H32 | **high** | Streaming: per-candidate timeouts 12s first token, 20s dead air | `ref-02 §7` checklist | `CANDIDATE_TTFB_S=12`, `CANDIDATE_READ_S=20` | **Verified** |
| H33 | **high** | Streaming: on stop mid-stream, bill floor rule, don't walk candidates | `ref-02 §7` checklist | `stopped_mid_stream` flag + floor rule | **Verified** |

---

## Files Verified (Read-Only, No Changes Needed)

These files were audited and found correct per their respective docs:

- `src/services/conversation_service.py` — Pure persistence, no AI library usage (dep-04)
- `src/services/ai_quick.py`, `src/services/cell_ai.py` — Thin wrappers over `ai_credits`/`ai_service` (dep-04)
- `src/services/model_catalog.py` — Router catalog logic, ranking, circuit breaker (dep-04, ref-02)
- `src/services/ai_credits.py`, `src/services/credit_service.py` — Metering math matches DDGS exactly (audit-03 #16, ref-02)
- `src/services/usage_cache.py` — Cache logic correct (audit-03 #17)
- `src/components/credit_pill.py`, `src/components/usage_chip.py` — Reactive patterns match DDGS (audit-03 #18)
- `src/screens/settings/account_section.py` — Module-level state pattern correct (audit-06 #18)
- `src/screens/session/notebook_view.py` — Correct `on_mounted`/`on_unmounted` (audit-06 #15)
- `src/components/notebook_cell/__init__.py` — Correct `use_effect` with deps (audit-06 #16)
- `src/screens/session/terminal_panel.py` — `flet_terminal` usage correct (dep-02 §4, dep-06 §4)
- `src/components/hardware_picker.py` — Correctly mirrors library enums (audit-04 #12)
- `src/services/colab/execution.py:20-66` — Output mapper preserves mime bundles (audit-04 #13)
- `tests/test_checkout_watcher.py` — Behavior matches DDGS (audit-03 #15)
- `scripts/check_elf_alignment.py` — ELF 16KB gate intact (audit-07 #11)
- `.gitignore` — No `__pycache__` or `*.pyc` tracked (audit-07 #12)

---

*Generated by consolidating 18 docs: `audit-01`..`07`, `dep-01`..`06`, `ref-01`..`02`, `research-01`..`03`. Baseline: `v2.1.2` (50fe98b) → `76a9d4b` (147 files, +31759/-1392).*
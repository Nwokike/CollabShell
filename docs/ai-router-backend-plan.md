# CollabShell AI — router ownership, backend, and the plan to finish it

**Status: the assistant cannot start.** Not "is slow" or "needs polish" — there
is no code path that starts a model. This is why nothing has felt like
progress: every milestone so far built UI on top of a router the app assumes
someone else is already running.

---

## 1. The root cause, stated plainly

CollabShell's `ai_service.py` registers a mirascope provider against a URL the
user types into Settings:

```
src/services/ai_service.py:26   from mirascope import llm
src/services/ai_service.py:51   provider = llm.register_provider("openai", scope="openai/", ...)
src/services/ai_service.py:209  @llm.call(model_id, tools=tools)
```

There is no code anywhere in the repo that:
- downloads or embeds a router engine,
- probes a port to find one already running,
- supervises, health-checks, or stops a router,
- reports its status to the UI.

Both reference apps do all five. So CollabShell's assistant works only if the
user has already started a Kiri router by hand on 8082 — which the user has not
done, and was never told to do. The "AI candidate auto failed
(ConnectionError)" line in the log is the whole story: nothing was listening
because nothing ever tried to listen.

## 2. What the two references actually do

### Router lifecycle — identical in both

**DDGS** (`src/services/ai_service.py`):
- `_probe_existing_router()` (`:230`) scans `8082..8092`, `GET /health`, and
  accepts a port only when `response.json().get("adapter") == "kiri-router"`.
  So the user's *own* router is found and reused, not shadowed.
- `ensure_router(verify=)` (`:294`): returns a known port; with `verify=True`
  it health-checks before trusting it, so a stale port is forgotten and
  re-attached rather than returned forever.
- If the scan finds nothing: `load_engine()` then `engine.acquire_server(base,
  span)` (`:347`), served on a `threading.Thread(daemon=True)`. The engine is
  `run.py` **fetched live from router.kiri.ng on every cold start** and cached
  (`engine.py:1-13`) — never vendored, because upstream changes constantly and
  a bundled snapshot would silently shadow it.
- `stop_router()` (`:416`) stops **only an embedded** server, never the user's
  own.
- Status is observable and only written on a real change
  (`_publish_status`, `:383`): `ready` / `stopped` / `unavailable` /
  `starting`. The picker renders an honest label for each, so an empty catalog
  during discovery reads as "still starting", not "broken app".
- A missed probe is memoised for `PROBE_MISS_TTL` so a 3-second watchdog does
  not pay a serial 11-port scan on every tick.

**LM Router** (`src/services/engine.py`, `services/agent.py`):
- Same `run.py`-fetched-live-and-cached engine, with one extra rule stated in
  its docstring: it is **sync urllib + threads on purpose, because it must
  never share an event loop with Flet or kani**.
- Kani turns run on a single `BlockingPortal` — its own thread and its own
  asyncio loop. That keeps kani's single-loop lock invariant intact while Flet
  stays on its own loop. Stop is `Future.cancel()` mapped to a task-group
  cancel; the async-for is never broken from outside.

### Agent loop — kani in both, mirascope in CollabShell

**DDGS** (`src/services/kani_backend.py:1-45`) is explicit that the agency is
borrowed, not rebuilt:

> "kani[openai] speaks the OpenAI wire our embedded router uses; NO MCP, never
> in scope; the gateway fallback is DROPPED — the router is the single AI
> source. `chat_agent` keeps every outer contract it always had (emit
> protocol, credits per model step, RELATED/citations, the approval gate, step
> rows); this module owns the turn mechanics: engine construction, tool
> serialization and the `full_round` iteration."

It also pins the billing rule: **one billable step == one model stream** —
kani yields a `StreamManager` per model round and a `DummyStream` per tool
result, so only model rounds reserve and charge.

**LM Router** (`services/agent.py`) uses `kani.ChatMessage` / `Kani` /
`OpenAIEngine` with a documented turn protocol: `on_delta`, `on_tool`,
`on_done` (only the final reply), `on_error`, `on_thought`, `on_settled`
(exactly once per turn even if a callback raised).

**CollabShell** built its loop on **mirascope[openai]** instead. That is the
one place it diverges from both references, and from the standing directive in
project memory: *"kani[openai] owns the agent loop; never hand-roll AI wire
code."*

---

## 3. The plan

Five phases, ordered so the app is usable after the first and each later phase
is independently valuable. Phases 1–2 are the ones that make the assistant
work at all.

### Phase 1 — Own the router *(unblocks everything)*
Port DDGS's lifecycle into `src/services/router.py`, adapting CollabShell's
own idioms:
- `_probe_existing_router()` over `8082..8092`, accepting only
  `adapter == "kiri-router"` on `/health`, with the miss-TTL memo.
- `ensure_router(verify=)`, `stop_router()` that never kills a foreign
  instance, `shutdown()` wired to `atexit` next to the existing session
  cleanup in `main._register_lifecycle_handlers`.
- Engine fetch from `router.kiri.ng`, cached under the durable data dir via
  `resolve_storage_dir()`, imported with `importlib.util` under a stable module
  name. Never vendored.
- Sync urllib + threads for the engine path only — it must not share the
  event loop with the model calls (`engine.py`'s rule, which the anyio study
  already established).
- `state.ai_router_status` / `ai_router_port` written only on real change, and
  rendered as honest labels everywhere the model is named.
- `autouse` boot call so no turn ever pays the probe cost.

**Done means:** a fresh install, no router running, tap Send → the router
starts, the model answers, and the pill says "Auto" instead of "Offline".

### Phase 2 — Move the agent loop onto kani
Replace the mirascope loop with kani[openai] inside a `BlockingPortal`,
keeping CollabShell's existing outer contracts intact (the emit protocol, the
per-step metering, the approval gate, the step rows, the candidate walk).
- Port `kani_backend.py`'s structure, not just its imports: engine
  construction, tool serialization, `full_round` iteration.
- Preserve what CollabShell already did well and that DDGS also does:
  client-ranked candidates with `auto` last, `max_retries=0`, observable
  candidate walking on failure.
- Preserve the credit floor rule by counting **model streams**, not tool
  rounds — the DummyStream distinction.
- Cancellation at manager boundaries only; never break an async-for from
  outside.
- `@llm.tool`-decorated tools → kani's tool shape. The 15 tools and the
  approval gate carry over; only the wrapper changes.

**Done means:** `tests/services/test_ai_service.py` (today the mirascope
contract) is replaced by a kani contract with the same pins — the model step
count, the stop mid-stream bill, the approval gate, the candidate walk.

### Phase 3 — Router status is a first-class surface
- The header pill's four states map exactly to `probe_router()`'s four
  statuses, with DDGS's copy ("Starting router…", "Offline" + "Start router").
- Settings shows the router URL, status, and a "Start router" action.
- Empty catalog offers *Refresh*, never a bare "No model".

### Phase 4 — Tool set parity
- Audit the 15 tools against kani's tool shape; keep the docstring-as-visible
  instruction pattern both references use.
- `mount_drive` / `auth_gcp` stay out, as now.
- Tool results carrying images survive the port.

### Phase 5 — E2E verification, on a real router
Today the assistant has never completed a turn in this environment. Phase 5 is:
a scripted turn against the embedded router (start, one text reply, one tool
round, a stop mid-stream, a rejected approval) asserting credits settled
correctly each time. Without it we are still shipping unrun code.

---

## 4. Decisions that are yours

1. **kani vs mirascope.** Both references and the standing directive say kani.
   CollabShell has ~450 lines on mirascope plus a test file that pins seven
   mirascope facts. Switching is the honest path but is real work; staying on
   mirascope keeps today's code and diverges from both references.
2. **Embed the router, or require an external one?** Both references embed.
   Embedding is what makes the assistant work out of the box; requiring an
   external one is less code but leaves the app unusable until the user
   installs and runs something else.
3. **Fixed 8082, or the 8082–8092 probe?** The probe finds the user's own
   router too and avoids double-embedding, which DDGS hit in the field. I
   recommend the probe.

My recommendation, if you want the shortest path to a working assistant:
**Phase 1 now** (it is self-contained and changes nothing else), then Phase 2,
then Phase 5 as the gate before any release.

---

## 5. On the Settings screen — I could not reproduce it

You have reported this three times and I have twice claimed a fix. This time I
verified it mechanically instead of by eye:

- **936** attribute references across `src/screens/settings/*.py`
  (`tokens.*`, `constants.*`, `AppColors.*`) — every one resolves.
- **480** Flet constructor keyword arguments — every one is a real parameter
  on the installed class, checked against `.venv/Lib/site-packages/flet/`.
- Every `ft.Page` method the settings path calls exists; no
  `set_clipboard`/`show_snack`-class misuse remains.
- No coroutine is left unawaited in any settings file.
- `SettingsScreen` renders clean with real `StorageService`,
  `KiriLicenseService`, `CreditService`, and `PremiumService`, and the
  try/except I added shows an error card naming the section if one ever fails.
- `pytest tests/screens/` is green.

I also checked the logging path, since you said nothing appears in your
terminal: `state.logtostderr` defaults to `True` and adds a stderr handler at
`DEBUG` level, so a crash *would* print. The absence of any traceback in your
terminal is consistent with the screen not crashing on this commit.

The most likely explanation is that the app you are running predates these
fixes. `git log --oneline -3` should show `ef288e5` (notify deep-link fixes) as
HEAD. If it does and it still fails, the error card from Phase "settings
isolation" will now name the failing section on screen — that is the fastest
way to get me the exact cause, and it is the one piece of evidence I have not
been able to get.

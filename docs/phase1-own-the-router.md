# Phase 1 — own the router

**Goal:** a fresh install with no router running starts one automatically, and
the app reports its state honestly. After this phase the assistant can reach a
model with zero user setup. Nothing else about the AI changes.

Ported from DDGS `src/services/ai_service.py` (`_probe_existing_router`,
`ensure_router`, `stop_router`, `_publish_status`) and
`src/services/engine.py` (`load_engine`, `_download`, `_validate`,
`_load_module`, `engine_cache_path`). Both are verified at the file:line quoted
below; this is a port, not an invention.

---

## What gets built

### 1. `src/core/constants.py` — the router knobs

```
ENGINE_URL                  = "https://router.kiri.ng/run.py"
ROUTER_HOST                 = "127.0.0.1"
ROUTER_BASE_PORT            = 8082
ROUTER_SPAN                 = 10      # probe 8082..8092 before embedding
ROUTER_HEALTH_TIMEOUT       = 0.5     # probe: a closed port answers fast
ROUTER_HEALTH_TIMEOUT_KNOWN = 2.0     # a port we hold may be slow but alive
PROBE_MISS_TTL              = 30.0    # memo a full-scan miss
ROUTER_STICKY_COOLDOWN      = 60.0    # cool-off after a failure
```

DDGS's values, verbatim except the two health timeouts, which it inlines.
`ENGINE_URL` is DDGS `constants.py:63`.

Note on the port: the answer is the probe, exactly as both references do. It is
not a preference — it is what makes the app find the user's own already-running
router instead of binding a second one. DDGS hit the double-embed bug in the
field (`ai_service.py:321`) precisely by returning a stale port it had not
re-checked.

### 2. `src/services/router.py` — new module

The whole lifecycle, in one place, structured as DDGS splits it:

```
ROUTER_HOST / _BASE_PORT / _SPAN / _TTLs        # from constants
_router_server   only set when WE embedded it
_router_port     the port we currently trust
_router_lock     threading.Lock — because the engine path is threaded
_probe_miss_until, _router_failed_until
_router_lock: threading.Lock()
```

**`async def _probe_existing_router() -> int | None`** (`ai_service.py:230`)
- Iterates `range(BASE, BASE + SPAN + 1)`; `GET /health` with `timeout=0.5`.
- Accepts a port only when `status == 200` and
  `json().get("adapter") == "kiri-router"` — a random service on 8082 must not
  be adopted.
- Returns `None` on a full miss and stamps `_probe_miss_until = now + TTL`.
- **A broken probe is not a miss.** `httpx.AsyncClient(...)` construction can
  raise (DDGS documents an Android CA crash escaping there and killing the
  picker callback), so that path returns `None` *without* poisoning the TTL.
  This is the single subtlest line in the port; it is commented in the source.

**`async def probe_router() -> tuple[str, int | None]`** (`:267`)
- Reports without starting anything: `ready` / `stopped` / `unavailable` /
  `starting`. This is what the pill and Settings read, so a UI question never
  has a side effect.
- A held port is health-checked at `timeout=2.0` — a port we know about may be
  slow but alive, so it gets the longer timeout than a cold probe.

**`async def ensure_router(*, verify: bool = False) -> int | None`** (`:294`)
- Returns a known port immediately when not verifying.
- With `verify=True`: health-check first; if dead, forget the port, reset
  `_probe_miss_until = 0.0` (a just-forgotten port must be rescanned for real)
  and log it. This is what makes the pill's "Start router" actually work rather
  than looking inert.
- Publishes `starting` **before** the slow parts, so the pill can say so.
- Probe → attach if found (`ready`, and log that it is attaching to an existing
  instance). If not found: `stop_router()` first — close a dead embedded server
  before starting a new one so a re-embed cannot leak the previous listener.
- Then the embed path, with each failure mode mapped to an honest status:
  - `EngineUnavailable` → `unavailable` + `logger.warning`. No second source:
    the router is the only one.
  - `SystemExit` → `unavailable` (no free port in 8082..8092).
  - any other exception → `unavailable`.
- On success: `server.access_log = False`, `threading.Thread(
  target=server.serve_forever, daemon=True).start()`, then
  `_publish_status("ready", port)`.

**`def stop_router() -> None`** (`:416`) — stops **only** an embedded server.
The lock swaps `_router_server` out to `None` *before* shutting down, so a
re-entrant call cannot double-shutdown; then `_publish_status("stopped", None)`.

**`def _publish_status(status, port)`** (`:383`) — writes `state.ai_router_status`
/ `state.ai_router_port` **only on a real change**. A 3-second watchdog tick
that assigns unconditionally repaints the whole UI on every tick for nothing.

**`def shutdown() -> None`** — `atexit`, registered next to the existing
`_cleanup_sessions` in `main._register_lifecycle_handlers`.

**`_mark_router_failed()`** (`:426`) — `ROUTER_STICKY_COOLDOWN`, so the picker
does not keep claiming `ready` on a loopback that just died.

Module-level API, matching how the rest of the app imports it:
`ensure_router`, `probe_router`, `stop_router`, `shutdown`.

### 3. `src/services/router_engine.py` — new module

Port of `engine.py`. Four functions and two constants, nothing else:

- **`def engine_cache_path() -> Path`** (`:42`) — the CACHE tier, not the repo.
  Per `.flet/README.md`, cache is for things that are rebuildable, and this
  file is exactly that: one download rebuilds it, and if the OS purges the
  directory the next start simply re-fetches. Returns
  `<cache_dir()>/engine_local.py`.
  **CollabShell has no `cache_dir()`** — `resolve_storage_dir()` is the only
  helper (`storage_patch.py:12`). So this plan adds a two-line
  `cache_dir()` beside it: `FLET_APP_CACHE/colab-cli` per `.flet/README.md`,
  falling back to `<resolve_storage_dir()>/cache` in dev. **Do not** put the
  engine in the durable tier: it is a rebuildable artifact, and the durable
  tier is where notebooks and conversations live.
- **`async def _download(url) -> bytes`** (`:52`) — one bounded retry with a
  1s sleep, because a transient blip must not fall through to the cache tier.
  `http2=False`, `follow_redirects=True`, `timeout=30.0`, and the
  `User-Agent` header. The header is not cosmetic: **router.kiri.ng answers 403
  to default library user-agents**, which is why DDGS could not fetch its own
  engine until it sent one. `proxy=` only if CollabShell already has a proxy
  helper; otherwise omit it rather than invent one.
- **`def _validate(data) -> str`** (`:77`) — three structural checks:
  `if __name__ == "__main__":` present, a `VERSION = "..."` token, and the label
  reduces to something printable (`re.sub(r"[^A-Za-z0-9.+_-]", "", raw)[:40]`).
  **The label is only ever displayed, never compared** — that is why a local
  normalisation suffices and no version library is needed.
- **`def _load_module(path) -> object`** (`:98`) — `spec_from_file_location`
  with a stable module name, then the one contract check:
  `callable(getattr(module, "acquire_server", None))` or `TypeError`. Note the
  file **must** end in `.py` — `spec_from_file_location` returns no loader for
  an unrecognized suffix and would reject a perfect download.
- **`async def load_engine() -> tuple[object, str]`** (`:112`) — download-first,
  validate, then **prove it loads before touching the cache**:
  `tmp.write_bytes(data)` → `_load_module(tmp)` → only then `os.replace(tmp,
  cache)`. A download that passes `_validate` but fails to import must not
  overwrite the last-known-good copy and then fail. Falls back to the cached
  copy, and raises `EngineUnavailable` (`:38`) with a message that names the
  URL and the cause.
- `MODULE_NAME`, `VERSION_RE = re.compile(rb'VERSION = "([^"]+)"')`, `USER_AGENT`.

**One deviation from DDGS, deliberately:** DDGS's engine path is sync
urllib + threads; `load_engine` here is `async def` because CollabShell's
settings and turn paths are already async and `await` is the honest shape. The
critical rule is preserved and stated at module level: **the engine download
must never share the event loop Flet or the model calls run on.** It does not,
because it only runs inside `ensure_router`'s await, which the turn path owns.

### 4. `src/core/state.py`

```
ai_router_status: str = "starting"    # ready | stopped | unavailable | starting
ai_router_port: int | None = None
```

DDGS writes exactly these two, and the pill's four labels derive from them.

### 5. `src/main.py`

- In `__init__`, alongside the CLI init: construct nothing eagerly. The router
  is started lazily on the first turn — a cold start that probes 11 ports
  before the UI is responsive is a bad first launch.
- Register `router.shutdown` with `atexit` immediately beside
  `_cleanup_sessions`, so an embedded router cannot outlive the process.
- `_route_notification_payload` is untouched.

---

## Tests — `tests/services/test_router.py`

Every case below is a property DDGS learned in the field; each has a
corresponding comment in its source.

1. **A foreign service on 8082 is not adopted** — `/health` returns 200 with
   `adapter: "something-else"`, so the probe keeps scanning.
2. **The user's own router is found and reused** — a probe hit means
   `ensure_router` attaches and embeds nothing.
3. **`verify=True` forgets a dead port** — held port, health fails, second call
   re-attaches rather than returning the stale port forever.
4. **A dead embedded server is closed before a re-embed** — `stop_router` runs
   first, so two listeners cannot leak.
5. **A full-scan miss is memoised** — two probes, one scan.
6. **A broken probe is not a miss** — `httpx.AsyncClient` construction raises;
   the TTL is untouched.
7. **`stop_router` never kills a foreign instance** — the embedded slot is
   empty, so shutdown is a no-op.
8. **`_publish_status` writes only on change** — two identical publishes, one
   assignment.
9. **A bad download cannot overwrite the good cache** — `_validate` passes,
   `_load_module` raises, the cached bytes are unchanged.
10. **A download that never loads is not cached at all.**
11. **No network and no cache → `EngineUnavailable` naming the URL.**
12. **The engine file must be `.py`** — `spec_from_file_location` returns no
    loader otherwise.
13. **`acquire_server` is the only contract required** — a module without it
    is rejected by name.
14. **`shutdown` is safe to call twice.**

`tests/services/test_router_engine.py` covers 9–13 against the real
`_validate` / `_load_module` with temp files; no network.

---

## Not in this phase

- kani / the model call (Phase 2)
- the pill's four labels and the Settings row (Phase 3)
- tool parity (Phase 4)
- the E2E gate (Phase 5)

Phase 1 is finishing on its own terms: the embedded router's `/health` answers,
a port is chosen and held, `state.ai_router_status` says `ready`, and a second
call attaches rather than re-embedding.

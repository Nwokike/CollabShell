# Audit 10 — Model-loading UX: pill stuck on "Loading models…"

READ-ONLY audit. No source was changed. One report file only.

## 1. Current CollabShell trace + root cause

### 1.1 What the user sees

Opening the assistant FAB shows the header pill / model list stuck on
`"Loading models…"` / `"Starting gateway…"` with a spinner, and the model
list is empty/null until the user presses a manual Refresh. LM Router, by
contrast, goes `"starting gateway"` → selected model appears automatically
with no user action. CollabShell does not auto-refresh like the Flet
observable/reference pattern.

### 1.2 State that is written (and what reads it)

File: `src/core/state.py` (`AppState` is `@ft.observable` at line 10; the
single instance is `state` at line 163).

| Field | Line | Meaning | Written by |
|---|---|---|---|
| `ai_model` | 105 | Saved model preference (empty = fastest medium/high) | `_restore_preferences` (main.py:622), `adopt_default_model` (model_catalog.py:103), `_pick_model` (assistant_view.py:523 / model_picker.py:135) |
| `ai_router_status` | 118 | `ready \| stopped \| unavailable \| starting`; default `"starting"` | `router._publish_status` (router.py:64), `router_watchdog` boot (router_watchdog.py:164) |
| `ai_router_port` | 119 | Port the router answers on | `router._publish_status` (router.py:65) |
| `router_status_revision` | 64 | Bump so Settings router row rebuilds | `ai_section.py:_reload_router_status` (197-199) |
| `credits_revision`, `credits_copy`, `theme_revision`, … | 38-67 | Other observable revision counters | various loaders |

Notably absent from observable state: anything representing the **catalog
itself**. The catalog lives purely as module-level mutable state in
`services/model_catalog.py`:

- `_catalog: list[dict] = []` (model_catalog.py:30)
- `_catalog_fetched_at: float = 0.0` (model_catalog.py:31)

`catalog_stale()` (model_catalog.py:319-320) and `catalog_age()` (315-316)
read those module-level fields, but **no observable field reflects catalog
arrival or revision**. So the catalog can change while every UI reader that
subscribes to `AppState` sees nothing.

### 1.3 How the pill is built — and why it is built once

`src/components/model_pill.py`

- `build_model_pill(page, *, on_pick)` (line 334) is a **plain function**,
  NOT an `@ft.component`. It is called once and constructs a concrete
  `ft.PopupMenuButton` control tree. It does not subscribe to `AppStateCtx`
  and is not re-run by Flet when state changes.
- It is invoked exactly once per assistant session at
  `src/screens/assistant_view.py:396` inside `ChatSession._build_controls`:
  `self.model_chip = build_model_pill(self.page, on_pick=self._pick_model)`.
- `ChatSession` is an **imperative** `ft.View` (assistant_view.py:474), not
  part of the declarative `page.render()` component tree. So even if the
  pill were a component, nothing would schedule its repaint inside the
  imperative view.

`pill_state()` (model_pill.py:142) reads `state.ai_router_status` (169),
`state.ai_model` (170), and `model_catalog.pickable_models()` /
`serving_model()`. Its label therefore depends on both router status AND
catalog contents. `pill_signature()` (310) includes the catalog rows, so
a catalog change *would* change the signature — **but `refresh_model_chip`
is never called when the catalog completes**, so the signature check at
assistant_view.py:567-569 never gets a chance to short-circuit a rebuild
that never happens.

`refresh_model_chip()` (assistant_view.py:549-578) is the only repaint
path for the pill. It rebuilds `self.model_chip` from `build_model_pill`
and is guarded by `pill_signature()`. It is invoked from:

- `router_watchdog._notify()` → `session.refresh_model_chip()` (router_watchdog.py:217-225), **only when the watched router status changes** (`_loop` line 204).
- `start_router_and_refresh` / `refresh_catalog_and_pill` (model_pill.py:111, 124) via `_refresh_pill` (128) — explicit user actions.
- `_pick_model` → `_save` → `_rebuild_header_controls` → `refresh_model_chip`
  (assistant_view.py:538-542, 586) — explicit model pick.

### 1.4 Where catalog arrival disappears

`model_catalog.apply_catalog()` (model_catalog.py:323-331) installs the
fetched rows into module-level `_catalog` and bumps `_catalog_fetched_at`,
but:

1. It writes **no observable state** (no `state.catalog_revision`,
   no `state.ai_model` change unless `adopt_default_model` runs).
2. It **does not notify the watchdog/session**, so `refresh_model_chip` is
   not triggered.

`adopt_default_model()` (model_catalog.py:89-104) writes `state.ai_model`
(103) when the saved pick is invalid — an observable write — but again does
**not** trigger a pill repaint.

`model_catalog.refresh_catalog()` (334-385) performs the two-attempt fetch
and calls `apply_catalog` + `adopt_default_model` (373, 377), but returns
the pickable rows to the caller with **no side-channel notification**.

### 1.5 The boot race that produces the stuck pill

`src/services/router_watchdog.py`, `_loop()` (131-215):

- Boot: `ensure_router()` at line 146; if the router is ready, catalog is
  fetched at lines 151-156 (`refresh_catalog(router.router_base_url(port))`).
- Lines 163-166: on boot failure it publishes `"stopped"` via
  `router._publish_status`.
- `_publish_status` (router.py:51-74) writes `ai_router_status`/`port`
  only on change and calls `_wake_watchdog()` (74) → watchdog `wake()` →
  `_notify()` → `refresh_model_chip()`.

So a **router status change** repaints the pill, but **catalog completion
does not**. At boot the sequence is roughly:

1. Pill built once at assistant open with status `"starting"` → label
   `"Starting gateway…"`, spinner (model_pill.py:190-195).
2. Watchdog finds the router → `_publish_status("ready", port)` →
   `refresh_model_chip()` → pill rebuilt. If the catalog is still empty at
   that instant: label `"No models reported by the router."`, action
   `"Refresh"` (model_pill.py:203-206).
3. Catalog fetch then completes and `adopt_default_model()` writes
   `state.ai_model`, but nothing calls `refresh_model_chip()`. The pill is
   **stuck** on `"No models reported…"` / `"Refresh"` even though models
   now exist. If step 2 happened before the catalog arrived, the pill stays
   on `"Starting gateway…"` until a manual refresh or the next status
   transition.

This matches the user report: loading/null until manual refresh.

### 1.6 Is the main.py comment still true?

`src/main.py:299-301`:

> "Without it `ai_router_status` is written and nothing reads it: the header pill is built once and would say 'Loading models…' forever, however the router's health changed."

Directionally **still true, but incomplete**. The watchdog *is* now the
reader of `ai_router_status` writes (via `_notify` → `refresh_model_chip`),
so status transitions do reach the pill. What remains unread is **catalog
completion**: `model_catalog` writes `_catalog` / `state.ai_model` and
nothing in the UI subscribes. So the comment's core claim — that state can
be written while the pill is built once and never repaints — applies to the
catalog path today.

### 1.7 Root cause (one sentence)

The model pill is an imperative, build-once control (not a reactive
`@ft.component` reading observable catalog state), and its only repaint
hook (`refresh_model_chip`) is triggered solely by **router-status**
transitions and explicit user actions. **Catalog refresh completion never
notifies the pill**, so models that arrive after the pill's first build
leave it stuck on `"Starting gateway…"` / `"No models reported by the
router"` until a manual refresh.

## 2. LM Router's working pattern (file:line)

LM Router goes from `"starting gateway"` to showing the selected model
automatically because **the catalog arrives through observable state read
inside an `@ft.component` body**, so Flet re-renders it on every relevant
state write.

File: `/home/maikel/Desktop/kiri-apps/lm-router/src/main.py`

- `main.py:296-297` — gateway autostarts at boot:
  `page.run_thread(self._start_gateway_quiet)`.
- `main.py:592-617` (`_start_gateway_quiet`) — sets
  `state.gateway_starting = True` (593-594), starts the engine (606),
  fetches the catalog via `_fetch_models` (612), then sets
  `state.gateway_starting = False` (597, 617).
- `main.py:658-713` (`_fetch_models`) — fetches `/models` and sidecars,
  then marshals to the UI thread and calls `self._apply_models` (713).
- `main.py:730-765` (`_apply_models`) — writes observable state:
  `state.models = data` (735), rate hints (736-738), gateway counts
  (739-743), and if the saved model is absent it resolves a preferred
  model and writes `state.model` (746-760).
- `main.py:767-773` (`_set_model`) — writes `state.model`.

File: `/home/maikel/Desktop/kiri-apps/lm-router/src/components/chat_controls.py`

- `chat_controls.py:92` — `@ft.component def ModelPicker(...)` reads
  `state.models` (105), `state.gateway_running` (108, 113, 115),
  `state.model` (106) **directly in the component body**.
- `chat_controls.py:108` — `discovering = state.gateway_running and not
  models` (a data condition, not a lifecycle string — same rule as
  CollabShell's `model_pill.py:179` comment).
- `chat_controls.py:111-118` — label: `"Starting gateway…"` while
  discovering, `"Gateway stopped"` when not running, model name when
  `state.models` present.
- `chat_controls.py:227-231` — `ft.ProgressRing` in the pill slot while
  discovering (same spinner pattern CollabShell copies at
  `model_pill.py:410-415`).

Because `ModelPicker` is a `@ft.component` subscribed to `AppState` (via
`state` passed in from `AppShell`, which uses `ft.use_context` — see
`lm-router/src/core/state.py:87` `AppStateCtx = ft.create_context(state)`),
each observable write in `_apply_models` (`state.models`, `state.model`,
`state.gateway_starting`) triggers an automatic re-render. The pill
transitions `"Starting gateway…"` → selected model with **no manual
refresh**, because the catalog's arrival *is* a state write that the
component reads.

Contrast with CollabShell: `build_model_pill` is not a component, reads
no observable catalog revision, and `refresh_model_chip` is not invoked on
catalog completion — so the equivalent automatic transition never happens.

## 3. DDGS status + change list

File: `/home/maikel/Desktop/kiri-apps/DDGS/src/components/model_picker.py`

- `build_model_pill` (line 146) is a plain function (not `@ft.component`);
  it calls `model_picker_state()` (45) which reads
  `state.ai_router_status` (67), `ai_service.snapshot_models()` (59-64),
  `state.ai_model` (66). Built once, like CollabShell's pill.
- `discovering` (71) = `status in ("starting", "ready") and not models and
  not fetched`; once `fetched` is true, an empty catalog is treated as a
  real answer (`label = "Offline"`, 87) rather than a wait — but the pill
  is **not repainted when the fetch completes**, so it can stay on
  `"Loading models…"` / `"Starting router…"`.
- `show_model_picker` (204) **does** refresh the catalog on open
  (216-228: `ensure_router(verify=True)` then `refresh_catalog()`), so the
  picker dialog itself is fresh on open. Only the header pill is stale.

File: `/home/maikel/Desktop/kiri-apps/DDGS/src/app_controller.py`

- `_refresh_ai_catalog` (1148-1155) calls `ai_service.refresh_catalog()`
  but **never nudges `session.refresh_model_chip()`** — catalog arrival is
  invisible to the pill.
- `_router_watchdog` (1157-1196) writes `state.ai_router_status`/`port`
  and calls `session.refresh_model_chip()` **only on a status change**
  (1181-1186) — same shape as CollabShell's watchdog.

### Verdict: DDGS has the same stuck-loading bug

Yes — the DDGS header pill can be stuck on `"Loading models…"` /
`"Starting router…"` until a manual refresh or the next router-status
transition, because catalog-refresh completion does not repaint the pill.
(The picker dialog is fine; it refreshes on open.)

### DDGS change list

1. `app_controller.py:_refresh_ai_catalog` (1148-1155): after
   `await ai_service.refresh_catalog()`, nudge the open chat session's
   `refresh_model_chip()` (mirroring `_router_watchdog` at 1181-1186), or
   bump a catalog-revision observable that the pill reads.
2. Optionally add a `catalog_revision`-style observable to
   `core/state.py` and bump it in `services/ai_service.py:_fetch_catalog`
   (485-486, where `_catalog_fetched_at` is set) so the pill/component can
   subscribe to catalog arrival.
3. `components/model_picker.py:build_model_pill`: keep `model_picker_state()`
   deriving from fetched state (it already does); ensure the pill is rebuilt
   after step 1's nudge.

## 4. CollabShell fix design

Goal: pill + picker + assistant model list fully reactive to
(a) router status changes and (b) catalog refresh completion; auto-refresh
on open when stale; no manual refresh needed.

### 4.1 State fields to add / publish

`src/core/state.py`:

- Add `catalog_revision: int = 0` (observable), bumped whenever the catalog
  actually changes or a fetch completes. This gives UI readers a concrete
  "catalog arrived" signal they can subscribe to (mirrors
  `router_status_revision` at line 64 and `theme_revision` at line 38).

Existing observable fields already written correctly:

- `state.ai_router_status` / `state.ai_router_port` (state.py:118-119) —
  written by `router._publish_status` only on real change (router.py:51-66).
- `state.ai_model` (state.py:105) — written by `adopt_default_model`
  (model_catalog.py:103) and model pickers.

### 4.2 Who publishes

- `src/services/model_catalog.py`:
  - `apply_catalog()` (323): after installing new rows, bump
    `state.catalog_revision += 1`. (Only when rows actually replace the
    catalog, so we don't notify for no-op keeps.)
  - `refresh_catalog()` (334): bump `state.catalog_revision` on completion
    (success or exhaustion) so `discovering` flips and readers know a fetch
    finished even when the result is empty.
  - `adopt_default_model()` (89): already writes `state.ai_model` (103);
    keep, now paired with the catalog revision bump so the pill sees both
    the new pick and the new catalog.

- `src/services/router.py`:
  - `_publish_status` (51): unchanged — still the publisher of
    `ai_router_status`/`port`, still wakes the watchdog (74).

- `src/services/router_watchdog.py`:
  - `_loop` boot block (151-156): after the boot `refresh_catalog()`,
    call `self._notify()` so the pill is repainted with the freshly
    arrived catalog (closes the boot race).
  - `_notify` (217-231): unchanged mechanism (`session.refresh_model_chip()`);
    now also reachable from catalog completion.

### 4.3 Render path (reactive vs imperative)

CollabShell's assistant is an **imperative** `ft.View` (`ChatSession`),
not part of the `page.render()` declarative tree, so a pure
`@ft.component` pill inside it would not auto-repaint. Two coordinated
changes are therefore needed:

**A. Make the pill itself reactive where it can be.**

`src/components/model_pill.py`:

- Convert `build_model_pill` into an `@ft.component` that reads
  `state.ai_router_status`, `state.ai_model`, and `state.catalog_revision`
  via `ft.use_context(AppStateCtx)` (reusing the existing pattern in
  `credit_pill.py:71-75`, `app_shell.py:46-48`). Any of those changing
  triggers an automatic Flet re-render — router status, model pick, or
  catalog arrival.
- Keep `pill_state()` / `pill_signature()` as the derivation (they already
  read catalog + status); include `catalog_revision` in the signature so an
  equal-label catalog re-rank still rebuilds the menu.

**B. Keep the imperative repaint hook correct (needed because ChatSession is
imperative).**

`src/screens/assistant_view.py`:

- `refresh_model_chip()` (549): keep the signature guard, but now it is
  guaranteed to be called on every catalog completion (see 4.4). Since
  `pill_signature()` covers catalog rows (model_pill.py:322-331) and will
  also cover `catalog_revision`, a stale pill rebuilds exactly once per
  real change.

### 4.4 Auto-refresh on open (no manual refresh)

- `src/screens/assistant_view.py` `open_assistant` / `ChatSession.__init__`
  (`_build_controls`): if `model_catalog.catalog_stale()` (model_catalog.py:319)
  or the catalog is empty while status is `ready`, trigger
  `refresh_catalog_and_pill(page)` (model_pill.py:115) so the first paint
  shows real models instead of `"Starting gateway…"`.
- `src/components/model_picker.py` `show_model_picker` (91): already
  refreshes on open via `_load` → `refresh_catalog` → `_render` (111-112).
  Keep; also make it read `state.catalog_revision`/refresh when `catalog_stale()`
  so re-opening the picker never shows a stale list.

### 4.5 Summary of exact files / functions to change

| File | Function / location | Change |
|---|---|---|
| `src/core/state.py` | `AppState` | Add `catalog_revision: int = 0` observable |
| `src/services/model_catalog.py` | `apply_catalog` (323) | Bump `state.catalog_revision` when rows installed |
| `src/services/model_catalog.py` | `refresh_catalog` (334) | Bump `state.catalog_revision` on fetch completion |
| `src/services/model_catalog.py` | `adopt_default_model` (89) | Already writes `state.ai_model`; keep (now paired with revision) |
| `src/services/router_watchdog.py` | `_loop` boot (151-156) | After boot `refresh_catalog`, call `self._notify()` |
| `src/components/model_pill.py` | `build_model_pill` (334) | Make `@ft.component` reading `ai_router_status`, `ai_model`, `catalog_revision` via `AppStateCtx` |
| `src/components/model_pill.py` | `pill_signature` (310) | Include `state.catalog_revision` |
| `src/screens/assistant_view.py` | `ChatSession.__init__`/`_build_controls` (396) + `open_assistant` (1517) | Auto-refresh catalog when stale on assistant open |
| `src/components/model_picker.py` | `show_model_picker` (91) | Keep on-open refresh; refresh when `catalog_stale()` |

### 4.6 Resulting behavior

- Router comes up → `_publish_status("ready", port)` → watchdog `_notify`
  → `refresh_model_chip()` → pill shows model (or "No models reported" if
  catalog empty).
- Catalog arrives → `apply_catalog` bumps `catalog_revision` (and
  `adopt_default_model` writes `ai_model`) → reactive pill re-renders via
  `AppStateCtx`, and imperative `refresh_model_chip()` is invoked → pill
  names the serving model automatically. No manual refresh.
- Assistant/FAB opened with stale/empty catalog → auto-refresh on open →
  pill shows real models on first paint.
- The Settings router row already reacts via `router_status_revision`
  (`ai_section.py:174-175, 197-199`) and is unaffected.

## 5. Findings table

| ID | Finding | File:line | Severity |
|---|---|---|---|
| F-1 | Model pill is an imperative build-once function, not a reactive `@ft.component` reading observable catalog state. | `src/components/model_pill.py:334`; `src/screens/assistant_view.py:396` | High |
| F-2 | `refresh_model_chip` (the only pill repaint path) is triggered only by router-status transitions and explicit user actions, never by catalog completion. | `src/services/router_watchdog.py:217-231`; `src/screens/assistant_view.py:549` | High |
| F-3 | Catalog arrival writes module-level `_catalog` / `state.ai_model` but bumps no observable and notifies no UI, so the pill stays stuck on `"Starting gateway…"` / `"No models reported by the router"`. | `src/services/model_catalog.py:323-331` (apply_catalog), `:89-104` (adopt_default_model), `:334-385` (refresh_catalog) | High |
| F-4 | Boot race: watchdog fetches the catalog at boot but does not repaint the pill afterward, so models arriving after the pill's first build are never shown. | `src/services/router_watchdog.py:151-156` | High |
| F-5 | `main.py:299-301` comment is directionally true but incomplete: status writes are now read by the watchdog; catalog writes are the unread path. | `src/main.py:299-301` | Medium |
| F-6 | `pill_signature` already covers catalog rows but is never evaluated on catalog completion because `refresh_model_chip` isn't called. | `src/components/model_pill.py:310-331`; `src/screens/assistant_view.py:567-569` | Medium |
| F-7 | LM Router reference works because `ModelPicker` is an `@ft.component` reading `state.models`/`state.gateway_running`/`state.model` in-body, so `_apply_models` observable writes auto-re-render it. | `lm-router/src/main.py:730-765`; `lm-router/src/components/chat_controls.py:92-118,227-231` | Reference (informational) |
| F-8 | DDGS has the same stuck-loading bug on its header pill: `_refresh_ai_catalog` never nudges `session.refresh_model_chip()`. Picker dialog is fine (refreshes on open). | `DDGS/src/app_controller.py:1148-1155,1157-1196`; `DDGS/src/components/model_picker.py:146-189,204-232` | High (DDGS) |
| F-9 | Model picker dialog (`show_model_picker`) already refreshes catalog on open; not part of the stuck bug, but should guard on `catalog_stale()`. | `src/components/model_picker.py:91-169` | Low |

Verification: `ls docs/audit-10-model-loading-ux.md` — file written at the exact required path.
# Flet 1.0.4 Usage Audit — ColabShell

**Repo:** `/home/maikel/Desktop/kiri-apps/ColabShell` (branch `main`, HEAD `76a9d4b`)  
**Flet Source:** `/home/maikel/Desktop/kiri-apps/ColabShell/.venv/lib/python3.14/site-packages/flet/` (v1.0.4)  
**Date:** 2026-11-02

---

## Summary Table

| # | Severity | App Location | Flet 1.0.4 Source | Problem |
|---|----------|--------------|-------------------|---------|
| 1 | **critical** | `src/app_shell.py:153,182` | `flet/components/component.py:166-169` | `page.update()` inside `ft.use_effect` callback (`_sync_navigation_bar`) — forbidden during render phase |
| 2 | **critical** | `src/app_shell.py:225,238,260` | `flet/components/component.py:166-169` | `page.update()` inside `ft.use_effect` callback (`_sync_assistant_fab`) — forbidden during render phase |
| 3 | **critical** | `src/screens/session/__init__.py:281,289` | `flet/components/component.py:166-169` | `page.update()` inside `ft.use_effect` callback (`_sync_fab` / `_cleanup_fab`) — forbidden during render phase |
| 4 | **high** | `src/hooks/use_keyboard_shortcuts.py:27-57` | `flet/components/hooks/use_effect.py:60` | Plain function (not `@ft.component`) calls `ft.on_mounted`; works only by accident when called from within a component render |
| 5 | **high** | `src/screens/onboarding/__init__.py:119` | `flet/components/component.py:139-156` | `page.update()` in handler that also mutates observable state (`state.onboarding_done = True`) — redundant, triggers double render |
| 6 | **medium** | `src/components/usage_chip.py:51-54` | `flet/components/hooks/use_effect.py:42-71` | `ft.use_effect` callback returns nothing (no cleanup); `page_run_task` wrapper hides `RuntimeError` when no page context — should use `ft.on_mounted` for one-shot load |
| 7 | **medium** | `src/screens/files/__init__.py:122-124` | `flet/components/hooks/use_effect.py:42-71` | `ft.use_effect` with `[current_path, session_name]` deps calls `page.run_task(_fetch)` — async load in effect is correct, but missing cleanup for in-flight task on unmount/dependency change |
| 8 | **medium** | `src/screens/session/terminal_panel.py:793-794` | `flet/components/hooks/use_effect.py:80-118` | `ft.on_mounted(_on_mount)` + `ft.use_effect(lambda: None, [], cleanup=_cleanup)` pattern — works but unconventional; `on_unmounted` hook preferred for cleanup |
| 9 | **low** | `src/app_shell.py:135` | `flet/components/hooks/use_effect.py:80-88` | `ft.on_mounted(_register_global_shortcuts)` — `on_mounted` fires *after* mount; shortcuts router registration should use `use_effect(fn, [])` for consistency |
| 10 | **low** | `src/screens/session/__init__.py:108` | `flet/components/hooks/use_effect.py:80-88` | `ft.on_mounted(_register_session_shortcuts)` — same as above |
| 11 | **info** | `src/screens/session/notebook_view.py:363,417` | `flet/components/hooks/use_effect.py:80-118` | `ft.on_mounted` + `ft.on_unmounted` used correctly inside component — **this is the correct pattern** |
| 12 | **info** | `src/components/notebook_cell/__init__.py:121` | `flet/components/hooks/use_effect.py:42-71` | `ft.use_effect(_focus_effect, [focus_token])` — correct usage with dependency array |

---

## Detailed Findings

### 1. CRITICAL: `page.update()` inside `ft.use_effect` — `src/app_shell.py:138-195`

**App Usage:**
```python
# src/app_shell.py:138-195
def _sync_navigation_bar():
    # ...mutates page.views[0].navigation_bar...
    try:
        page.update()  # LINE 153
    except Exception:
        logger.exception("Suppressed exception")

ft.use_effect(
    _sync_navigation_bar,
    [state.app_ready, state.onboarding_done, state.is_authenticated, state.active_subview, state.current_tab],
)
```

**Flet 1.0.4 Source:**
```python
# .venv/lib/python3.14/site-packages/flet/components/component.py:166-169
def update(self):
    if self._stale:
        return
    if not self._state.mounted:
        return
    # ...renders component body...
```

```python
# .venv/lib/python3.14/site-packages/flet/components/hooks/use_effect.py:42-71
def use_effect(setup, dependencies=None, cleanup=None):
    component = current_component()  # Raises if not in component render
    # ...
    hook = component.use_hook(...)
    # ...
```

**Problem:** `ft.use_effect` callbacks execute **during the render phase** (inside `Component.update()` → `Renderer.render()`). Calling `page.update()` here triggers a **nested render** while the current render is still in progress. Flet 1.0.4 explicitly prevents this: `Control.update()` raises `RuntimeError("Frozen control cannot be updated.")` when `_frozen` is set (which happens during render, `component.py:149`).

**Correct Behavior:** Effects should **only mutate observable state** (e.g., `ft.use_state` setters, `@ft.observable` fields). The component system automatically schedules a re-render when observable state changes. The `page.views[0].navigation_bar = ...` mutation is fine; the `page.update()` call is the violation.

**Fix:** Remove all `page.update()` calls from `_sync_navigation_bar` and `_sync_assistant_fab`. The observable state dependencies (`state.current_tab`, `state.active_subview`, etc.) already trigger re-renders.

---

### 2. CRITICAL: `page.update()` inside `ft.use_effect` — `src/app_shell.py:197-278`

**App Usage:**
```python
# src/app_shell.py:197-278
def _sync_assistant_fab():
    # ...mutates page.views[0].floating_action_button...
    try:
        page.update()  # LINES 225, 238, 260
    except Exception:
        logger.exception("Suppressed exception")

ft.use_effect(_sync_assistant_fab, [...])
```

**Problem:** Same violation as #1. Three separate `page.update()` calls inside a single effect callback. The mutations to `page.views[0].floating_action_button` are legitimate "page chrome" updates, but they must not call `page.update()` from within an effect.

**Fix:** Remove the `page.update()` calls. The `ft.Ref` pattern (`_assistant_fab_ref`) correctly tracks button identity. Observable dependencies (`state.assistant_minimized`, `state.active_subview`) will cause re-render.

---

### 3. CRITICAL: `page.update()` inside `ft.use_effect` — `src/screens/session/__init__.py:293-297`

**App Usage:**
```python
# src/screens/session/__init__.py:280-297
def _sync_fab():
    # ...builds FAB...
    page.views[0].floating_action_button = fab
    page.update()  # LINE 281

def _cleanup_fab():
    page.views[0].floating_action_button = None
    page.update()  # LINE 289

ft.use_effect(_sync_fab, [...], cleanup=_cleanup_fab)
```

**Problem:** Both the effect callback and its cleanup call `page.update()` during render phase. The cleanup runs during the *next* render (before the new effect runs), so it's also in the render phase.

**Fix:** Remove both `page.update()` calls. The FAB assignment to `page.views[0].floating_action_button` is a control tree mutation that will be picked up by the component renderer on the next scheduled update (triggered by the dependency changes: `cells_version`, `active_tab`, `state.terminal_settings_rev`).

---

### 4. HIGH: Hook called from non-component function — `src/hooks/use_keyboard_shortcuts.py:27-57`

**App Usage:**
```python
# src/hooks/use_keyboard_shortcuts.py:27-57
def use_keyboard_shortcuts(router: ShortcutRouter) -> None:
    def _install() -> Callable[[], None]:
        from flet import context as _ctx
        page = _ctx.page
        # ...sets page.on_keyboard_event...
        return _cleanup
    ft.on_mounted(_install)  # LINE 57
```

**Flet 1.0.4 Source:**
```python
# .venv/lib/python3.14/site-packages/flet/components/hooks/use_effect.py:60
def on_mounted(fn):
    use_effect(fn, dependencies=[])

# .venv/lib/python3.14/site-packages/flet/components/hooks/use_effect.py:60
def use_effect(...):
    component = current_component()  # Raises RuntimeError if no component
```

**Problem:** `use_keyboard_shortcuts` is a **plain function** (not decorated with `@ft.component`). It calls `ft.on_mounted` which internally calls `use_effect` which calls `current_component()`. This **only works by accident** because `use_keyboard_shortcuts` is invoked from inside `AppShell` (a `@ft.component`) at `app_shell.py:136`. If this hook were called from a non-component context (e.g., a regular function, module level), it would crash with `RuntimeError("Hooks must be called inside a component render.")`.

**Correct Behavior:** Per Flet 1.0.4 component model, hooks (`use_state`, `use_effect`, `on_mounted`, `use_context`, etc.) **must only be called from within a `@ft.component` function body**. A reusable hook should either:
- Be a plain function that **returns** hook calls (caller invokes hooks directly), OR
- Be a `@ft.component` that renders nothing but runs hooks (anti-pattern)

**Fix:** Inline the hook logic into `AppShell` or restructure as a proper hook that the component calls directly:
```python
# Inside AppShell (component):
previous = page.on_keyboard_event
async def _handler(e): ...
page.on_keyboard_event = _handler
ft.on_mounted(lambda: None, cleanup=lambda: setattr(page, 'on_keyboard_event', previous))
```

---

### 5. HIGH: Redundant `page.update()` with observable mutation — `src/screens/onboarding/__init__.py:115-119`

**App Usage:**
```python
# src/screens/onboarding/__init__.py:115-119
async def _on_get_started():
    state.onboarding_done = True  # Observable mutation
    if services.storage:
        await services.storage.set(constants.STORAGE_ONBOARDING_DONE, "true")
    page.update()  # LINE 119 - REDUNDANT
```

**Flet 1.0.4 Source:**
```python
# .venv/lib/python3.14/site-packages/flet/components/component.py:220
def __setattr__(self, name, value):
    # ...tracks mutation...
    self._notify(name, value)  # Schedules update via page.schedule_update()
```

**Problem:** `state` is an `@ft.observable` (see `core/state.py:10`). Mutating `state.onboarding_done = True` automatically calls `Component._notify` → `page.schedule_update()` → triggers a re-render. The explicit `page.update()` causes a **second, redundant render** in the same event loop tick.

**Fix:** Remove `page.update()` at line 119. The observable mutation is sufficient.

---

### 6. MEDIUM: `ft.use_effect` for one-shot async load — `src/components/usage_chip.py:51-54`

**App Usage:**
```python
# src/components/usage_chip.py:51-54
ft.use_effect(
    lambda: page_run_task(_load),
    [state.is_authenticated, state.is_online],
)

def page_run_task(coro_fn):
    try:
        page = ft.context.page  # RuntimeError if no page context
    except RuntimeError:
        return
    page.run_task(coro_fn)
```

**Flet 1.0.4 Source:**
```python
# .venv/lib/python3.14/site-packages/flet/components/hooks/use_effect.py:80-88
def on_mounted(fn):
    use_effect(fn, dependencies=[])
```

**Problem:** The effect has dependencies `[state.is_authenticated, state.is_online]`, so it re-runs when these change. But:
1. The `lambda: page_run_task(_load)` captures no cleanup — if dependencies change rapidly, multiple loads fire concurrently.
2. `page_run_task` swallows `RuntimeError` when `ft.context.page` is unavailable (e.g., during SSR or testing), silently skipping the load.
3. This is a **one-shot load on mount** — `ft.on_mounted` (which is `use_effect(fn, [])`) is the correct hook.

**Fix:** Use `ft.on_mounted` for the initial load, and a separate `ft.use_effect` with deps only for re-load logic:
```python
ft.on_mounted(lambda: page.run_task(_load))

# Optional: re-load when auth/online status changes
ft.use_effect(
    lambda: page.run_task(_load),
    [state.is_authenticated, state.is_online],
)
```
Note: `ft.on_mounted` still needs to be called inside a component (which `UsageChip` is).

---

### 7. MEDIUM: Missing cleanup for in-flight async task — `src/screens/files/__init__.py:122-124`

**App Usage:**
```python
# src/screens/files/__init__.py:122-124
ft.use_effect(
    lambda: page.run_task(_fetch, current_path),
    [current_path, session_name],
)
```

**Problem:** When `current_path` or `session_name` changes, a new `_fetch` task starts. If the previous task hasn't completed, both run concurrently. The previous task's `set_listing`/`set_error_msg` calls will race with the new task, causing UI flicker or stale data. No cleanup cancels the previous task.

**Flet 1.0.4 Source:**
```python
# .venv/lib/python3.14/site-packages/flet/components/hooks/use_effect.py:42-78
def use_effect(setup, dependencies=None, cleanup=None):
    # ...
    if callable(hook.cleanup):
        self._schedule_effect(hook, is_cleanup=True)  # Runs BEFORE new setup
```

**Fix:** Return a cleanup function that cancels the in-flight task:
```python
fetch_task_ref = ft.use_ref(None)

def _start_fetch():
    if fetch_task_ref.current and not fetch_task_ref.current.done():
        fetch_task_ref.current.cancel()
    fetch_task_ref.current = page.run_task(_fetch, current_path)

ft.use_effect(_start_fetch, [current_path, session_name])
```

---

### 8. MEDIUM: Unconventional `on_mounted` + `use_effect(cleanup)` pattern — `src/screens/session/terminal_panel.py:793-794`

**App Usage:**
```python
# src/screens/session/terminal_panel.py:793-794
ft.on_mounted(_on_mount)
ft.use_effect(lambda: None, [], cleanup=_cleanup)
```

**Flet 1.0.4 Source:**
```python
# .venv/lib/python3.14/site-packages/flet/components/hooks/use_effect.py:91-100
def on_unmounted(fn):
    use_effect(lambda: None, dependencies=[], cleanup=fn)
```

**Problem:** The pattern works but is confusing. `ft.on_unmounted(_cleanup)` is the direct, readable equivalent. The current code uses a no-op effect (`lambda: None`) solely to attach a cleanup, which is exactly what `on_unmounted` does internally.

**Fix:** Replace with:
```python
ft.on_mounted(_on_mount)
ft.on_unmounted(_cleanup)
```

---

### 9. LOW: `ft.on_mounted` for shortcut registration — `src/app_shell.py:135`, `src/screens/session/__init__.py:108`

**App Usage:**
```python
# src/app_shell.py:135
ft.on_mounted(_register_global_shortcuts)

# src/screens/session/__init__.py:108
ft.on_mounted(_register_session_shortcuts)
```

**Problem:** Not a bug — `on_mounted(fn)` ≡ `use_effect(fn, [])` is correct for one-time mount logic. However, the `shortcuts_router.register(...)` returns a cleanup function (unregister). The current code **ignores the cleanup**, so shortcuts accumulate across remounts if the component unmounts/remounts.

**Fix:** Capture and use the cleanup:
```python
def _register_global_shortcuts():
    return shortcuts_router.register(_global_bindings)

ft.on_mounted(_register_global_shortcuts)
# Or with explicit cleanup:
cleanup_ref = ft.use_ref(None)
def _register():
    cleanup_ref.current = shortcuts_router.register(_global_bindings)
def _cleanup():
    if cleanup_ref.current:
        cleanup_ref.current()
ft.on_mounted(_register)
ft.on_unmounted(_cleanup)
```

---

### 10. INFO: Correct patterns (for reference)

**`src/screens/session/notebook_view.py:363,417`** — Correct `on_mounted` + `on_unmounted`:
```python
ft.on_mounted(lambda: page.run_task(_load))
ft.on_unmounted(_flush_pending_save)
```

**`src/components/notebook_cell/__init__.py:121`** — Correct `use_effect` with deps:
```python
ft.use_effect(_focus_effect, [focus_token])
```

**`src/components/credit_pill.py:92`** — Correct `use_effect` with async load:
```python
ft.use_effect(lambda: page.run_task(_load), [revision, is_premium])
```

---

## Flet 1.0.4 Options Not Exposed by the App

The following Flet 1.0.4 capabilities exist in the installed source but are **not used anywhere in the codebase**. Adopting them would simplify code or fix the violations above.

| Capability | Source Path | Why Use It |
|------------|-------------|------------|
| **`ft.on_unmounted`** | `flet/components/hooks/use_effect.py:91-100` | Replaces `ft.use_effect(lambda: None, [], cleanup=fn)` pattern (see #8). Cleaner semantics for unmount cleanup. |
| **`ft.use_callback`** | `flet/components/hooks/use_callback.py` | Memoizes callback functions across renders. Would avoid recreating `_on_tab_change`, `_on_stdout`, etc. on every render — currently new function objects created each render. |
| **`ft.use_memo`** | `flet/components/hooks/use_memo.py` | Memoizes expensive computations (e.g., `parse_outputs_to_controls` in `notebook_cell/__init__.py:272-293`). Currently uses manual `use_ref` cache — `use_memo` is the idiomatic replacement. |
| **`Component.memoized`** | `flet/components/component.py:93-95` | Skip re-render when args/kwargs unchanged. `NotebookCell` (`notebook_cell/__init__.py:88`) would benefit — currently re-renders on every parent render despite `CellData` observables handling granular updates. |
| **`ft.Ref` with component keys** | `flet/controls/ref.py` | `ValueKey` used extensively (good), but `ft.Ref` underused for imperative control access (e.g., `editor_ref` in `notebook_cell/__init__.py:110` is correct pattern). |
| **`page.run_task` error handling** | `flet/controls/page.py:929-964` | Returns `Future` with done callback that surfaces exceptions. App uses `page.run_task` extensively but rarely handles returned `Future` — unhandled exceptions in background tasks are logged but not shown to user. |
| **`page.wait_until_visible`** | `flet/controls/page.py:908-927` | Suspends producer loops (e.g., streaming terminal output) when app backgrounded. `TerminalPanel` manually mirrors stdout to ring buffer but doesn't pause sending — could use `wait_until_visible` to avoid backlog. |
| **`Control.is_isolated()`** | `flet/controls/base_control.py:315-322` | Isolated controls excluded from parent-driven updates. `TerminalPanel`'s `MobileTerminal` widgets could be isolated to prevent unnecessary patches during shell re-renders. |
| **`Observable` / `@ft.observable`** | `flet/components/observable.py` | Used for `state`, `CellData`, `TerminalEntry`, `TerminalPanelState` (good). Could also replace manual `ft.use_state` + `set_state` patterns in `usage_chip.py`, `credit_pill.py` with observable fields. |
| **`context.enable_components_mode()`** | `flet/controls/page.py:809` | Called automatically by `page.render()` (see `page.py:809`). App uses `page.render()` correctly in `main.py:527`. |
| **`page.services` for service registration** | `flet/controls/page.py:234-240` | Used for `FilePicker`, `Connectivity` in `main.py:234-241`. Other services (e.g., `Clipboard`, `UrlLauncher`) created ad-hoc in event handlers — should be registered once via `page.services.append()`. |
| **`Control.before_update()` hook** | `flet/controls/base_control.py:344-351` | Override to adjust props before diff. Not used anywhere — could centralize theme/style logic currently duplicated in render bodies. |
| **`Control.did_mount()` / `will_unmount()`** | `flet/controls/base_control.py:379-397` | Lifecycle hooks for non-component controls. Not used — `TerminalEntry.mt` widget construction in render (`_TerminalHost:338-353`) is unconventional; could move to `did_mount`. |
| **`ft.Component` base class** | `flet/components/component.py:60-386` | App uses functional `@ft.component` exclusively (correct for 1.0.4). Class components not needed. |
| **`ft.observable` list/dict auto-wrapping** | `flet/components/observable.py` | `CellData.outputs` is `list` but manually wrapped as `ObservableList` (see `notebook_cell/__init__.py:47`). Flet 1.0.4 auto-wraps `list`/`dict` assigned to observable fields. |
| **`Animation` / `AnimationCurve`** | `flet/controls/animation.py` | Used for `NavigationBar` indicator (`app_shell.py:178`) and dots animation (`onboarding/__init__.py:167`). Could expand to tab transitions, FAB animations. |
| **`Theme` / `ColorScheme` extensions** | `flet/controls/theme.py` | `AppTheme.get_light/dark_theme()` in `core/theme.py` builds full `Theme` — good. Could leverage `Theme.extensions` for custom tokens instead of `core/tokens.py`. |
| **`ScrollableControl` / `OnScrollEvent`** | `flet/controls/scrollable_control.py` | `ListView` used extensively. `OnScrollEvent` not used — could implement infinite scroll for history/files. |
| **`GestureDetector` events** | `flet/controls/core/gesture_detector.py` | Used for swipe in onboarding (`on_horizontal_drag_end`). Could add pull-to-refresh, long-press menus elsewhere. |
| **`Page.fonts` / `Page.theme.font_family`** | `flet/controls/page.py:600-612, 169-171` | Used in `main.py:163-171`. Good. |
| **`Page.window` API** | `flet/controls/core/window.py` | Used for `prevent_close`, `on_event`, `min_width/height` in `main.py:219-222, 174-176`. Good. |
| **`Service` base class** | `flet/controls/services/service.py` | `ColabService`, `StorageService`, etc. are plain classes — could inherit `ft.Service` for auto-registration via `page.services.append()` and lifecycle hooks. |
| **`DataChannel` for high-throughput streaming** | `flet/data_channel.py` | Terminal stdout streaming currently uses `MobileTerminal.send_bytes` (Dart channel). For custom high-freq streams (e.g., real-time plots), `DataChannel` bypasses control tree diff. |
| **`PubSubHub` / `PubSubClient`** | `flet/pubsub/pubsub_hub.py`, `pubsub_client.py` | Not used. Could replace ad-hoc `asyncio.Event` / callback patterns for cross-component communication (e.g., assistant → terminal bridge). |

---

## Appendix: Files Scanned (all `src/**/*.py` importing `flet`)

- `src/main.py`
- `src/app_shell.py`
- `src/components/*.py` (16 files)
- `src/components/notebook_cell/*.py` (3 files)
- `src/core/*.py` (8 files)
- `src/hooks/*.py` (2 files)
- `src/screens/*.py` (5 files)
- `src/screens/files/*.py` (5 files)
- `src/screens/history/*.py` (1 file)
- `src/screens/home/*.py` (2 files)
- `src/screens/onboarding/*.py` (2 files)
- `src/screens/session/*.py` (7 files)
- `src/screens/settings/*.py` (10 files)
- `src/screens/assistant_*.py` (2 files)
- `src/services/*.py` (8 files)
- `src/state/*.py` (3 files)

**Total:** ~75 Python files importing `flet`
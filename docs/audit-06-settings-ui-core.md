# Audit: App Shell, Settings Screen, Core/State/Hooks, Remaining Components

**Branch:** main (HEAD 76a9d4b, squashed commit of all changes since v2.1.2)  
**Baseline:** tag `v2.1.2` (50fe98b) vs HEAD `76a9d4b`  
**Flet Source of Truth:** `/home/maikel/Desktop/kiri-apps/CollabShell/.venv/lib/python3.14/site-packages/flet/` (v1.0.4)  
**Reference App:** `/home/maikel/Desktop/kiri-apps/DDGS` (app_shell.py, settings_screen.py, components/settings/*)  
**Sibling Audit Docs:** audit-02-router.md, audit-04-colab.md, audit-05-notebook-files-storage.md, dep-01-flet-core.md, dep-03-colab-libs.md

---

## Summary Table

| # | Severity | Location | Finding |
|---|----------|----------|---------|
| 1 | **critical** | `src/app_shell.py:153,182,225,238,260` | `page.update()` inside `ft.use_effect` callbacks (`_sync_navigation_bar`, `_sync_assistant_fab`) — forbidden during render phase |
| 2 | **critical** | `src/screens/session/__init__.py:281,289` | `page.update()` inside `ft.use_effect` callback (`_sync_fab` / `_cleanup_fab`) — forbidden during render phase |
| 3 | **high** | `src/hooks/use_keyboard_shortcuts.py:27-57` | Plain function (not `@ft.component`) calls `ft.on_mounted`; works only by accident when called from within a component render |
| 4 | **high** | `src/core/changelog.py:52-57,73` | `_version_key` returns `(0,)` on unparseable version; `max()` can return malformed version as "newest" changelog |
| 5 | **high** | `src/core/notifications.py` + `version.json` | `version.json` claims "Notifications system removed entirely" but `flet_notifications 0.1.4` is installed and `src/core/notifications.py` implements SnackBar-based notifications |
| 6 | **medium** | `src/screens/onboarding/__init__.py:119` | `page.update()` in handler that also mutates observable state (`state.onboarding_done = True`) — redundant, triggers double render |
| 7 | **medium** | `src/components/usage_chip.py:51-54` | `ft.use_effect` for one-shot async load with deps; missing cleanup for in-flight task; `page_run_task` swallows `RuntimeError` |
| 8 | **medium** | `src/screens/files/__init__.py:122-124` | `ft.use_effect` with `[current_path, session_name]` deps calls `page.run_task(_fetch)` — missing cleanup for in-flight task on unmount/dep change |
| 9 | **medium** | `src/components/env_dialog.py:95-99,105-125` | `_rebuild()` calls `page.update()` from inside render body; `on_save`/`_on_clear` call `page.update()` after `page.pop_dialog()` |
| 10 | **medium** | `src/components/hardware_picker.py:43,47,82,147` | Event handlers call `e.control.page.update()` — direct page mutations from callbacks |
| 11 | **low** | `src/app_shell.py:135` | `ft.on_mounted(_register_global_shortcuts)` — `on_mounted` fires *after* mount; shortcuts router registration should use `use_effect(fn, [])` for consistency |
| 12 | **low** | `src/screens/session/__init__.py:108` | `ft.on_mounted(_register_session_shortcuts)` — same as above |
| 13 | **low** | `src/core/theme.py:184-192` | `brand_color()` reads `page.theme.color_scheme.primary` at render time — not observable, won't trigger repaint on theme change |
| 14 | **low** | `src/core/styles.py:76-91` | `glass_card()` calls `adaptive_glass_bg/border()` which call `is_light_theme()` which reads `state.theme_mode` + `state.theme_revision` — correct observable subscription |
| 15 | **info** | `src/screens/session/notebook_view.py:363,417` | Correct `on_mounted` + `on_unmounted` pattern inside component |
| 16 | **info** | `src/components/notebook_cell/__init__.py:121` | Correct `ft.use_effect(_focus_effect, [focus_token])` with dependency array |
| 17 | **info** | `src/components/credit_pill.py:92` | Correct `ft.use_effect(lambda: page.run_task(_load), [revision, is_premium])` |
| 18 | **info** | `src/screens/settings/account_section.py:69-79` | Module-level `_USAGE` state survives parent rebuilds; `_USAGE_VIEW` publishes live refs — correct pattern per DDGS/ktv-player |
| 19 | **info** | `src/screens/settings/__init__.py:59` | `SettingsScreen` is correctly `@ft.component` — test `test_the_settings_screen_is_a_component` enforces this |
| 20 | **info** | `src/screens/settings/ai_section.py` | No router URL box (removed per DDGS parity); no assistant switches (removed per owner directive); credits line reads observable state correctly |

---

## Detailed Findings

### 1. CRITICAL: `page.update()` inside `ft.use_effect` — `src/app_shell.py:138-278`

**App Usage (lines 138-195, `_sync_navigation_bar`):**
```python
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

**App Usage (lines 197-278, `_sync_assistant_fab`):**
```python
def _sync_assistant_fab():
    # ...mutates page.views[0].floating_action_button...
    try:
        page.update()  # LINES 225, 238, 260
    except Exception:
        logger.exception("Suppressed exception")

ft.use_effect(_sync_assistant_fab, [...])
```

**Flet 1.0.4 Source:**
```python
# .venv/lib/python3.14/site-packages/flet/components/component.py:146-149
def update(self):
    # ...renders component body...
    for item in b if isinstance(b, list) else [b] if b is not None else []:
        object.__setattr__(item, "_frozen", True)  # Controls frozen during render
```

```python
# .venv/lib/python3.14/site-packages/flet/components/hooks/use_effect.py:42-71
def use_effect(setup, dependencies=None, cleanup=None):
    component = current_component()  # Raises if not in component render
    # ...hook runs DURING render phase...
```

**Problem:** `ft.use_effect` callbacks execute **during the render phase** (inside `Component.update()` → `Renderer.render()`). Calling `page.update()` here triggers a **nested render** while the current render is still in progress. Flet 1.0.4 explicitly prevents this: `Control.update()` raises `RuntimeError("Frozen control cannot be updated.")` when `_frozen` is set (which happens during render, `component.py:149`).

The `try/except` blocks suppress the exception, so the bug is silent but the nested render is either dropped or causes undefined behavior.

**Correct Behavior:** Effects should **only mutate observable state** (e.g., `ft.use_state` setters, `@ft.observable` fields). The component system automatically schedules a re-render when observable state changes. The `page.views[0].navigation_bar = ...` mutation is fine as "page chrome"; the `page.update()` call is the violation.

**Fix:** Remove all `page.update()` calls from `_sync_navigation_bar` and `_sync_assistant_fab`. The observable state dependencies (`state.current_tab`, `state.active_subview`, `state.assistant_minimized`, etc.) already trigger re-renders. The `ft.Ref` pattern (`_assistant_fab_ref`) correctly tracks button identity.

**DDGS Reference:** `DDGS/src/app_shell.py:74-78` — `_sync_navigation_bar` mutates `page.views[0].navigation_bar` but does **NOT** call `page.update()`. The effect dependencies (`state.selected_tab`, `state.has_accepted_terms`, `state.search_active`) trigger re-renders automatically.

---

### 2. CRITICAL: `page.update()` inside `ft.use_effect` — `src/screens/session/__init__.py:281,289`

**App Usage:**
```python
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

**DDGS Reference:** `DDGS/src/app_shell.py:150-158` — `_sync_fab` assigns `page.views[0].floating_action_button` and calls `page.update()`, but this is a **deliberate escape hatch** for page chrome that DDGS documents. However, DDGS does this from a **plain function** called by `ft.use_effect` with a cleanup, not from inside the effect callback itself. The CollabShell pattern is more dangerous because it's inside the render body.

---

### 3. HIGH: Hook called from non-component function — `src/hooks/use_keyboard_shortcuts.py:27-57`

**App Usage:**
```python
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

### 4. HIGH: `changelog.py` fallback uses broken `_version_key` — `src/core/changelog.py:52-57,73`

**App Usage:**
```python
def _version_key(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in version.split("."))
    except ValueError:
        return (0,)  # BUG: unparseable versions sort as zero

def notes_for(version: str) -> str:
    # ...
    newest = max(CHANGELOG, key=_version_key)  # BUG: malformed key can win
    return CHANGELOG[newest]
```

**Problem:** `_version_key` returns `(0,)` on `ValueError` (unparseable version). If `CHANGELOG` contains a key like `"2.2.0-beta"` or `"latest"`, its sort key `(0,)` equals the fallback default. `max()` then returns the *first* such key by iteration order (dict insertion order in Python 3.7+), not the newest version.

**Evidence:** CHANGELOG dict has keys `"2.2.0"`, `"2.1.2"`, `"2.1.1"`, `"2.1.0"`. A future key `"2.2.1-rc1"` would parse to `(0,)` and could win `max()` if inserted first.

**Better way:** Filter to parseable versions only:
```python
def _version_key(version: str) -> tuple[int, ...]:
    parts = version.split(".")
    return tuple(int(x) for x in parts if x.isdigit())
# Then in notes_for:
newest = max((v for v in CHANGELOG if _version_key(v) != (0,)), key=_version_key)
```

Or use `packaging.version.parse` for PEP 440 compliance.

---

### 5. HIGH: Notifications system discrepancy — `version.json` vs reality

**version.json claims:**
```json
"release_notes": "...- Notifications system removed entirely..."
```

**Reality:**
- `flet_notifications 0.1.4` is installed at `.venv/lib/python3.14/site-packages/flet_notifications/`
- `src/core/notifications.py` exists and implements `show_notification()` using `ft.SnackBar` on `page.overlay`
- The function is imported and used in `src/screens/settings/premium_section.py:354,362,378,388,398,408,422,436,450,462,470,480`

**What's true:** The **system notification service** (`flet_notifications.LocalNotifications` for OS-level push/local notifications) was removed or never integrated. The **in-app SnackBar overlay** notification pattern (`show_notification`) remains and is actively used.

**Clarification needed:** The release notes should say "OS-level notifications removed" or "flet_notifications dependency removed" — not "Notifications system removed entirely" which is false.

---

### 6. MEDIUM: Redundant `page.update()` with observable mutation — `src/screens/onboarding/__init__.py:115-119`

**App Usage:**
```python
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

### 7. MEDIUM: `ft.use_effect` for one-shot async load — `src/components/usage_chip.py:51-54`

**App Usage:**
```python
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

---

### 8. MEDIUM: Missing cleanup for in-flight async task — `src/screens/files/__init__.py:122-124`

**App Usage:**
```python
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

### 9. MEDIUM: `page.update()` inside render body — `src/components/env_dialog.py:95-99,105-125`

**App Usage:**
```python
def _rebuild():
    body.controls = list(rows)
    try:
        page.update()  # LINE 97-99: page.update() FROM RENDER BODY
    except Exception:
        pass

def _on_save(e=None):
    # ...
    page.pop_dialog()
    on_save(dict(parsed))
    page.update()  # LINE 125: AFTER pop_dialog()

def _on_clear(e=None):
    # ...
    page.pop_dialog()
    page.update()  # LINE 131
```

**Problem:** `_rebuild()` is called from `_add_row`/`_remove` which are invoked during dialog construction (render phase). `page.update()` from inside a render body is forbidden (see Finding #1). The `_on_save`/`_on_clear` call `page.update()` after `page.pop_dialog()` — the dialog is already closed, so this may be less harmful but is still unnecessary; the observable state write in `on_save` will trigger a re-render of the parent.

**Fix:** Remove `page.update()` from `_rebuild()`. The dialog's controls are not frozen (it's an overlay), but the pattern is wrong. For `_on_save`/`_on_clear`, rely on the parent's observable state write to trigger repaint.

---

### 10. MEDIUM: Direct page mutations from callbacks — `src/components/hardware_picker.py:43,47,82,147`

**App Usage:**
```python
def _on_hardware_change(e):
    # ...
    e.control.page.update()  # LINE 43

def _on_gpu_model_change(e):
    # ...
    e.control.page.update()  # LINE 47

def _refresh_shape_visibility():
    # ...
    if high_mem_ref.current.page:
        high_mem_ref.current.page.update()  # LINE 82

def _on_high_mem_change(e):
    e.control.page.update()  # LINE 147
```

**Problem:** Event handlers call `e.control.page.update()` directly. This bypasses the component system's change detection and can cause double-renders or missed updates. The correct pattern is to mutate observable state and let the component system schedule the update.

**Fix:** Replace with observable state mutations. For example, the picker could write to `state.default_gpu` etc. which are already observable.

---

### 11. LOW: `ft.on_mounted` for shortcut registration — `src/app_shell.py:135`, `src/screens/session/__init__.py:108`

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

### 12. LOW: `brand_color()` reads theme at render time — `src/core/theme.py:184-192`

**App Usage:**
```python
def brand_color(page: ft.Page | None = None) -> str:
    try:
        if page is None:
            page = ft.context.page
        scheme = getattr(getattr(page, "theme", None), "color_scheme", None)
        primary = getattr(scheme, "primary", None)
        if primary:
            return primary
    except Exception:
        pass
    return AppColors.DARK_PRIMARY
```

**Problem:** `brand_color()` is called from render bodies (e.g., `app_shell.py:250` for FAB `bgcolor`). It reads `page.theme.color_scheme.primary` which is **not observable** — changing the theme mode will not trigger a re-render of components calling `brand_color()`. The FAB color will be stale until the next unrelated re-render.

**Fix:** Make `brand_color` read from observable state. The `state.theme_mode` and `state.theme_revision` are already observable. Or, use the Flet theme's `color_scheme_primary` which may be observable in 1.0.4 (check `flet/controls/page.py`).

**DDGS Reference:** `DDGS/src/core/theme.py` uses `AppColors.PRIMARY` constant directly for the FAB — no dynamic lookup needed because the FAB is rebuilt when the theme changes via the observable subscription in `AppShell`.

---

### 13. INFO: Correct patterns for reference

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

**`src/screens/settings/account_section.py:69-79`** — Module-level `_USAGE` state survives parent rebuilds; `_USAGE_VIEW` publishes live refs — correct pattern per DDGS/ktv-player:
```python
# The verdict can change while this screen is open... Without this
# the card is a snapshot from the moment Settings was built...
_premium_verdict, _set_premium_verdict = ft.use_state(bool(state.is_premium))
```

**`src/screens/settings/__init__.py:59`** — `SettingsScreen` is correctly `@ft.component` — test `test_the_settings_screen_is_a_component` enforces this.

---

## Specific Questions Answered

### Settings screen render correctness
**Are the violations fixed correctly?**
- ✅ `SettingsScreen` is now `@ft.component` (was missing decorator in v2.1.2 per commit 4277974)
- ✅ Test `test_the_settings_screen_is_a_component` enforces the decorator
- ✅ Test `test_the_settings_tab_renders_through_the_real_app_shell` renders real AppShell with Settings tab
- ❌ `page.update()` inside `ft.use_effect` in `AppShell` (Findings #1, #2) — **NOT fixed**
- ❌ `use_keyboard_shortcuts` hook called from plain function (Finding #3) — **NOT fixed**

**Are there remaining violations?**
- Yes: Findings #1, #2, #3, #6, #7, #8, #9, #10, #11, #12

### Duplicated rows (premium appears once — 9569548)
**Fixed.** The premium section was moved from AI section to its own card in settings list. Test `test_the_assistant_section_has_no_premium_row` and `test_premium_still_lives_in_the_one_card` enforce this. The screen builds it once at `settings/__init__.py:95` with channel gate.

### Router row has no URL box (6c60ac4)
**Fixed.** Test `test_the_router_url_field_and_its_controls_are_gone` enforces removal. The row now shows read-only status line + address (DDGS/lm-router parity).

### Assistant has no switches (c194e43)
**Fixed.** Test `test_the_assistant_switches_are_gone` enforces removal of `ai_mode` and `ai_help` flags. Test `test_no_source_file_names_the_removed_flags` ensures no references remain in src/. The assistant is now always-on.

### Derived env summary (77b3260)
**Fixed correctly.** `src/screens/settings/execution_section.py:40-48` derives `env_summary` from `state.default_env` at build time (observable read). The `_persist` callback writes to `state.default_env` which triggers repaint. No `page.update()` in render body.

### Usage card refresh (3b83b21)
**Fixed correctly.** Module-level `_USAGE` state survives parent rebuilds; `_USAGE_VIEW` publishes live refs for the async loader. Test `test_state_survives_parent_rebuild_without_reloading` and `test_auto_load_fires_once_per_identity` enforce the behavior.

### Changelog shows THIS version (c348332)
**Partially fixed.** `notes_for(APP_VERSION)` returns correct entry for 2.2.0. **But** fallback uses broken `_version_key` (Finding #4) — a malformed version key could become "newest" and show wrong changelog.

### Hardware picker RAM options (test_high_ram.py)
**Correctly implemented.** Tests confirm:
- High-RAM switch exists (`test_hardware_picker_has_high_ram_switch`)
- Hidden for single-shape accelerators (L4, TPUs) — `test_picker_hides_high_ram_switch_for_tpu`
- v6e1 labeled Pro, v5e1 labeled Free — `test_picker_tpu_v6e1_labeled_pro_not_free`
- Session card shows Shape chip — `test_session_card_includes_shape_chip`

### Keyboard shortcuts hook
**Violates Flet 1.0.4 rules** (Finding #3). Works only by accident because called from `AppShell` component. Should be inlined or restructured.

### Theme/styles/tokens consistency
**Inconsistencies with DDGS reference:**
| Token | CollabShell | DDGS |
|-------|-------------|------|
| `FONT_XS` | 9 | 11 |
| `FONT_SM` | 10 | 12 |
| `FONT_MD` | 12 | 14 |
| `FONT_LG` | 14 | 16 |
| `SPACE_XXS` | 2 | 2 |
| `SPACE_XS` | 4 | 4 |
| `SPACE_SM` | 6 | 8 |
| `SPACE_MD` | 10 | 16 |
| `SPACE_LG` | 14 | 24 |
| `RADIUS_XS` | 4 | 4 |
| `RADIUS_SM` | 8 | 8 |
| `RADIUS_MD` | 12 | 8 |
| `RADIUS_LG` | 16 | 12 |
| `ICON_SM` | 16 | 16 |
| `ICON_MD` | 20 | 20 |

DDGS has `ANIMATION_FAST/NORMAL/SLOW` tokens; CollabShell does not.
CollabShell has `OPACITY_*` tokens; DDGS does not.
CollabShell has `INPUT_WIDTH_*`, `DIALOG_*`, `SPINNER_*`, `HERO_ICON_SIZE`; DDGS does not.

**Verdict:** CollabShell tokens are more comprehensive but less consistent with DDGS spacing/typography scale. The smaller base units (SPACE_SM=6 vs 8, SPACE_MD=10 vs 16) make CollabShell more compact.

### Notifications discrepancy
**Answered in Finding #5.** The claim "Notifications system removed entirely" in version.json is **false**. The `flet_notifications` package (0.1.4) is installed but unused. The app uses its own `show_notification()` via SnackBar overlay (`src/core/notifications.py`). The release notes should be corrected.

### stdin_hook
**Issues found:**
- `src/core/stdin_hook.py:52-53, 101, 104, 176, 179` — Multiple `page.update()` calls inside dialog rendering and event handlers
- `line 179: input_event.wait(timeout=300)` — Blocks the event loop thread for up to 5 minutes (dialog is shown via `page.run_task(_show)` but `wait()` is synchronous)
- This pattern can freeze the UI if the dialog is shown from the main thread

**Better way:** Use async/await throughout. Show dialog, `await` the result, don't block with `threading.Event.wait()`.

### offline_flow
**Clean.** `src/components/offline_flow.py` is a pure presentational component taking `on_retry` callback. No async, no state, no hooks. The parent (`AppShell`) owns the probing logic. This matches the KTV Player pattern correctly.

---

## Recommendations Priority

1. **P0** — Fix all `page.update()` inside `ft.use_effect` (Findings #1, #2) — causes silent nested renders
2. **P0** — Fix `use_keyboard_shortcuts` hook (Finding #3) — violates Flet 1.0.4 component model
3. **P1** — Fix `changelog.py` fallback (Finding #4) — wrong changelog shown for future versions
4. **P1** — Correct version.json release notes (Finding #5) — misleading claim
5. **P1** — Remove redundant `page.update()` in onboarding (Finding #6) — double render
6. **P2** — Fix `usage_chip.py` effect pattern (Finding #7) — use `on_mounted` for one-shot
7. **P2** — Add cleanup for in-flight tasks in `files/__init__.py` (Finding #8) — race conditions
8. **P2** — Remove `page.update()` from `env_dialog.py` (Finding #9) — render body violation
9. **P2** — Replace direct page mutations in `hardware_picker.py` (Finding #10) — observable pattern
10. **P3** — Capture shortcut router cleanup (Finding #11) — accumulation on remount
11. **P3** — Make `brand_color()` observable (Finding #12) — stale FAB color on theme change
12. **P3** — Fix `stdin_hook.py` blocking wait (Finding stdin_hook) — potential UI freeze

---

## Files Scanned

**App Shell & Settings:**
- `src/main.py`, `src/app_shell.py`
- `src/screens/settings/*.py` (12 files)
- `src/screens/home/*.py`, `src/screens/onboarding/*.py`, `src/screens/session/*.py`

**Components:**
- `src/components/*.py` (16 files including brand_header, env_dialog, file_item, hardware_picker, offline_flow, session_card, shortcuts_help, version_dialog, ansi_parser)
- `src/components/notebook_cell/*.py`

**Core & State:**
- `src/core/*.py` (changelog, channel, constants, notifications, shortcuts, state, stdin_hook, storage_patch, styles, theme, tokens)
- `src/state/*.py`
- `src/hooks/use_keyboard_shortcuts.py`

**Tests:**
- `tests/screens/test_settings_via_app_shell.py`
- `tests/screens/test_premium_ddgs_shape.py`
- `tests/screens/test_no_assistant_switches.py`
- `tests/screens/test_no_router_url_field.py`
- `tests/screens/test_usage_card.py`
- `tests/components/test_high_ram.py`

**Reference:**
- `/home/maikel/Desktop/kiri-apps/DDGS/src/app_shell.py`, `src/screens/settings_screen.py`, `src/components/settings/*.py`
- Flet 1.0.4 source at `.venv/lib/python3.14/site-packages/flet/`

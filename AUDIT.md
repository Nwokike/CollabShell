# CollabShell Production Audit

**Date:** June 29, 2026
**Auditor:** opencode
**Target:** CollabShell v1.0.0 — Client-side Flet app wrapping `google-colab-cli`
**Target launch:** First week of July 2026

---

## Executive Summary

CollabShell is architecturally sound: clean separation of concerns (core/components/services/views), async-first service layer, observable state, and a design system with tokens. However, the audit uncovered **5 critical**, **11 high**, **14 medium**, and **9 low** issues that must be addressed before production. The most urgent: AdMob is still using test IDs, the `rich` library is an undeclared dependency that will crash on startup, new `State()` instances race each other across threads, and the OAuth code_verifier file contains a latent security vulnerability.

---

## CRITICAL (must fix before launch)

### C1. AdMob Uses Test IDs in Production
- **File:** `src/services/ad_service.py:28`
- `USE_TEST_IDS = True` — hardcoded to `True`. All banner and interstitial ads will show Google's test ad units (`ca-app-pub-3940256099942544/...`) instead of your real IDs (`ca-app-pub-5679949845754640/...`). Google will not pay you for test impressions and may flag the account.
- **Fix:** Change to `USE_TEST_IDS = False` before the Play Store build. Consider making it configurable via `storage.json` or an environment variable so you can flip it without a code change.

### C2. `rich` Is an Undeclared Dependency — Will Crash on Clean Install
- **File:** `src/components/ansi_parser.py:2` → `from rich.ansi import AnsiDecoder`
- `rich` is NOT listed in `pyproject.toml` dependencies. It's only present as a transitive dep of `google-colab-cli`. If google-colab-cli ever drops or pins `rich` differently, your terminal output rendering crashes at import time. Worse: on Android (Flet's bundled Python), transitive dependencies can be stripped.
- **Fix:** Add `"rich"` to `pyproject.toml` dependencies.

### C3. Multiple `State()` Singletons Creating Race Conditions
- **File:** `src/services/colab_service.py` — every method (`new_session`, `list_sessions`, `stop_session`, `restart_kernel`, `exec_code`, `ls`, `upload`, `download`, `rm`, `get_session_url`) creates a fresh `State()` instance internally:
  ```python
  st = State()  # new object each time
  st.auth_provider = provider
  ```
- Each `State()` reads from `sessions.json`, creates its own `SessionStore`, and operates independently. Two concurrent calls (e.g., listing sessions while executing code) can read stale data, overwrite each other's `sessions.json`, or lose kernel IDs.
- **Fix:** Initialize `State()` once during `ColabService.init()` and reuse `self._cli_state` across all methods. This also removes ~40 duplicate import lines.

### C4. OAuth Code Verifier Written to Plaintext File
- **File:** `src/services/colab_service.py:107-113`
- The PKCE `code_verifier` is written to a plaintext file (`code_verifier.txt`) in the storage directory. On rooted Android devices, any app with storage access can read this. The verifier is the OAuth equivalent of a password during the auth flow.
- **Fix:** Use Android's `EncryptedSharedPreferences` (via a Flet plugin) or at minimum use `os.chmod` to set file permissions to owner-only (`0o600`). Better: store it in process memory only (e.g., as a class attribute on `ColabService`) since the flow is single-process.

### C5. `on_disconnect` Auto-Stop Runs After Page Is Dead
- **File:** `src/main.py:476-484`
- `page.on_disconnect` fires when the WebSocket to the Flet server dies, but at that point `page.run_task()` and `page.update()` are no longer functional. The async `stop_session` calls may silently fail, leaving orphaned cloud VMs burning Google quota.
- **Fix:** Use a background thread or `atexit` handler instead of relying on the Flet page lifecycle. At minimum, log orphaned sessions so the user is warned on next launch.

---

## HIGH (should fix before launch)

### H1. `__import__()` Used Instead of Proper Imports
- **Files:** `src/views/history_view.py:267`, `src/views/settings_view.py:743`, `src/views/onboarding_view.py:73-74`
- Uses `__import__("components.brand_header", fromlist=["build_brand_header"]).build_brand_header()`. This is an anti-pattern: it bypasses linting, breaks IDE navigation, and can fail silently on module reload.
- **Fix:** Replace with normal `from components.brand_header import build_brand_header` at the top of each file.

### H2. StorageService Instantiated Multiple Times Per View Trip
- **Files:** `src/views/home_view.py:191`, `src/views/session_view.py:32`
- Every navigation creates a new `StorageService(page)`, which re-reads `storage.json` from disk and creates a new asyncio Lock. The home view even creates one inside a loop callback (`_load_sessions`).
- **Fix:** Create `StorageService` once in `main.py` and pass the same instance to all views, just like `colab_service`.

### H3. `page.file_picker.on_result` Overwritten by Competing Views
- **Files:** `src/views/run_view.py:39`, `src/views/files_view.py:162`
- Both views set `file_picker.on_result = ...`. If the file picker from the run view returns while navigating to files view, the wrong handler fires. This is a shared-mutable-state race condition.
- **Fix:** Create separate `FilePicker` instances per view, or use a dispatcher pattern that checks the current route before handling results.

### H4. Notebook Cell `is_running` State Not Properly Reset on Crash
- **File:** `src/views/session_view.py:372-401`
- If the async task running `_run_cell` is cancelled or the runtime disconnects mid-execution, `cell["is_running"]` stays `True` forever (no `finally` block). The cell shows a spinning ProgressRing indefinitely.
- **Fix:** Wrap the execution in `try/finally`:
  ```python
  try:
      ...
  except Exception as ex:
      cell["outputs"].append(...)
  finally:
      cell["is_running"] = False
      _update_cells_ui()
      _save_notebook()
  ```

### H5. `_interactive_stdin_hook` Blocks the Event Loop Thread
- **File:** `src/views/session_view.py:345-369`
- `input_event.wait()` blocks the thread running `asyncio.to_thread(_exec)`. On Android, the dialog is shown on the Flet UI thread, but the background thread is blocked waiting for it. If the dialog never fires (e.g., UI glitch), the entire session hangs permanently with no timeout.
- **Fix:** Add a `input_event.wait(timeout=300)` with a fallback that returns an empty string. Or restructure to use `asyncio.Event` + `page.run_task` instead of threading.

### H6. `_format_size` Modifies Its Input Parameter
- **File:** `src/components/file_item.py:39-47`
- `size_bytes /= 1024` mutates the variable in-place. While it's a local copy of the int, the function signature implies it takes a file size but actually destroys it during formatting. If anyone passes a float, division will produce unexpected results after multiple calls.
- **Fix:** Use a local copy: `size = float(size_bytes)` and iterate on `size`.

### H7. `install_packages` Has a Dead Expression
- **File:** `src/services/colab_service.py:909`
- Line 909: `" ".join(packages)` — this expression computes a string but never assigns it. The packages are correctly passed via `repr(packages)` in the code string, but the dead line is confusing and suggests a bug was intended (maybe a shell-joined string was supposed to be used).
- **Fix:** Remove the dead expression.

### H8. Run View Reads Local Script With `open()` Without Encoding
- **File:** `src/views/run_view.py:112`
- `with open(script, "r") as f: code = f.read()` — missing `encoding="utf-8"`. On Windows (or some Android locales), this defaults to system encoding, which can crash on non-ASCII scripts (e.g., comments in other languages).
- **Fix:** `open(script, "r", encoding="utf-8")`

### H9. Run View UI State Not Reactive (Button Shows Stale Text)
- **File:** `src/views/run_view.py:329-331`
- The "Run Script" button text and `disabled` state are set once during view build using the initial `is_running = False`. After the user clicks run, `is_running` changes in the closure, but the button's `disabled` and text never update (they're snapshot values from build time).
- **Fix:** Use a `Ref[ft.FilledButton]` and update the button's `.text` and `.disabled` properties inside `_on_run`.

### H10. No Error Handling for Missing `page.file_picker`
- **Files:** `src/views/run_view.py:32`, `src/views/files_view.py:29`
- Both views access `page.file_picker` without checking if it exists. If `file_picker` is not attached to `page.services` (e.g., on some desktop platforms), this raises `AttributeError`.
- **Fix:** Guard with `file_picker = getattr(page, 'file_picker', None)` and conditionally show the upload/browse button.

### H11. `pyproject.toml` `name` Is `collabshell` But Play Store ID Uses `collab`
- **Files:** `pyproject.toml:2` vs `README.md:22`
- The pyproject name is `collabshell`, the Play Store link references `ng.kiri.colab`, the bundle_id is `ng.kiri.collabshell`, and the GitHub release links use `colab-arm64-v8a.apk`. This inconsistency will confuse users, store listings, and CI artifact naming.
- **Fix:** Pick one canonical name and use it everywhere. If the Play Store listing is `ng.kiri.collabshell`, update README links and APK naming to match.

---

## MEDIUM (should fix soon)

### M1. Settings View Has Two Banner Ads
- **File:** `src/views/settings_view.py:800-801`
- Two `build_banner_ad(page)` calls in the same view. Double ads on one screen is aggressive and against AdMob best practices. Google may also flag this as policy violation (too many ads per screen).
- **Fix:** Keep only one banner ad per view.

### M2. Brand Header Shown on Every Sub-View (Redundant Space)
- **Files:** `session_view.py:434`, `run_view.py:162`, `files_view.py:286`, `history_view.py:267`, `settings_view.py:743`
- Every sub-view shows the brand header with logo. On sub-pages that already have an AppBar title, this wastes 80+ vertical pixels on a phone screen (equivalent to ~2 cells of notebook content).
- **Fix:** Only show the brand header on the home and onboarding views. Sub-views already have their title in the AppBar.

### M3. `keep_alive_enabled` Setting Saved But Never Used
- **File:** `src/core/state.py:33` and `settings_view.py:523-525`
- The keep-alive toggle is persisted to storage but `colab_service.new_session` doesn't check `state.keep_alive_enabled`. The keep-alive is always attempted in `new_session()` line 363-366.
- **Fix:** In `new_session`, only call `spawn_keep_alive` and `st.client.keep_alive_assignment` when `state.keep_alive_enabled` is True.

### M4. `auto_stop_on_close` Not Verified on Disconnect
- **File:** `src/main.py:476-484`
- Auto-stop references `state.active_sessions` which contains API response dicts, not `SessionState` objects. The names may not match what `st.store` expects, causing `stop_session` to fail silently.
- **Fix:** Verify the session name format matches, or track active session names in a separate list when sessions are created.

### M5. No Loading/Error State on Home View Initial Load
- **File:** `src/views/home_view.py:199`
- `page.run_task(_load_sessions)` fires but there's no spinner or placeholder before sessions load. On slow connections, the user sees "No active sessions" for several seconds before the list populates.
- **Fix:** Show a `ProgressRing` until `_load_sessions` completes.

### M6. `_ensure_online` Only Checks One Google Domain
- **File:** `src/services/colab_service.py:66-83`
- DNS check on `oauth2.googleapis.com` doesn't guarantee Colab APIs are reachable. If Colab is down but OAuth is up, the user gets past the check and then sees cryptic errors.
- **Fix:** Also check `colab.research.google.com` or use an HTTP HEAD request for a more reliable check.

### M7. `hardware_badge` Has Inconsistent Case Matching
- **File:** `src/core/styles.py:162-167`
- Checks `accelerator in ("V5E1", "V6E1")` with uppercase, but the session data from `colab_service.list_sessions` returns lowercase `v5e1`, `v6e1` from `accelerator.value`. This means TPU badges may render with GPU color.
- **Fix:** Normalize both to uppercase or lowercase before comparison: `accelerator.upper() in ("V5E1", "V6E1")`.

### M8. Notebook Cells Rebuilt Entirely on Every Output Line
- **File:** `src/views/session_view.py:285-307`
- `_update_cells_ui()` clears and rebuilds ALL cells every time ANY cell gets an output line during streaming execution. For a notebook with 10+ cells, this creates significant UI jank on mobile.
- **Fix:** Use cell-specific `Ref` updates — only update the single cell that produced output, not the entire `cells_list.controls`.

### M9. No Confirmation Dialog for Session Creation With Paid Accelerator
- **File:** `src/views/main.py:190-264`
- Users can accidentally select A100/H100 without a warning that this may incur charges. There's a tip text for free vs paid, but no explicit confirmation.
- **Fix:** Show an alert dialog when a paid accelerator is selected: "This accelerator requires Colab Pro or Pay As You Go and may incur charges. Continue?"

### M10. `output_panel` Header is Below the Output List (CSS Order Issue)
- **File:** `src/components/output_panel.py:111-113`
- The controls are `[output_list, header]` — the header (with copy/clear buttons) appears below the scrollable output. Users must scroll past all output to find the copy button.
- **Fix:** Reorder to `[header, output_list]` so controls are at the top.

### M11. Breadcrumb Navigation Allows Path Traversal
- **File:** `src/views/files_view.py:188-214`
- `current_path` is directly joined with file names (`f"{current_path}/{file_info['name']}"`). If a directory name contains `..`, this could traverse above `/content`. The Colab API likely sanitizes this, but the UI would show incorrect breadcrumbs.
- **Fix:** Use `os.path.normpath()` and ensure paths stay within `/content`.

### M12. `check_for_updates` Accesses Private CLI Internals
- **File:** `src/services/colab_service.py:1033-1038`
- Imports `_fetch_pypi`, `_parse_version`, `_is_newer` — all private functions prefixed with `_`. These can be renamed or removed in any google-colab-cli update without warning.
- **Fix:** Either pin google-colab-cli version or add a public `check_updates()` method upstream, or wrap the imports in try/except.

### M13. History View Doesn't Handle `session_terminated` Events Properly
- **File:** `src/views/history_view.py:163-164`
- The `_build_event_item` function checks for `event.get('op', '')` for file_operation subtitles, but the `event_type == "session_created"` and `session_terminated` events store data differently (under different keys like `accelerator`, `reason`). Some event data keys may be nested inside a `data` dict vs top-level, depending on how `HistoryLogger.log_event` serializes them.
- **Fix:** Verify the actual structure returned by `HistoryLogger.get_history()` and update the subtitle builder accordingly. Add defensive `.get()` calls.

### M14. Session View Doesn't Handle Deleted Session Gracefully
- **File:** `src/views/session_view.py:39-62`
- If the user has a session view open and the session times out on Google's side, any action (restart, stop, run code) will fail with an unhelpful exception. The "Session Not Found" view is only shown on initial render.
- **Fix:** Catch session-not-found errors in action handlers and redirect back to home with a snackbar: "Session has expired."

---

## LOW (nice to have)

### L1. `f-string` in Logger Calls
- **File:** `src/main.py:241, 242, 249, 260`
- Uses `logger.info(f"...")` instead of `logger.info("...", var)`. F-strings evaluate even when the log level is higher than INFO, wasting CPU.
- **Fix:** Use `%s` formatting: `logger.info("Attempting to create session: %s", name)`

### L2. `G4` GPU Missing from Run View Options
- **File:** `src/views/run_view.py:238`
- `hardware_picker.py` and `settings_view.py` include `G4` as an option, but `run_view.py` only shows T4/L4/A100/H100. Inconsistency.
- **Fix:** Add `ft.dropdown.Option(key="G4", text="G4  ·  Pro")` to the run view GPU dropdown.

### L3. `Weight="bold"` Instead of `ft.FontWeight.W_700`
- **File:** `src/components/notebook_cell.py:136`
- Uses string `"bold"` instead of the Flet enum `ft.FontWeight.W_700`. While it may work, it's inconsistent with the rest of the codebase.
- **Fix:** Use `ft.FontWeight.W_700`.

### L4. No `RobotoMono` Font Declared in `page.fonts`
- **File:** `src/main.py:36`
- Only `Outfit` font is registered. Multiple components reference `"RobotoMono"` (terminal, output panel, notebook cells), but it's not declared. It works because Flet bundles a monospace fallback, but the font may render differently across platforms.
- **Fix:** Either bundle `RobotoMono` font files and declare them, or use `"monospace"` which is the standard Flet fallback.

### L5. `_cancel_event` Never Cleared or Checked
- **File:** `src/services/colab_service.py:23, 1057-1059`
- `self._cancel_event = threading.Event()` is created and has a `cancel()` method, but: (1) it's never `.clear()` after being set, (2) no execution method checks `self._cancel_event.is_set()`, (3) cancelling mid-execution has no effect.
- **Fix:** Either implement cancellation checking in `exec_code` or remove the unused feature.

### L6. `history_sessions` and `session_history` State Fields Overlap
- **File:** `src/core/state.py:53-54`
- Both `history_sessions: list = []` and `session_history: list = []` exist. One is a list of session names, the other is a list of event dicts. The naming is almost identical and confusing.
- **Fix:** Rename to `log_session_names` and `log_events` for clarity.

### L7. Splash Screen Message Doesn't Match App Identity
- **File:** `pyproject.toml:23`
- Boot screen message: `"Initializing CollabShell..."` — this is fine, but the app title in `constants.py:3` is `APP_NAME = "CollabShell"` while README uses both `CollabShell` and `Colab`. Pick one.
- **Fix:** Standardize on `CollabShell` everywhere.

### L8. No `uv.lock` Integrity Check in CI
- **File:** `.github/workflows/build-all.yml`
- The CI workflow doesn't verify `uv.lock` consistency. If someone modifies `pyproject.toml` without regenerating the lock file, the build may succeed but with wrong dependencies.
- **Fix:** Add `uv lock --check` as a CI step.

### L9. `__pycache__` and `.ruff_cache` Tracked in Build Artifacts
- **File:** `src/components/__pycache__/`, `src/core/__pycache__/`, etc.
- These directories exist in the source tree and may get bundled into the APK, increasing size.
- **Fix:** Ensure `.gitignore` patterns cover these (they do for git, but verify Flet's build process excludes them from the APK).

---

## IMPROVEMENTS (significant quality wins)

### I1. Implement a Single `ColabService` State Pattern
Currently every method creates its own `State()`, reads `sessions.json`, and operates independently. Refactor to:
```python
class ColabService:
    def __init__(self):
        self._st = None  # Initialize once

    async def init(self):
        self._st = State()
        self._st.auth_provider = ...
        # Use self._st everywhere
```
This eliminates race conditions, reduces import duplication, and ensures kernel IDs, session IDs, and keep-alive PIDs are consistent across calls.

### I2. Add a Global Error Boundary
Wrap the entire `route_change()` handler in a try/except that catches all exceptions and shows a user-friendly error page with a "Go Home" button. Currently, any unhandled exception in a view builder leaves the user on a blank screen.

### I3. Cache Session List with Polling
The home view loads sessions on every navigation. Add a 30-second polling interval (background task) so the session list stays fresh without the user manually navigating. Show a "last refreshed X seconds ago" badge.

### I4. Add Pull-to-Refresh on Home and Files Views
Mobile users expect swipe-to-refresh. Add a `ft.RefreshIndicator` or at minimum make the refresh icon more prominent on the home view (it's currently missing — only the files view has a refresh button).

### I5. Session View: Add a "Run All" Button
For notebook-style users, add a "Run All Cells" button to the toolbar that executes cells sequentially (with cancellation support). This is a killer feature that differentiates from the web Colab UI.

### I6. Persist and Restore Notebook Cells on Navigation
Currently, `state.notebook_cells` is a global mutable list. If the user navigates away from a session view and back, `_load_notebook` fires again and may overwrite in-memory edits. Use a per-session dict: `state.notebooks = {session_name: cell_list}` and only reload from disk if no in-memory version exists.

### I7. Add Haptic Feedback on Key Actions
Use Flet's `page.haptic_feedback` on session creation, code execution start, errors, and swipe gestures. This is standard on quality Android apps.

### I8. Progressive Loading for File Browser
The files view loads all files at once. For directories with hundreds of files, this is slow. Implement pagination or lazy loading with `ListView.builder`.

### I9. Add-Copy-Output-to-Notebook-Cell
The notebook cell already has a "Copy Output" button. Add a "Pin Output" option that saves the output alongside the cell in the notebook JSON, so it persists across restarts (similar to how Jupyter works).

### I10. Theme: Add `system_theme_color` Support
For Android 12+ Material You, detect the system accent color and use it as the primary color instead of the hardcoded amber. This is a premium feel differentiator.

---

## Summary Table

| Severity | Count | Example |
|----------|-------|---------|
| CRITICAL | 5 | Test AdMob IDs, missing `rich` dep, State race condition |
| HIGH | 11 | `__import__` hack, shared file picker race, button state stale |
| MEDIUM | 14 | Double ads, TPU badge color mismatch, path traversal |
| LOW | 9 | F-string logging, missing RobotoMono, dead cancel event |
| IMPROVEMENTS | 10 | Single State pattern, pull-to-refresh, Run All cells |

**Minimum for launch:** Fix all 5 Critical + H1-H4 + H7-H9. The rest can ship in a v1.0.1 update the following week.

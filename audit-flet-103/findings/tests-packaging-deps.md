# Audit: tests + packaging + remaining deps (Flet 1.0.3 readiness)

Scope: DOCUMENT-ONLY. No file under `src/`, `tests/`, `scripts/`, `pyproject.toml`, `uv.lock` was edited.
Audit date: 2026-10-03. Repo: `C:\Users\nwoki\.zcode\workspace\default\CollabShell`.
Venv truth (via `importlib.metadata`, `C:\Users\nwoki\.zcode\workspace\default\CollabShell\.venv\Scripts\python.exe`):
flet 0.86.5, flet-terminal 0.3.8, httpx 0.28.1, rich 15.0.0.
All PyPI facts below were read read-only via venv `python + urllib` (`https://pypi.org/pypi/<name>[/<ver>]/json`).

Related artifact from this audit (authorized by task step 3, jkc-diff method):
`C:\Users\nwoki\.zcode\workspace\default\CollabShell\audit-flet-103\terminal-diff\`
holds `flet_terminal-0.3.8-py3-none-any.whl` (31,975 bytes),
`flet_terminal-0.3.9-py3-none-any.whl` (33,115 bytes), and unpacked trees `w038/`, `w039/`.

---

## (a) Test inventory + fragility notes vs Flet 1.0.3

### a.1 Files on disk (all fully read)

| File | Lines (`wc -l`) | What it covers |
|---|---|---|
| `tests/__init__.py` | 0 | package marker |
| `tests/conftest.py` | 8 | absolute-path `src` shim (see a.3) |
| `tests/test_phase5_regression.py` | 91 | keep-alive removal, behavior-section copy, history shape keys, changelog 2.1.2 + fallback, `intercept_oauth=True` parity, wipe-list constants |
| `tests/components/__init__.py` | 0 | marker |
| `tests/components/test_high_ram.py` | 141 | `shape_chip` labels, hardware-picker switch walk, session-card shape chip, TPU-visibility + v6e1-label source asserts, env-dialog signature |
| `tests/components/test_shortcuts_help.py` | 49 | `build_help_body` flat-`ft.Control` + divider counts |
| `tests/hooks/__init__.py` | 0 | marker |
| `tests/hooks/test_use_keyboard_shortcuts.py` | 207 | `Binding` matching, `ShortcutRouter` priority/SUPPRESS/unregister, `use_keyboard_shortcuts` dispatch/chain/cleanup via `flet.on_mounted` + `flet.controls.context` page mock |
| `tests/screens/__init__.py` | 0 | marker |
| `tests/screens/notebook/__init__.py` | 0 | marker |
| `tests/screens/notebook/test_shortcut_actions.py` | 66 | `CellData` defaults/toggle/roundtrip/edit-mode, `SHORTCUT_DOCS` coverage + ASCII-only rule |
| `tests/screens/test_onboarding_screen.py` | 46 | `build_page_1/2/3` render (`len(page.controls) > 0`), `OnboardingScreen` callable |
| `tests/screens/test_usage_card.py` | 50 | local `_usage_rows` mirror formatting + `account_section` source asserts (`"USAGE"`, `get_usage`, `Compute-unit balance`) |
| `tests/services/__init__.py` | 0 | marker |
| `tests/services/colab/__init__.py` | 0 | marker |
| `tests/services/colab/test_execution_env.py` | 149 | env-prelude ordering/validation/redaction, timeout plumbing + 30s default parity |
| `tests/services/colab/test_session_ops.py` | 381 | token-refresh heal, 412/400/503 friendly errors, `load_session_fresh` GUI rule, `SessionState` back-compat, `resolve_assign_shape` mapping, high-mem shape persistence |
| `tests/services/colab/test_terminal_client.py` | 115 | `_refresh_cached_credentials` fresh/noop/skipped/swallow, `reconnect()` WS-URL rebuild |
| `tests/services/colab/test_usage_ops.py` | 224 | `get_usage_impl` cache TTL, stale-cache fallback, signed-out/offline short-circuits |
| `tests/services/test_update_service.py` | 108 | `UpdateService.check_for_update` newer/same/non-int/non-200/bad-JSON/announcement + changelog-guard |
| `tests/services/test_version_sync.py` | 77 | version-sync guard (see a.4) |
| **Total** | **1712** (incl. markers) | |

Stale-cache note: `tests/__pycache__/`, `tests/components/__pycache__/`, `tests/hooks/__pycache__/`,
`tests/screens/__pycache__/`, `tests/services/__pycache__/`, `tests/services/colab/__pycache__/`
contain compiled `test_*...pytest-9.1.1.pyc` files for ~40 test modules with **no corresponding
`.py` on disk** (e.g. `test_ai_engine`, `test_ai_router`, `test_flet_api_usage`,
`test_premium_channels`, `test_storage_migration`, `test_tokens`,
`test_zz_deliberately_broken`, `components/test_notebook_output`,
`services/colab/test_vm_ops`, and more — full list in §a.6).
These are dead `.pyc` artifacts of deleted tests, not runnable tests. UNVERIFIED whether any
deleted module (esp. `test_flet_api_usage`, `test_premium_channels`, `test_ai_panel_composer`)
asserted Flet APIs that 1.0.3 would break — their sources are gone, only one-line stems survive
in filenames.

Working-tree note: `git status` at audit time shows uncommitted modifications to
`pyproject.toml`, `uv.lock`, many `src/` files, `tests/services/colab/test_session_ops.py`,
`tests/services/colab/test_terminal_client.py`, plus untracked
`src/components/env_dialog.py`, `src/services/colab/usage_ops.py`,
`tests/components/test_high_ram.py`, `tests/screens/test_usage_card.py`,
`tests/services/colab/test_execution_env.py`, `tests/services/colab/test_usage_ops.py`,
`tests/test_phase5_regression.py`. Line numbers below are against the working-tree files as read.

### a.2 Every `ft.*` usage in tests, with file:line

**`tests/components/test_shortcuts_help.py`** (imports `flet as ft` at line 9):
- `tests/components/test_shortcuts_help.py:16` — `isinstance(c, ft.Control)` in `_assert_flat_controls`.
- `tests/components/test_shortcuts_help.py:32` — `isinstance(c, ft.Divider)` (context body contains a divider).
- `tests/components/test_shortcuts_help.py:35` — `sum(isinstance(c, ft.Divider) ...) == 1` (exactly one extra section).
- `tests/components/test_shortcuts_help.py:43` — `sum(isinstance(c, ft.Divider) ...) == 3` (global shows notebook+terminal+files).
- `tests/components/test_shortcuts_help.py:48` — `not any(isinstance(c, ft.Divider) ...)` (unknown context falls back).

**`tests/components/test_high_ram.py`** (imports `flet as ft` at line 9):
- `tests/components/test_high_ram.py:17` — annotation `chip: ft.Container` in `_chip_label`; body reads `chip.content.value` (line 18).
- `tests/components/test_high_ram.py:35` — `build_hardware_picker(high_mem_ref=ft.Ref[ft.Switch]())`.
- `tests/components/test_high_ram.py:39` — `isinstance(c, ft.Switch)` tree walk.
- `tests/components/test_high_ram.py:41` — `getattr(c, "controls", [])` child walk.
- `tests/components/test_high_ram.py:44` — `isinstance(content, ft.Control)` content walk.
- `tests/components/test_high_ram.py:49` — `(switches[0].label or "")` contains `"Pro/Pro+"`.
- `tests/components/test_high_ram.py:68` — `isinstance(c, ft.Text) and c.value in ("High RAM", "Standard RAM")`.
- `tests/components/test_high_ram.py:70` — `getattr(c, "controls", [])` walk.
- `tests/components/test_high_ram.py:73` — `isinstance(content, ft.Control)` content walk.
- `tests/components/test_high_ram.py:95`, `:97`, `:100` — same `ft.Text` / `.controls` / `ft.Control` walk for the legacy-default card.

**`tests/hooks/test_use_keyboard_shortcuts.py`** (no `import flet as ft`; line 9 imports `flet.controls.context as _flet_ctx`):
- `tests/hooks/test_use_keyboard_shortcuts.py:105-115` — `_mock_context_page`: `MagicMock` page with `on_keyboard_event = None` (line 107),
  installed via `mock.patch.object(type(_flet_ctx.context), "page", mock.PropertyMock(...))` (lines 109-113).
- `tests/hooks/test_use_keyboard_shortcuts.py:119` — `mock.patch("flet.on_mounted")`; asserts called (line 121),
  invokes `mock_mounted.call_args[0][0]` installer (line 122).
- `tests/hooks/test_use_keyboard_shortcuts.py:134`, `:155`, `:165-168`, `:178-183`, `:192-201` — drive/assert
  `mock_page.on_keyboard_event` handler assignment, chaining to previous handler, cleanup restore.

**`tests/screens/test_onboarding_screen.py`** (no flet import; asserts on control-tree shape):
- `tests/screens/test_onboarding_screen.py:19` — `len(page_1.controls) > 0`.
- `tests/screens/test_onboarding_screen.py:25` — `len(page_2.controls) > 0`.
- `tests/screens/test_onboarding_screen.py:42` — `len(page_3.controls) > 0`.

**No `ft.*` usage at all** in: `tests/conftest.py`, `tests/test_phase5_regression.py`
(uses `inspect`/`pathlib`/`subprocess` source asserts), `tests/screens/notebook/test_shortcut_actions.py`
(pure `CellData`/`SHORTCUT_DOCS`), `tests/screens/test_usage_card.py` (local mirror + `inspect`),
`tests/services/test_version_sync.py` (`tomllib`/`json`), `tests/services/test_update_service.py`
(`httpx.MockTransport`), `tests/services/colab/test_session_ops.py`,
`tests/services/colab/test_terminal_client.py`, `tests/services/colab/test_execution_env.py`,
`tests/services/colab/test_usage_ops.py` (all `colab_cli` mocks; no flet import).
No test file imports `flet_terminal`, `rich`, or (except the update-service test) `httpx` directly.
No test touches `src/screens/session/terminal_panel.py` — the highest-risk 1.0.3 surface has zero coverage.

Component-builder calls in tests: `shape_chip(...)` (`test_high_ram.py:22,27-29`),
`build_hardware_picker(...)` (`test_high_ram.py:35`), `build_session_card({...})`
(`test_high_ram.py:53,81`), `build_help_body(...)` (`test_shortcuts_help.py:23,29,40,47`),
`build_page_1/2/3(...)` (`test_onboarding_screen.py:17,23,29-39`), `use_keyboard_shortcuts(router)`
(`test_use_keyboard_shortcuts.py:120`, via the `flet.on_mounted` patch).

### a.3 Every `sys.path.insert` shim

- `tests/conftest.py:7-8` — absolute: `SRC = Path(__file__).resolve().parent.parent / "src"`,
  `sys.path.insert(0, str(SRC))` guarded by `if str(SRC) not in sys.path`. Robust; CWD-independent.
- `tests/test_phase5_regression.py:5` — `sys.path.insert(0, "src")` (relative; pytest-rootdir dependent).
- `tests/screens/test_usage_card.py:9` — `sys.path.insert(0, "src")` (relative).
- `tests/screens/test_onboarding_screen.py:6` — `sys.path.insert(0, "src")` (relative).
- `tests/components/test_high_ram.py:11` — `sys.path.insert(0, "src")` (relative; placed AFTER `import flet as ft`, line 9).
- `tests/services/test_update_service.py:10` — `sys.path.insert(0, "src")` (relative).
- `tests/services/test_version_sync.py:21` — `sys.path.insert(0, "src")` (relative).
- `tests/services/colab/test_session_ops.py:11` — `sys.path.insert(0, "src")` (relative).
- `tests/services/colab/test_terminal_client.py:13` — `sys.path.insert(0, "src")` (relative).
- `tests/services/colab/test_execution_env.py:12` — `sys.path.insert(0, "src")` (relative).
- `tests/services/colab/test_usage_ops.py:13` — `sys.path.insert(0, "src")` (relative).
- No shim in `tests/components/test_shortcuts_help.py`, `tests/hooks/test_use_keyboard_shortcuts.py`,
  `tests/screens/notebook/test_shortcut_actions.py` — these rely on `tests/conftest.py:7-8`.
  Mixed scheme (absolute conftest + relative per-file inserts) is redundant but harmless;
  duplicate inserts of the same path are idempotent-ish (relative `"src"` can duplicate on repeat —
  no guard — but only import-order noise, not a 1.0.3 risk).

### a.4 Version-sync guard tests (what pins they assert)

`tests/services/test_version_sync.py` (docstring lines 1-14 explains the build-11 phantom-update incident):
- `test_version_in_sync_everywhere` (`test_version_sync.py:28-49`): asserts
  `pyproject["project"]["version"] == APP_VERSION` (lines 36-39),
  `pyproject["tool"]["flet"]["build_number"] == APP_BUILD_NUMBER` (lines 40-43),
  and `uv.lock` contains `name = "collabshell"\nversion = "{APP_VERSION}"` (lines 45-49).
  Current values it pins: `APP_VERSION = "2.1.2"` (`src/core/constants.py:5`),
  `APP_BUILD_NUMBER = 12` (`src/core/constants.py:6`).
- `test_feed_never_ahead_of_app` (`test_version_sync.py:52-64`): asserts
  `version.json build_number <= APP_BUILD_NUMBER` (one-sided; lag OK, ahead forbidden).
  Current feed: `{"version": "2.1.1", "build_number": 11}` (`version.json:2-3`) — behind, passing by design.
- `test_workflow_defaults_in_sync` (`test_version_sync.py:67-77`): asserts the workflow contains
  `default: "2.1.2"` (line 70), `default: "12"` (line 73),
  `inputs.build_version || '2.1.2'` (line 76), `inputs.build_number || '12'` (line 77).
Companion guard: `tests/services/test_update_service.py:106-108`
(`test_changelog_has_entry_for_current_version`) asserts `notes_for(APP_VERSION)` is truthy;
`tests/test_phase5_regression.py:41-57` asserts the 2.1.2 changelog entry covers
High-RAM/usage-card/env/refresh/allocation/SSH and that `notes_for("9.9.9") == CHANGELOG["2.1.0"]`
(fallback = last-inserted dict value, lines 54-56).

### a.5 Fragility vs Flet 1.0.3 (property-default `None`→constant + child-reconciling)

Method limit: Flet 1.0.3 was NOT installed (venv holds 0.86.5); all 1.0.x behavior verdicts are
reasoned from the 0.3.8→0.3.9 wheel diff + PyPI metadata, marked UNVERIFIED where stated.

1. `ft.Control` / `ft.Divider` / `ft.Text` / `ft.Switch` / `ft.Container` isinstance checks
   (`test_shortcuts_help.py:16,32,35,43,48`; `test_high_ram.py:39,44,68,73,95,100`):
   LOW risk. These are core control classes, not deprecated properties; the 0.3.9 changelog's
   Flet-1.0 breakages are `TextField.border_color`, `SnackBar(duration)`, `run_task` sync callables,
   and `Clipboard()` registration — none is an isinstance target in tests. UNVERIFIED that
   `ft.Control` remains importable from the top level in 1.0.3 (no 1.0.3 wheel inspected).
2. `_chip_label` reads `chip.content.value` (`test_high_ram.py:17-18`): LOW risk. It reads a set
   value, not a default; a `None`→constant default change on `Container.content`/`Text.value`
   would not alter explicitly-constructed content. Survives unless `shape_chip` itself is
   refactored (source-side, not Flet-side).
3. `ft.Ref[ft.Switch]()` (`test_high_ram.py:35`) + `switches[0].label or ""` (line 49):
   LOW risk. `Ref` subscription and `Switch.label` default (`None` → `or ""` guard already
   normalizes any `None`→constant change either way).
4. `.controls` list walks (`test_high_ram.py:41,70,97`; `test_onboarding_screen.py:19,25,42`):
   LOW-MEDIUM risk. `controls: list` on layout controls is the stable 0.86 API and the 0.3.9
   diff shows the declarative component model (`@ft.component`, re-render diffing) persists
   into 1.0 (comment-only changes `extra_keys.py:27`, `frozen_support.py:43`, METADATA). Child
   reconciliation *inside* flet (frozen-subtree parent-chain drops, cf. `frozen_support.py:43`)
   affects live page trees, not these freshly-built offline controls. UNVERIFIED against 1.0.3.
5. Exact divider counts (`test_shortcuts_help.py:35,43,48` — `== 1`, `== 3`, `== 0`):
   MEDIUM fragility, but source-side not Flet-side: any added section in `build_help_body`
   breaks them; a Flet Divider-default change would not (they count instances, not values).
6. `flet.on_mounted` patch + `flet.controls.context` page mock
   (`test_use_keyboard_shortcuts.py:9,109-122`): HIGHEST test-side 1.0.3 risk.
   If 1.0.3 moves/renames `on_mounted` (hook API) or restructures `flet.controls.context`
   (the 0.3.9 `mobile_terminal.py:307` comment confirms Flet 1.0 changed service
   registration semantics for `Clipboard()`, proving adjacent lifecycle internals DID change),
   the `mock.patch("flet.on_mounted")` target or the `type(_flet_ctx.context).page` property
   can raise `AttributeError`. UNVERIFIED — needs a 1.0.3 import check
   (`python -c "import flet; print(flet.on_mounted)"` + `flet.controls.context` layout).
   The `MagicMock` page itself (`on_keyboard_event`) is src-hook surface, unaffected by Flet.
7. `httpx.MockTransport` injection (`test_update_service.py:17-32,75-88`): NO risk from 1.0.3;
   httpx is pinned at latest (see §d). `asyncio.run(...)` per test is stdlib.
8. `colab_cli` mocks (`test_session_ops.py`, `test_terminal_client.py`, `test_execution_env.py`,
   `test_usage_ops.py`): no Flet surface; 1.0.3-irrelevant. Their upstream pins
   (`google-colab-cli==0.7.4`, `jupyter-kernel-client==0.9.0`) are out of this audit's scope
   except as recorded in §b.
9. Source-text asserts (`inspect.getsource` in `test_phase5_regression.py:22-29,60-91`,
   `test_usage_card.py:45-50`, `test_high_ram.py:114-141`): immune to Flet version changes
   by construction (they read `src/` text), but brittle to any source refactor that renames
   `_refresh_shape_visibility`, `_on_gpu_model_change`, `V5E1`/`V6E1` strings, `"USAGE"`,
   or dialog `title`/`subtitle` params.
10. Coverage gap (not a fragility, a blind spot): NOTHING tests `terminal_panel.py`'s
    `MobileTerminal` construction or its private-internals use
    (`mt._terminal.on_mount`, `mt._terminal._lock/_pending_writes` at
    `src/screens/session/terminal_panel.py:340,252-253`), the per-copy `ft.Clipboard()`
    (`terminal_panel.py:607`), or `show_search/show_settings/scrollback/font_family` ctor kwargs
    (`terminal_panel.py:316-325`). These are exactly the APIs 0.3.9 had to change for Flet 1.0
    (see §c). A 1.0.3 upgrade without a terminal-panel test will fly blind on the riskiest file.

### a.6 Deleted-test stems (stale `.pyc` only, no source — for completeness)

Compiled caches with no on-disk `.py` (all under `tests/__pycache__/` unless noted):
`test_about_section`, `test_ad_gating`, `test_ads_cadence`, `test_ai_chats`, `test_ai_credits`,
`test_ai_display` (+ stray `tests/__pycache__`-level copy), `test_ai_engine`, `test_ai_entry_points`,
`test_ai_notebook`, `test_ai_panel_composer` (+ stray copy), `test_ai_reactivity`, `test_ai_recovery`,
`test_ai_router`, `test_ai_router_local`, `test_ai_terminal`, `test_ai_tools`, `test_app_paths`,
`test_billing_restore_refusal`, `test_channel_split`, `test_checkout_watcher`, `test_contrast`,
`test_empty_state`, `test_execution_prelude`, `test_fab_and_ai_sheet`, `test_flet_api_usage`
(+ stray copy), `test_history_reader`, `test_license_crypto`, `test_local_auth_gate`,
`test_mount_dialog_stack`, `test_notebook_orphan`, `test_prefs_restore`, `test_premium_channels`
(+ stray copy), `test_premium_credits`, `test_py312_compat`, `test_settings_ia`, `test_settings_tree`,
`test_storage_clear`, `test_storage_migration`, `test_tokens`, `test_zz_deliberately_broken`;
`tests/components/__pycache__/test_notebook_output`; `tests/services/colab/__pycache__/test_vm_ops`.
Also `scripts/__pycache__/probe_ai...pyc` with no `scripts/probe_ai.py` source. None are runnable;
`pytest` collects only the §a.1 files.

---

## (b) Pin table: pyproject / uv.lock / .flet / workflows / version.json

### b.1 `pyproject.toml` (full dependency + packaging record)

- `pyproject.toml:3` — `version = "2.1.2"`.
- `pyproject.toml:6` — `requires-python = ">=3.14"`.
- `pyproject.toml:8` — `flet>=0.86.5` (floor; allows 1.0.3 — resolver would jump).
- `pyproject.toml:9` — `flet-ads>=0.86.5`.
- `pyproject.toml:10` — `httpx>=0.28.1`.
- `pyproject.toml:11` — `flet-cli>=0.86.5; sys_platform == 'win32'`.
- `pyproject.toml:12` — `flet-desktop>=0.86.5; sys_platform == 'win32'`.
- `pyproject.toml:13` — `flet-terminal>=0.3.8` (floor; allows 0.3.9, which demands `flet>=1.0.1`).
- `pyproject.toml:14` — `google-colab-cli==0.7.4` (exact; comment lines 15-22 documents the
  upstream-tested `jupyter-kernel-client==0.9.0` combo + 3-way resolver).
- `pyproject.toml:23` — `jupyter-kernel-client==0.9.0` (exact).
- `pyproject.toml:24` — `rich>=15.0.0`.
- `pyproject.toml:27-30` — `[tool.flet] org = "ng.kiri"`, `product = "Colab Shell"`, `build_number = 12`.
- `pyproject.toml:33-37` — app `path = "src"`, boot `startup_message = "Initializing Collab Shell..."`.
- `pyproject.toml:39-46` — android `bundle_id = "ng.kiri.collabshell"`;
  `target_arch = ["arm64-v8a", "armeabi-v7a"]` (x86_64 dropped: pyzmq 27.2.0 4 KB-aligned libs;
  comment lines 42-45).
- `pyproject.toml:48-56` — AdMob `APPLICATION_ID = "ca-app-pub-5679949845754640~7138516733"`,
  `allowBackup = "false"`, INTERNET + ACCESS_NETWORK_STATE permissions.
- `pyproject.toml:58-60` — signing `key_store = "../../../../kiri_keystore.jks"`, `key_alias = "upload"`.
- `pyproject.toml:64-68` — dev group: `pytest`, `ruff`.
- `pyproject.toml:72-73` — ruff `extend-ignore = ["BLE001", "S110"]`.
- `scripts/check_elf_alignment.py:1-104` — full read. Pure stdlib
  (`struct`, `sys`, `tempfile`, `zipfile`, `pathlib`; `PT_LOAD = 1` line 23, `PAGE_16K = 16384`
  line 24, `ABI_64_BIT = {"arm64-v8a", "x86_64"}` line 25). No flet/httpx/rich imports;
  Flet-1.0.3-immune by construction. CI gate wiring: `build-all.yml:98,140`.

### b.2 `uv.lock` (resolved truth; header `version = 1`, `revision = 3`, `requires-python = ">=3.14"`)

| Package | Locked | Source stanza | Notes |
|---|---|---|---|
| `collabshell` | 2.1.2 (virtual) | `uv.lock:253-255` | deps + specifiers `uv.lock:256-285` mirror pyproject |
| `flet` | 0.86.5 | `uv.lock:390-404` | registry `https://pypi.org/simple` |
| `flet-ads` | 0.86.5 | `uv.lock:405+` | — |
| `flet-cli` | 0.86.5 | `uv.lock:417+` | win32-only per marker |
| `flet-desktop` | 0.86.5 | `uv.lock:436+` | win32-only per marker |
| `flet-terminal` | 0.3.8 | `uv.lock:449-457` | dep `{ name = "flet" }` only (`uv.lock:452-454`); sdist+wheel hashes recorded |
| `google-colab-cli` | 0.7.4 | `uv.lock:487+` | — |
| `jupyter-kernel-client` | 0.9.0 | `uv.lock:647+` | — |
| `httpx` | 0.28.1 | `uv.lock:545-553` | deps anyio/certifi/httpcore/idna |
| `rich` | 15.0.0 | `uv.lock:1084-1092` | deps markdown-it-py/pygments |
| `pytest`, `ruff` | dev group | `uv.lock` dev section | versions not enumerated here (out of scope) |

Lock is internally consistent: `collabshell 2.1.2` (`uv.lock:253-254`) matches
`pyproject.toml:3` + `APP_VERSION` (`src/core/constants.py:5`); no drift.

### b.3 `.flet/` listing (no pins — dev runtime state only)

- `.flet/README.md` — stock Flet dev-state readme (safe to delete, git-ignored).
- `.flet/.gitignore` — content: `*` (single line; everything ignored).
- `.flet/storage/data/colab-cli/history/*.jsonl` (5 files), `notebook_057efa.json`,
  `sessions.json` (+ `.lock`), `storage.json` (+ `.bak`), `token.json` — local run state
  of the app (`colab-cli` storage id), not packaging. No version/build pins anywhere under `.flet/`.

### b.4 `.github/workflows/build-all.yml` (full read; 315 lines)

- Version pins: `workflow_dispatch` inputs `build_version` default `"2.1.2"` (lines 10-12),
  `build_number` default `"12"` (lines 13-16); env `BUILD_VERSION: inputs.build_version || '2.1.2'`
  (line 25), `BUILD_NUMBER: inputs.build_number || '12'` (line 26) — the exact strings the
  version-sync guard asserts (`test_version_sync.py:70-77`).
- Toolchain pins: `UV_PYTHON: "3.14"` (line 24), `setup-python '3.14'` (line 74),
  `setup-java temurin 17` (lines 76-79 / 118-121), `actions/checkout@v4`, `astral-sh/setup-uv@v6`,
  `actions/setup-python@v5`, `actions/setup-java@v4`, `softprops/action-gh-release@v2`.
- Build commands pass `--build-version ${{ env.BUILD_VERSION }} --build-number ${{ env.BUILD_NUMBER }}`
  for apk (line 96), aab (line 138), windows (line 159), linux (line 228).
- ELF-alignment gate: `python scripts/check_elf_alignment.py build/apk/*.apk` (line 98),
  `... build/aab/*.aab` (line 140).
- Windows job additionally `uv pip install pillow` + generates `icon.ico` (lines 163-164),
  Inno Setup installer (lines 166-204). Linux job installs gtk/gstreamer/rpm/fpm deps
  (lines 222-226), builds deb+rpm+tar.gz (lines 230-305).
- No FletТова/httpx/rich version pins in the workflow (all flow from `uv.lock` via `uv run`).

### b.5 `version.json` (live feed, deliberately held back)

`version.json:2-3`: `{"build_number": 11, "version": "2.1.1", ...}` with
`github_url` (line 8) and `playstore_url` (line 9). Feed build 11 <= app build 12:
satisfies the one-sided `test_feed_never_ahead_of_app` invariant
(`test_version_sync.py:52-64`). Full content read (10 lines).

---

## (c) flet-terminal delta 0.3.8 → 0.3.9 + usage sites in `src/`

### c.1 Version history (PyPI fact: `https://pypi.org/pypi/flet-terminal/json`)

13 releases, first `0.1.0`, latest `0.3.9`:
`0.1.0`, `0.2.0`, `0.2.1`, `0.2.2`, `0.3.1`, `0.3.2`, `0.3.3`, `0.3.4`, `0.3.5`, `0.3.6`,
`0.3.7`, `0.3.8` (2026-08-23), `0.3.9` (2026-09-23, wheel uploaded
`2026-09-23T14:09:15Z`, 33,115 bytes vs 31,975 for 0.3.8). Neither yanked.
`0.3.8` metadata: `requires_python >=3.14`, `requires_dist ['flet>=0.86.5']`.
`0.3.9` metadata: `requires_python >=3.14`, `requires_dist ['flet>=1.0.1']` —
**0.3.9 forces the Flet 1.0.x upgrade; it cannot be adopted while staying on 0.86.5.**
(Direct `requires_dist` for latest read as `['flet>=1.0.1']` from
`https://pypi.org/pypi/flet-terminal/json`.)

### c.2 0.3.8 → 0.3.9 wheel diff (unpacked `w038/` vs `w039/`; `diff -ru`)

Identical files (no diff): `__init__.py`, `themes.py`, `tokens.py`,
`flutter/flet_terminal/lib/flet_terminal.dart`, `lib/src/extension.dart`,
`lib/src/flet_terminal.dart` — **no Dart-side control change**; the delta is Python-side
Flet-1.0 adaptation. (`pubspec.yaml` version `0.3.8`→`0.3.9`, `flet: ^0.86.5`→`^1.0.0`.)

`CHANGELOG.md` 0.3.9 entry (5 bullets, `w039/.../CHANGELOG.md:1-7`):
1. Targets Flet 1.0.1: Python floor `flet>=1.0.1`, Dart pubspec `flet: ^1.0.0`.
2. Pending-write flush fix — Flet 1.0's `run_task` rejects sync callables, so queued
   `send_bytes` writes re-queued forever on 0.3.8.
3. One shared `Clipboard` service instead of a new instance per copy.
4. New `MobileTerminal` API: `on_mount` property, `ready`, `pending_count`,
   `clear_pending()`, `flush()`, `set_on_unmount()` — no more `_terminal` internals.
5. Search-bar `border_color` → `border=OutlineInputBorder(...)`; example SnackBar
   `duration` → `ft.Duration` (deprecated/changed in Flet 1.0).

Per-file hunks:
- `terminal.py` (`w039/.../terminal.py:1,91-104`): added `import inspect`; flush now branches
  `inspect.iscoroutinefunction(task_fn)` → `page.run_task(...)`, else calls `task_fn(*arg_list)`
  directly (comment: "Flet 1.0's run_task rejects sync callables with TypeError, which used to
  re-queue this write forever"); log text "run_task failed" → "flush failed".
- `mobile_terminal.py`: new `self._clipboard: ft.Clipboard | None = None` (line ~66);
  copy path reuses it (lines ~304-310, comment: "every Clipboard() construct would auto-register
  another instance on the page (Flet 1.0)"); new members `on_mount` property+setter (via `thaw`),
  `ready`, `pending_count`, `clear_pending()`, `flush()`, `set_on_unmount()`.
- `search_bar.py:49`: `border_color="#45475A"` →
  `border=ft.OutlineInputBorder(side=ft.BorderSide(color="#45475A"))`.
- `extra_keys.py:27`, `frozen_support.py:43`, METADATA long description: comment-only
  "Flet 0.86's" → "Flet 1.0's" (declarative model + `thaw()` narrative unchanged).

### c.3 `flet_terminal` / `Terminal` usage in `src/` (grep, with file:line)

Only ONE file imports the package: `src/screens/session/terminal_panel.py:30`
(`from flet_terminal import BUILTIN_THEMES, MobileTerminal`). All call sites below are in it
except where noted:

- `:98` — `self.mt: MobileTerminal | None = None` (per-tab widget handle).
- `:232`, `:255` — `entry.mt.send_bytes(data)` / `mt.send_bytes(chunk)` (the path 0.3.9's
  flush fix repairs under Flet 1.0 — on 0.3.8+1.0.x queued writes re-queue forever).
- `:316-325` — ctor: `MobileTerminal(show_search=False, show_settings=False, scrollback=10000,
  font_family="JetBrains Mono", font_size=ps.zoom,
  theme=BUILTIN_THEMES.get(_active_theme_name(page)), auto_focus=False, expand=True)`.
- `:322`, `:473` — `BUILTIN_THEMES.get(...)` / `list(BUILTIN_THEMES.keys())` (theme follow + cycle).
- `:328`, `:581` — `mt.toggle_cursor_blink()` (ctor-time inherit + FAB toggle).
- `:334` — `mt.set_on_bytes(handlers["on_bytes"])`; `:335` — `mt.on_data = ...` (dual wiring);
  `:338` — `mt.on_resize = handlers["on_resize"]`.
- `:340` — `mt._terminal.on_mount = handlers["on_mount"]` — PRIVATE internal; 0.3.9 replaces
  with public `mt.on_mount = ...`. Must change on upgrade.
- `:252-253` — `with mt._terminal._lock: mt._terminal._pending_writes.clear()` — PRIVATE
  internals; 0.3.9 replaces with `mt.clear_pending()`. Must change on upgrade.
- `:344` — `mt.on_shortcut = lambda e: on_shortcut(e.shortcut)` (0.3.8+ API; unchanged in 0.3.9).
- `:341-342`, `:510` — comments pinning "flet-terminal ≥0.3.8" shortcut behavior.
- `:352`, `:495` — `mt.focus()` (desktop-gated initial + toolbar refocus).
- `:537`, `:625` — `entry.mt.paste()` (shortcut dispatch + FAB action).
- `:556`, `:664` — `mt.set_theme(name)` (FAB/settings + light-dark follow).
- `:560`, `:567`, `:574` — `mt.zoom_in()` / `mt.zoom_out()` / `mt.reset_zoom()`;
  `:563`, `:570`, `:577`, `:637` — `entry.mt.font_size` reads.
- `:588` — `mt.toggle_search() if mt.show_search != want else None` (`show_search` read).
- `:601`, `:608` — `await entry.mt.get_selection_async()` / `entry.mt.clear_selection()`.
- `:607` — `await ft.Clipboard().set(text)` — constructs a NEW `Clipboard` per copy: the exact
  pattern 0.3.9 eliminated inside the package for Flet 1.0 ("auto-register another instance
  on the page"). Source-side instance, not the package's — needs a 1.0.3 check (UNVERIFIED
  whether per-call `Clipboard()` breaks or merely leaks under 1.0.3).
- `:655-656`, `:668` — `ft.on_mounted(_on_mount)` / `ft.use_effect(...)` lifecycle
  (same hook family as the highest-risk test mock in §a.5.6).
- `:646-653` — `_on_mount` sets `app_state.terminal_reconnect`; `_cleanup` clears it.
- `:814-829` — keyed `_TerminalHost`/`Container` (`key=ft.ValueKey(...)`) — reconciler-sensitive;
  stable keys already in place, good for 1.0.

Supporting (non-importing) references:
- `src/core/state.py:39` — `terminal_settings_rev: int = 0` (FAB-rebuild bump);
  `terminal_panel.py:547` bumps it (`_changed_settings`); `src/screens/session/__init__.py:234`
  subscribes `[session_name, cells_version, active_tab, state.terminal_settings_rev]`.
- `src/core/state.py:42` — `terminal_reconnect = None` (resume hook slot).
- `src/screens/session/fab_menu.py:51-58,66-125` — terminal settings menu (theme presets
  Dracula/JetBrains Dark/Matrix Green/Colab Light, zoom, blink, search) driven by the
  `term_settings` dict — no `flet_terminal` import; survives the upgrade untouched.
- Comments only: `src/core/shortcuts.py:8`, `src/screens/session/__init__.py:40,204`,
  `src/screens/session/fab_menu.py:51`, `terminal_panel.py:1-19` docstrings.

Upgrade consequence summary: adopting 0.3.9 REQUIRES Flet ≥1.0.1 (metadata floor), which is
the whole 1.0.3 migration; staying on 0.3.8 + Flet 1.0.3 keeps the two private-internal uses
(`:340`, `:252-253`) working only if 1.0.3 preserves `_terminal`/`_lock`/`_pending_writes`
layout — UNVERIFIED. The 0.3.9 public replacements (`on_mount`, `clear_pending`) exist
precisely because consumers should stop touching those internals.

### c.4 Flet satellite packages (PyPI facts, same read-only method)

- `flet-ads` latest `1.0.3` (`requires_python >=3.10`, `requires_dist ['flet==1.0.3']`) —
  lock holds 0.86.5; upgrade to 1.0.3 is lockstep with Flet.
- `flet-cli` latest `1.0.3` (deps `flet==1.0.3`, `flet-platform-assets==1.0.3`, watchdog,
  packaging, qrcode, cookiecutter, `rich>=13.0.0`, …) — lock holds 0.86.5 (win32-only).
- `flet-desktop` latest `1.0.3` (deps `flet==1.0.3`, `rich>=13.0.0`) — lock holds 0.86.5 (win32-only).
- `flet-web` latest `1.0.3` (deps `flet==1.0.3`, fastapi, uvicorn) — not in our dependency set.

---

## (d) httpx / rich verdicts (with PyPI facts)

### httpx: NO UPGRADE NEEDED (already at latest stable)

- PyPI fact (`https://pypi.org/pypi/httpx/json`): `info.version = "0.28.1"`.
  Numeric sort of all release keys puts `0.28.1` at top among stable releases; the only newer
  keys are `1.0.dev1`…`1.0.dev6` pre-releases (6 dev tags, not stable).
- Lock: `httpx 0.28.1` (`uv.lock:545-553`); floor `httpx>=0.28.1` (`pyproject.toml:10`).
- Flet 1.0.3 still needs `httpx>=0.28.1` (`platform_system != "Emscripten"` —
  from `https://pypi.org/pypi/flet/1.0.3/json`, full `requires_dist` in §e.1).
  Our lock satisfies the 1.0.3 floor exactly. `UpdateService` uses
  `httpx.AsyncClient(timeout=4.0, follow_redirects=True)` (`src/services/update_service.py:60`);
  no API change involved.

### rich: NO UPGRADE NEEDED (already at latest)

- PyPI fact (`https://pypi.org/pypi/rich/json`): `info.version = "15.0.0"`;
  `"15.0.0" in releases` is True; numeric sort top-8 =
  `15.0.0, 14.3.4, 14.3.3, 14.3.2, 14.3.1, 14.3.0, 14.2.0, 14.1.0`.
  (Caveat: the raw `releases` dict's insertion order ends at `9.9.0` — order is NOT sorted;
  `info.version` + numeric max agree on 15.0.0.)
- Lock: `rich 15.0.0` (`uv.lock:1084-1092`); floor `rich>=15.0.0` (`pyproject.toml:24`).
  `flet-desktop 1.0.3` / `flet-cli 1.0.3` need only `rich>=13.0.0` — satisfied with headroom.

---

## (e) Claim provenance (every material claim → file:line or PyPI fact)

### e.1 PyPI facts (all via venv python + urllib, 2026-10-03)

- `flet` latest `1.0.3` (`https://pypi.org/pypi/flet/json` → `info.version`); 88 releases from
  `0.1.0` to `1.0.3`; tail `0.86.4, 0.86.5, 0.9.0, 1.0.0, 1.0.0.dev0, 1.0.0.dev2, 1.0.1, 1.0.2, 1.0.3`.
- `flet 1.0.3` full `requires_dist` (`https://pypi.org/pypi/flet/1.0.3/json`):
  `flet-cli==1.0.3; extra == "cli"`, `flet-web==1.0.3; extra == "web"`,
  `oauthlib>=3.2.2; platform_system != "Emscripten"`, `httpx>=0.28.1; platform_system != "Emscripten"`,
  `repath>=0.9.0`, `msgpack>=1.1.0`, `typing-extensions; python_version < "3.11"`,
  `flet-cli==1.0.3; extra == "all"`, `flet-web==1.0.3; extra == "all"`,
  `flet-desktop==1.0.3; extra == "all"`, `flet-cli==1.0.3; extra == "cli"`,
  `flet-desktop==1.0.3; extra == "desktop"`, `flet-web==1.0.3; extra == "web"`,
  `pytest>=7.2.0; extra == "test"`, `pytest-asyncio>=1.1.0; extra == "test"`,
  `numpy>=2.2.0; extra == "test"`, `pillow>=10.3.0; extra == "test"`,
  `scikit-image>=0.25.2; extra == "test"`.
  `requires_python >=3.10`; wheel uploaded `2026-09-30T02:13:31Z` (`flet-1.0.3-py3-none-any.whl`);
  not yanked; 2 release files.
- `flet-terminal`: §c.1 (`https://pypi.org/pypi/flet-terminal/json` + `/0.3.8/json` + `/0.3.9/json`).
- `httpx`, `rich`: §d (`https://pypi.org/pypi/httpx/json`, `https://pypi.org/pypi/rich/json`).
- Satellites: §c.4 (`https://pypi.org/pypi/flet-ads|flet-cli|flet-desktop|flet-web/json`).

### e.2 Repo facts → locations

- All test claims: file:line citations in §§a.1-a.6 point at the working-tree files read in full.
- All pyproject claims: `pyproject.toml:3-73` (cited per line in §b.1).
- All lock claims: `uv.lock:253-285` (collabshell), `:390-404` (flet), `:405+` (flet-ads),
  `:417+` (flet-cli), `:436+` (flet-desktop), `:449-457` (flet-terminal), `:487+`
  (google-colab-cli), `:545-553` (httpx), `:647+` (jupyter-kernel-client), `:1084-1092` (rich).
- Workflow claims: `.github/workflows/build-all.yml:10-26,66-140,150-228,307-314` (§b.4).
- `.flet` claims: `.flet/README.md`, `.flet/.gitignore` (content `*`), `.flet/storage/data/colab-cli/*`.
- Terminal usage: `src/screens/session/terminal_panel.py` lines cited in §c.3; state
  `src/core/state.py:39,42`; FAB `src/screens/session/fab_menu.py:51-58,66-125`;
  session wiring `src/screens/session/__init__.py:40,204,234`.
- Wheel diff: `audit-flet-103/terminal-diff/w038/` vs `w039/` (§c.2).

### e.3 UNVERIFIED items (could not be checked document-only / without installing 1.0.3)

1. Whether `ft.Control`, `ft.Divider`, `ft.Text`, `ft.Switch`, `ft.Container`, `ft.Ref`,
   `ft.Clipboard`, `flet.on_mounted`, `flet.controls.context.page`, `ft.use_effect`,
   `ft.observable`, `ft.component` keep their 0.86 import paths/signatures/defaults in 1.0.3.
2. Whether `Text(value=None)`-style defaults changed `None`→constant anywhere tests depend on
   (tests read set values, so exposure is minimal — but not proven).
3. Whether 0.3.8's `_terminal._lock/_pending_writes/on_mount` layout survives under Flet 1.0.3
   (relevant only if staying on 0.3.8; 0.3.9 removes the need).
4. Whether per-call `ft.Clipboard()` (`terminal_panel.py:607`) breaks vs merely leaks on 1.0.3.
5. Contents/intent of the ~40 deleted test modules (only `.pyc` stems survive; §a.6).
6. Exact `pytest`/`ruff` versions in the dev group (not enumerated; out of scope).

---

## Bottom line for the 1.0.3 migration (no implementation done)

1. `httpx` (0.28.1) and `rich` (15.0.0) are already at PyPI latest stable — no action.
2. `flet-terminal` 0.3.9 is a pure Flet-1.0 adaptation (no Dart change) and its floor is
   `flet>=1.0.1`: the terminal upgrade IS the Flet upgrade. On the way, replace the two
   private-internal uses (`terminal_panel.py:340` → `mt.on_mount`; `:252-253` →
   `mt.clear_pending()`), re-check the per-copy `ft.Clipboard()` (`:607`), and confirm the
   `MobileTerminal(...)` kwargs in `:316-325` against 1.0.3.
3. Test-suite risk concentrates in ONE file: `tests/hooks/test_use_keyboard_shortcuts.py:105-122`
   (`flet.on_mounted` + `flet.controls.context` page mock). Everything else `ft.*`-shaped in
   tests is low-risk isinstance/`.controls` reads over offline-built controls.
4. Blind spot: zero tests cover `terminal_panel.py` — the file with the most 1.0-sensitive calls.
5. Pins that must move together (guarded by `tests/services/test_version_sync.py:28-77` for
   app version, but NOT guarded for Flet): `pyproject.toml:8-13` floors
   (`flet`, `flet-ads`, `flet-cli`, `flet-desktop`, `flet-terminal`) + `uv.lock` resolutions.
   `version.json` (11/2.1.1) stays behind the app (12/2.1.2) by design — do not "fix" that lag.

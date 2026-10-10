# CollabShell — Flet 0.86.5 → 1.0.3 Master Change Inventory

> **Purpose:** single source of truth every Flet upgrade step MUST read.
> **Rule:** document-first, no assumptions; `version.json` FROZEN; match upstream.
> **Upstream repo:** `flet-dev/flet` (monorepo: flet, flet-ads, flet-cli, flet-desktop).
> **Raw release bodies:** `audit-flet-103/upstream-notes/v0.86.5.md`, `v1.0.0.md` (66,878 chars, full), `v1.0.1.md`, `v1.0.2.md`, `v1.0.3.md`.
> **Area audits:** `audit-flet-103/findings/upstream-truth.md` · `ui-usage-surface.md` · `core-services-usage.md` · `tests-packaging-deps.md` (+ `terminal-diff/w038` vs `w039`).

---

## 1. Version / release truth (verified 2026-10-03)

| Tag | GitHub published | PyPI flet upload | Lag |
|---|---|---|---|
| v0.86.5 | 2026-08-01 | 2026-08-01 | ~16 s |
| v1.0.0 | 2026-09-14 | 2026-09-14 | ~17 s |
| v1.0.1 | 2026-09-22 | 2026-09-22 | ~15 s |
| v1.0.2 | 2026-09-28 | 2026-09-28 | ~20 s |
| v1.0.3 | 2026-09-30 | 2026-09-30 | ~15 s |

- Companions track 1:1: flet-ads, flet-cli, flet-desktop all latest **1.0.3**, same 5 versions, uploads ~15–60 s after core.
- v1.0.1/1.0.2/1.0.3 bodies contain NO Breaking-changes section (Improvements/Bug fixes only). ALL breaking items are v1.0.0.
- **flet-terminal: 13 releases; 0.3.8 (2026-08-23, requires flet>=0.86.5) → 0.3.9 (2026-09-23, requires flet>=1.0.1). 0.3.9 FORCES the Flet 1.0.x upgrade — cannot adopt while on 0.86.5.**
- **httpx==0.28.1: latest, no upgrade** (Flet 1.0.3 floor is `httpx>=0.28.1`; lock matches).
- **rich==15.0.0: latest, no upgrade.**
- Core dep delta 0.86.5→1.0.3: NO new third-party floors (`oauthlib>=3.2.2`, `httpx>=0.28.1`, `repath>=0.9.0`, `msgpack>=1.1.0` unchanged). Only addition in the whole set: `flet-cli` gains **`flet-platform-assets==1.0.3`** (icon/splash generator replacing flutter_launcher_icons/flutter_native_splash; Pillow only).
- `requires_python >=3.10` unchanged. Ours is `>=3.14` — no conflict.

## 2. Our baseline (verified)

- `pyproject.toml`: `flet>=0.86.5`, `flet-ads>=0.86.5`, `flet-cli>=0.86.5` + `flet-desktop>=0.86.5` (win32-only markers), `flet-terminal>=0.3.8`, `httpx>=0.28.1`, `rich>=15.0.0`.
- `uv.lock`: flet 0.86.5, flet-terminal 0.3.8, httpx 0.28.1, rich 15.0.0.
- `[tool.flet]` table (lines 27-60): only `boot_screen.startup_message` set; NO rename-sensitive keys (no splash/icon_bgcolor), NO exclusion keys, `target_arch = ["arm64-v8a", "armeabi-v7a"]` + pyzmq 16KB comment intact.

## 3. Every breaking change (v1.0.0, all via PR #6693 unless noted) + our exposure

| # | Upstream removal/change | Our exposure (verified by grep) | Verdict |
|---|---|---|---|
| B1 | Remove `Page.go()` → `Page.push_route()` | ZERO call sites in src/ or tests/ | SAFE |
| B2 | Remove `app()`/`app_async()` → `run()`/`run_async()`; remove `run(target=)` → `main=` | `ft.run` used in main.py only (param name TBD in diff pass) | CHECK param |
| B3 | Remove `ElevatedButton` → `Button` | ZERO usages | SAFE |
| B4 | Remove `ConstrainedControl` → `LayoutControl` | Never subclassed | SAFE |
| B5 | Remove non-underscored `Colors` aliases → underscored | Only canonical names used (75+ sites, all underscored) | SAFE |
| B6 | Remove 5 Page service accessors → instantiate classes | Never referenced | SAFE |
| B7 | Remove `Page.launch_url/can_launch_url/close_in_app_web_view` | All 7 sites use `ft.UrlLauncher().launch_url(url)` (signature UNCHANGED in 1.0.3) | SAFE |
| B8 | Remove `DragTargetEvent.x/y/offset`, `Video.show_controls/playlist_*` | No Video/DragTarget usage | SAFE |
| B9 | Remove `FletApp.show_app_startup_screen*` → `boot_screen_options` | Not referenced | SAFE |
| B10 | Remove `--clear-cache` → `flet clean` | Not used | SAFE |
| B11 | Remove legacy `[tool.flet.app.boot_screen]` fallback → `[tool.flet.boot_screen]` | Table uses `[tool.flet.app.boot_screen]` TODAY — MUST migrate key | **MIGRATE** |
| B12 | Remove `""` widget-state key → `"default"`/`ControlState.DEFAULT` | Never referenced | SAFE |
| B13 | Remove `flet.utils.cleanup_path()` | Never referenced | SAFE |
| B14 | **`InputBorder` enum → class hierarchy** | Never referenced directly — BUT 17 `border_radius=` + 2 `border_color=` sites use the deprecated shorthands (removal 1.3.0, still working in 1.0.3) | **MIGRATE (17+2 sites)** |
| B15 | Property defaults `None` → constants (read-path only, rendering unchanged) | Tests read `.value`/`.controls` — low risk; `test_use_keyboard_shortcuts` page-mock is highest risk | VERIFY in diff pass |
| B16 | Splash renames (`icon_bgcolor`→`icon_background` etc., old names still read) | No splash keys in our table | SAFE (soft) |
| B17 | iOS signing precedence flip | No iOS keys in our table | SAFE |
| B18 | `init()` registration timing (v1.0.1): fields set in `init()` now serialize; `self.page` unavailable in `init()` | No `init()` overrides in our code (reactive `use_*` pattern, not services) — VERIFY zero `def init` in src/ | VERIFY |
| B19 | Children matched by control id (v1.0.3) + equal-child reconciling (v1.0.0) | Benefits us (focus/scroll/event fixes); our per-render lambdas masked the bug anyway | POSITIVE |
| B20 | Hard-exit contract: `atexit`/`__del__`/unflushed writes NOT guaranteed on exit | `main.py` atexit cleanup + storage flush path must be checked | **CHECK** |
| B21 | `UrlTarget.BLANK` `"blank"`→`"_blank"` | `url` param usage unchanged; check any `UrlTarget` refs | VERIFY |
| B22 | Build default-excludes (`.venv`/`.git`/`.flet`/`__pycache__`/dotfiles no longer packaged) | **No exclusion keys in our table — `.env` in app root would now be EXCLUDED by default.** Check for dotfiles we ship. | **CHECK** |
| B23 | Web CDN default (71MB→19MB), CanvasKit/Pyodide handling | Affects web builds only; we ship Android/desktop | NOTE |

## 4. Deprecations (removal 1.3.0, PR #6773) — all still working in 1.0.3

- `InputBorder.OUTLINE/UNDERLINE/NONE` → `OutlineInputBorder()` etc. (not used by us).
- `border_radius/border_width/border_color/focused_border_width/focused_border_color` on TextField/Dropdown/DropdownM2/CupertinoTextField → `border=` (17+2 sites — the H1/H2 migration).
- `DropdownM2.border_radius` → `menu_border_radius` (DropdownM2 never used by us).

## 5. flet-terminal 0.3.8 → 0.3.9 (wheel diff, Python-side Flet-1.0 adaptation, no Dart change)

- Requires `flet>=1.0.1` — lockstep with core upgrade.
- Fixes: `run_task` sync-callable rejection (was infinite re-queue), shared `Clipboard` service (was per-copy instance), new `MobileTerminal` API (`on_mount`, `ready`, `pending_count`, `clear_pending()`, `flush()`, `set_on_unmount()` — replaces `_terminal` private internals), search-bar `border_color` → `OutlineInputBorder`, example SnackBar `ft.Duration`.
- Our exposure: SOLE importer is `terminal_panel.py:30`; private-internal uses at `:340, :252-253` (replaced by 0.3.9 API); per-copy `ft.Clipboard()` at `:607` (now shared service). **Zero tests cover terminal_panel.py — highest-risk file.**

## 6. Audit instructions (all sub-agents)

Same 6-section format as the colab-cli audit (ADD / REMOVE / AFFECT / IMPROVE / VERIFY / TRACK) into `audit-flet-103/findings/<area>.md`. Every claim needs our file:line + upstream file:line (venv 0.86.5 baseline + 1.0.3 probe or release-note section). UNVERIFIED where applicable, never guessed.

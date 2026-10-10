# Flet 0.86.5 → 1.0.3 — Upstream Truth Inventory

> DOCUMENT-ONLY research. No file under `src/`, `tests/`, `scripts/`, `pyproject.toml`, `uv.lock` was touched.
> Raw release bodies: `audit-flet-103/upstream-notes/<tag>.md` (full, untruncated, via `gh api repos/flet-dev/flet/releases/tags/<tag> --jq .body`).
> flet-terminal release stubs: `audit-flet-103/upstream-notes/flet-terminal/<tag>.md`.
> PyPI facts: read-only GETs to `https://pypi.org/pypi/<pkg>/json` via the project venv python + `urllib` (no installs).
> Collection date: 2026-10-03. Every claim cites its source. Anything not directly observed is marked **UNVERIFIED**.

---

## (a) Version / release truth table

### GitHub releases (`flet-dev/flet`) vs PyPI uploads (`flet` package)

| Tag | GitHub `published_at` | PyPI `flet` upload times (sdist + wheel) | Lag GH→PyPI |
|---|---|---|---|
| `v0.86.5` | 2026-08-01T16:51:08Z | 2026-08-01T16:51:24Z, 16:51:26Z | ~16–18 s |
| `v1.0.0` | 2026-09-14T23:00:22Z | 2026-09-14T23:00:39Z, 23:00:41Z | ~17–19 s |
| `v1.0.1` | 2026-09-22T20:24:31Z | 2026-09-22T20:24:46Z, 20:24:47Z | ~15–16 s |
| `v1.0.2` | 2026-09-28T19:19:32Z | 2026-09-28T19:19:52Z, 19:19:53Z | ~20–21 s |
| `v1.0.3` | 2026-09-30T02:13:16Z | 2026-09-30T02:13:31Z, 02:13:33Z | ~15–17 s |

Sources: `gh api repos/flet-dev/flet/releases?per_page=100` (tag/date list); per-version PyPI JSON `upload_time_iso_8601`.
Raw bodies: `upstream-notes/v0.86.5.md` (18 lines), `upstream-notes/v1.0.0.md` (109 lines / 66,878 chars — saved whole),
`upstream-notes/v1.0.1.md` (18 lines), `upstream-notes/v1.0.2.md` (33 lines), `upstream-notes/v1.0.3.md` (17 lines).

### Companion packages track `flet` 1:1 (PyPI `info.version` = latest)

| PyPI package | Latest | 0.86.5 uploaded | 1.0.0 uploaded | 1.0.1 uploaded | 1.0.2 uploaded | 1.0.3 uploaded |
|---|---|---|---|---|---|---|
| `flet` | 1.0.3 | 2026-08-01T16:51:24Z | 2026-09-14T23:00:39Z | 2026-09-22T20:24:46Z | 2026-09-28T19:19:52Z | 2026-09-30T02:13:31Z |
| `flet-ads` | 1.0.3 | 2026-08-01T16:51:42Z | 2026-09-14T23:01:02Z | 2026-09-22T20:25:06Z | 2026-09-28T19:20:08Z | 2026-09-30T02:13:49Z |
| `flet-cli` | 1.0.3 | 2026-08-01T16:51:28Z | 2026-09-14T23:00:45Z | 2026-09-22T20:24:50Z | 2026-09-28T19:19:55Z | 2026-09-30T02:13:35Z |
| `flet-desktop` | 1.0.3 | 2026-08-01T16:51:32Z | 2026-09-14T23:00:48Z | 2026-09-22T20:24:54Z | 2026-09-28T19:19:58Z | 2026-09-30T02:13:38Z |

Source: PyPI JSON per package (full version lists confirm no gaps: `flet-ads` 42 versions, `flet-cli`/`flet-desktop` 53 each,
all containing 0.86.5 → 1.0.0 → 1.0.1 → 1.0.2 → 1.0.3; `flet` 88 versions incl. `1.0.0.dev0`, `1.0.0.dev2` pre-releases).
Each version ships 2 files (sdist + wheel). Companion uploads land ~15–60 s after the matching `flet` upload.

### Dependency floor delta 0.86.5 → 1.0.3 (PyPI `requires_dist`, exact)

`flet==1.0.3` (`requires_python: >=3.10`, unchanged from 0.86.5):

```
flet-cli==1.0.3; extra == "cli"
flet-web==1.0.3; extra == "web"
oauthlib>=3.2.2; platform_system != "Emscripten"
httpx>=0.28.1; platform_system != "Emscripten"
repath>=0.9.0
msgpack>=1.1.0
typing-extensions; python_version < "3.11"
flet-cli==1.0.3; extra == "all"
flet-web==1.0.3; extra == "all"
flet-desktop==1.0.3; extra == "all"
flet-cli==1.0.3; extra == "cli"
flet-desktop==1.0.3; extra == "desktop"
flet-web==1.0.3; extra == "web"
pytest>=7.2.0; extra == "test"
pytest-asyncio>=1.1.0; extra == "test"
numpy>=2.2.0; extra == "test"
pillow>=10.3.0; extra == "test"
scikit-image>=0.25.2; extra == "test"
```

Source: `https://pypi.org/pypi/flet/1.0.3/json` (`info.requires_dist`, verbatim, order preserved).
`flet==0.86.5` is byte-identical except every `==0.86.5` pin reads `==1.0.3` — i.e. **no new third-party floors in core**
(`oauthlib>=3.2.2`, `httpx>=0.28.1`, `repath>=0.9.0`, `msgpack>=1.1.0` all unchanged).

`flet-cli` delta (only material dependency change in the whole set):

```
# 0.86.5                              # 1.0.3 (ADDED line)
flet==0.86.5                 →        flet==1.0.3
                                      flet-platform-assets==1.0.3      ← NEW
watchdog>=4.0.0                       watchdog>=4.0.0                  (unchanged)
packaging>=25.0                       packaging>=25.0                  (unchanged)
qrcode>=7.4.2                         qrcode>=7.4.2                    (unchanged)
tomli>=1.1.0; python_version < "3.11" (unchanged)
cookiecutter>=2.6.0                   (unchanged)
binaryornot<0.5                       (unchanged)
chardet<6                             (unchanged)
rich>=13.0.0                          (unchanged)
flet-mcp; extra == "mcp"              (unchanged)
```

Source: `https://pypi.org/pypi/flet-cli/0.86.5/json` vs `/flet-cli/1.0.3/json`.
The new `flet-platform-assets==1.0.3` pin corresponds to the v1.0.0 release note:
"`flet build` generates app icons and splash screens itself, replacing `flutter_launcher_icons` and
`flutter_native_splash`… generation now runs through a new **`flet-platform-assets`** package (Pillow only, no other dependencies)"
(Source: v1.0.0 body, Improvements section, @FeodorFitsner).

`flet-desktop` delta: only `flet==0.86.5` → `flet==1.0.3`; `rich>=13.0.0` unchanged.
Source: `https://pypi.org/pypi/flet-desktop/0.86.5/json` vs `/1.0.3/json`.
`flet-ads` delta: only `flet==0.86.5` → `flet==1.0.3`.
Source: `https://pypi.org/pypi/flet-ads/0.86.5/json` vs `/1.0.3/json`.

---

## (b) BREAKING CHANGES — exact upstream quotes

All 20 items below are from the **`### Breaking changes`** section of the **v1.0.0** release body
(`upstream-notes/v1.0.0.md`, lines 35–56). v1.0.1 / v1.0.2 / v1.0.3 bodies contain **no** `Breaking changes`
section (only Improvements / Bug fixes / Other changes) — verified by reading all three files in full.
v0.86.5 body likewise has no breaking section (Bug fixes + Improvements only).

> Quoting convention: each bullet starts with the release body's exact sentence(s); bracketed notes after `—` are
> analyst cross-references, not upstream text.

* **Splash renames + splash sizing.** "Three keys under `[tool.flet.splash]` describe the Android 12 splash icon and now say so: `icon_bgcolor` becomes `icon_background`, `icon_dark_bgcolor` becomes `icon_dark_background`, and `android_12_fit` becomes `icon_fit`. All three were undocumented, and the former names are still read so existing configuration keeps working. Every key under `[tool.flet.splash]` now also accepts a per-platform override at `[tool.flet.<platform>.splash]`, which previously only the colours did. Separately, when no splash image is supplied the splash falls back to `icon.png` — and since an app icon fills its canvas by design, it was being drawn at full size, which made the splash artwork 67% larger than before. It is now framed for the splash, as it always effectively was when the default icon carried its own padding. An explicit `splash.png` is still used exactly as supplied, and opaque artwork is never resized on either path — including on the Android 12 splash icon, which previously shrank it into the middle of the circle instead of letting its colour bleed past, unlike the equivalent icon rule" — old names still accepted (soft break), but default-icon apps see a smaller splash. (Source: v1.0.0 Breaking changes, @FeodorFitsner)

* **`InputBorder` enum → class hierarchy.** "**`InputBorder` is a class hierarchy instead of an enum**, so enum-shaped usage no longer works: `InputBorder` is not iterable, its members have no `.value` or `.name`, and `InputBorder.OUTLINE is InputBorder.OUTLINE` is now `False` because each access returns a new instance — compare with `==`. Assigning a border is unaffected; see the deprecations below. Rendering changes as well: a border with no explicit `side` now takes its color and weight from the Material theme per state instead of always painting black, so dark mode and custom themes work; an underline finally honors its `border_radius`; `DropdownM2`'s open menu is shaped by the new `menu_border_radius` rather than by the field's radius; and on `CupertinoTextField`, `NoInputBorder()` now actually removes the border while an outline without a `side` keeps the native iOS one. See the [InputBorder class hierarchy](/docs/updates/breaking-changes/v1-0-0/inputborder-class-hierarchy) guide ([#6773](https://github.com/flet-dev/flet/pull/6773))" (Source: v1.0.0 Breaking changes, @ndonkoHenri)

* **Property defaults `None` → constants.** "Properties whose Flutter default is a fixed constant now declare that constant rather than `Optional[...] = None`, so reading one returns the value the control actually applies instead of `None`: the eight `Paint` style properties, `RoundedRectangleBorder.radius`, `Button.autofocus`, `Text.no_wrap`, `GridView.clip_behavior`, `Semantics.container`, `ExpansionPanelList.spacing`, `TextField.fit_parent_size`, `Page.show_semantics_debugger`, the three `CupertinoAppBar.automatic*` flags, `Path.Rect.border_radius` and `canvas.Text.max_width`. Rendering is unchanged, and properties a widget resolves at runtime from the theme, the platform or its own state keep `None` ([#6773](https://github.com/flet-dev/flet/pull/6773))" (Source: v1.0.0 Breaking changes, @ndonkoHenri) — read-path only; rendering unchanged.

* **iOS per-method signing precedence flip.** "iOS per-method signing settings in `[tool.flet.ios.export_methods.<method>]` (`provisioning_profile`, `signing_certificate`, `export_options`, `team_id`) now override the flat `[tool.flet.ios]` keys instead of being overridden by them. Previously a per-method value silently lost to the generic one, making the subtables useless whenever a flat key was also set; the flat key is now the shared fallback across methods — the same rule as the macOS `[tool.flet.macos.signing.<lane>]` subtables. See the [iOS per-method signing precedence](/docs/updates/breaking-changes/v1-0-0/ios-per-method-signing-precedence) guide ([#6702](https://github.com/flet-dev/flet/pull/6702))" (Source: v1.0.0 Breaking changes, @ndonkoHenri)

* **Removal: `DragTargetEvent` coordinates.** "Remove `DragTargetEvent.x`, `DragTargetEvent.y`, and `DragTargetEvent.offset` (deprecated in `0.85.0`). Use `DragTargetEvent.local_position` for target-relative coordinates or `DragTargetEvent.global_position` for global coordinates ([#6693](https://github.com/flet-dev/flet/pull/6693))" (Source: v1.0.0 Breaking changes, @ndonkoHenri)

* **Removal: `Video.show_controls`.** "Remove `Video.show_controls` (deprecated in `0.85.0`). Set `Video.controls` to `None` to hide controls ([#6693](https://github.com/flet-dev/flet/pull/6693))" (Source: v1.0.0 Breaking changes, @ndonkoHenri)

* **Removal: `Video.playlist_add()` / `playlist_remove()`.** "Remove `Video.playlist_add()` and `Video.playlist_remove()` (deprecated in `0.85.0`). Mutate `Video.playlist` directly with list methods such as `append()` and `pop()` ([#6693](https://github.com/flet-dev/flet/pull/6693))" (Source: v1.0.0 Breaking changes, @ndonkoHenri)

* **Removal: `FletApp` startup-screen options.** "Remove `FletApp.show_app_startup_screen` and `FletApp.app_startup_screen_message` (deprecated in `0.86.0`). Use `FletApp.boot_screen_options` instead, e.g. `boot_screen_options={'spinner_size': 30}` or `boot_screen_options={'startup_message': '...'}` ([#6693](https://github.com/flet-dev/flet/pull/6693))" (Source: v1.0.0 Breaking changes, @ndonkoHenri)

* **Removal: `--clear-cache` flag.** "Remove the `--clear-cache` flag of `flet build` and `flet debug` (deprecated in `0.86.0`). Use the `flet clean` command instead ([#6693](https://github.com/flet-dev/flet/pull/6693))" (Source: v1.0.0 Breaking changes, @ndonkoHenri)

* **Removal: `Page.go()`.** "Remove `Page.go()` (deprecated in `0.80.0`). Use `Page.push_route()` instead ([#6693](https://github.com/flet-dev/flet/pull/6693))" (Source: v1.0.0 Breaking changes, @ndonkoHenri)

* **Removal: `Page` service accessors.** "Remove the `Page.url_launcher`, `Page.browser_context_menu`, `Page.shared_preferences`, `Page.clipboard`, and `Page.storage_paths` service accessors (deprecated in `0.80.0`). Instantiate the corresponding service classes directly: `UrlLauncher()`, `BrowserContextMenu()`, `SharedPreferences()`, `Clipboard()`, `StoragePaths()` ([#6693](https://github.com/flet-dev/flet/pull/6693))" (Source: v1.0.0 Breaking changes, @ndonkoHenri)

* **Removal: `ConstrainedControl`.** "Remove the `ConstrainedControl` base class (deprecated in `0.80.0`). Inherit from `LayoutControl` instead ([#6693](https://github.com/flet-dev/flet/pull/6693))" (Source: v1.0.0 Breaking changes, @ndonkoHenri)

* **Removal: `ElevatedButton`.** "Remove `ElevatedButton` (deprecated in `0.80.0`). Use `Button` instead ([#6693](https://github.com/flet-dev/flet/pull/6693))" (Source: v1.0.0 Breaking changes, @ndonkoHenri)

* **Removal: non-underscored `Colors` aliases.** "Remove the deprecated non-underscored `Colors` aliases (`BLACK12`, `BLACK26`, `BLACK38`, `BLACK45`, `BLACK54`, `BLACK60`, `BLACK87`, `WHITE10`, `WHITE12`, `WHITE24`, `WHITE30`, `WHITE38`, `WHITE54`, `WHITE60`, `WHITE70`)." — **CAREFUL: the actual body lists** "`BLACK12`, `BLACK26`, `BLACK38`, `BLACK45`, `BLACK54`, `BLACK87`, `WHITE10`, `WHITE12`, `WHITE24`, `WHITE30`, `WHITE38`, `WHITE54`, `WHITE60`, `WHITE70`" (no `BLACK60` in upstream text). Full exact quote: "Remove the deprecated non-underscored `Colors` aliases (`BLACK12`, `BLACK26`, `BLACK38`, `BLACK45`, `BLACK54`, `BLACK87`, `WHITE10`, `WHITE12`, `WHITE24`, `WHITE30`, `WHITE38`, `WHITE54`, `WHITE60`, `WHITE70`). Use the underscored names instead (e.g. `Colors.BLACK_12`) ([#6693](https://github.com/flet-dev/flet/pull/6693))" (Source: v1.0.0 Breaking changes, @ndonkoHenri)

* **Removal: `app()` / `app_async()`.** "Remove `app()` and `app_async()` (deprecated in `0.80.0`). Use `run()` and `run_async()` instead ([#6693](https://github.com/flet-dev/flet/pull/6693))" (Source: v1.0.0 Breaking changes, @ndonkoHenri)

* **Removal: `target` parameter of `run()` / `run_async()`.** "Remove the `target` parameter of `run()` and `run_async()` (deprecated alias for `main`). Pass `main` instead ([#6693](https://github.com/flet-dev/flet/pull/6693))" (Source: v1.0.0 Breaking changes, @ndonkoHenri)

* **Removal: `Page.launch_url()` family.** "Remove `Page.launch_url()`, `Page.can_launch_url()`, and `Page.close_in_app_web_view()` (deprecated in `0.80.0`). Use `UrlLauncher().launch_url()` / `.can_launch_url()` / `.close_in_app_web_view()` instead ([#6693](https://github.com/flet-dev/flet/pull/6693))" (Source: v1.0.0 Breaking changes, @ndonkoHenri)

* **Removal: legacy boot-screen build-config fallback.** "Remove the legacy `[tool.flet.app.boot_screen]` / `[tool.flet.app.startup_screen]` build-config fallback. Use `[tool.flet.boot_screen]` with a named screen instead ([#6693](https://github.com/flet-dev/flet/pull/6693))" (Source: v1.0.0 Breaking changes, @ndonkoHenri) — note this project's `pyproject.toml` has a `[tool.flet.app.boot_screen]` section (`startup_message = "Initializing Collab Shell..."`), which is exactly the removed fallback path.

* **Removal: Dart empty-string widget-state key mapping.** "Remove the Dart empty-string (`""`) widget-state key back-compat mapping. Use `"default"` (or `ControlState.DEFAULT`) instead ([#6693](https://github.com/flet-dev/flet/pull/6693))" (Source: v1.0.0 Breaking changes, @ndonkoHenri)

* **Removal: `flet.utils.cleanup_path()`.** "Remove `flet.utils.cleanup_path()`. It existed only to strip rival `flutter`/`dart` directories out of the `PATH` given to Flutter subprocesses, which is the cause of [#5118](https://github.com/flet-dev/flet/issues/5118) and no longer done; it has no remaining callers. ([#6815](https://github.com/flet-dev/flet/pull/6815))" (Source: v1.0.0 Breaking changes, @ndonkoHenri)

### Reverted deprecation (anti-breaking, v1.0.0 `### Changed`)

* "`DropdownM2` is no longer deprecated and remains a supported control; its `0.84.0` deprecation in favor of `Dropdown` has been reverted ([#6693](https://github.com/flet-dev/flet/pull/6693))" (Source: v1.0.0 Changed section, @ndonkoHenri)

---

## (c) DEPRECATIONS — with scheduled removal versions

All three items are from the **`### Deprecations`** section of the **v1.0.0** body
(`upstream-notes/v1.0.0.md`, lines 58–62). All three name **`1.3.0`** as the removal version.
No new deprecations appear in v1.0.1 / v1.0.2 / v1.0.3 bodies (verified by full read).

* **`InputBorder` enum members.** "`InputBorder.OUTLINE`, `InputBorder.UNDERLINE` and `InputBorder.NONE` are deprecated in favor of `OutlineInputBorder()`, `UnderlineInputBorder()` and `NoInputBorder()`. Each still resolves, returning the equivalent instance, and they are scheduled for removal in `1.3.0`. See the [InputBorder class hierarchy](/docs/updates/breaking-changes/v1-0-0/inputborder-class-hierarchy) guide ([#6773](https://github.com/flet-dev/flet/pull/6773))" (Source: v1.0.0 Deprecations, @ndonkoHenri)

* **`border_*` properties.** "The `border_radius`, `border_width`, `border_color`, `focused_border_width` and `focused_border_color` properties of `TextField`, `Dropdown`, `DropdownM2` and `CupertinoTextField` are deprecated in favor of `border`, which accepts an `InputBorder` or a `ControlState` dictionary. They keep working and are scheduled for removal in `1.3.0`; where both are set, `border` wins. See the [InputBorder class hierarchy](/docs/updates/breaking-changes/v1-0-0/inputborder-class-hierarchy) guide ([#6773](https://github.com/flet-dev/flet/pull/6773))" (Source: v1.0.0 Deprecations, @ndonkoHenri)

* **`DropdownM2.border_radius`.** "`DropdownM2.border_radius` is deprecated in favor of `menu_border_radius` for the open menu, or `border` for the input field. It is scheduled for removal in `1.3.0`. See the [InputBorder class hierarchy](/docs/updates/breaking-changes/v1-0-0/inputborder-class-hierarchy) guide ([#6773](https://github.com/flet-dev/flet/pull/6773))" (Source: v1.0.0 Deprecations, @ndonkoHenri)

Deprecation summary table:

| Deprecated API | Replacement | Removal scheduled | Source |
|---|---|---|---|
| `InputBorder.OUTLINE` / `.UNDERLINE` / `.NONE` | `OutlineInputBorder()` / `UnderlineInputBorder()` / `NoInputBorder()` | 1.3.0 | v1.0.0 Deprecations (#6773) |
| `border_radius`, `border_width`, `border_color`, `focused_border_width`, `focused_border_color` on `TextField`, `Dropdown`, `DropdownM2`, `CupertinoTextField` | `border` (InputBorder or ControlState dict; wins on conflict) | 1.3.0 | v1.0.0 Deprecations (#6773) |
| `DropdownM2.border_radius` | `menu_border_radius` (menu) / `border` (field) | 1.3.0 | v1.0.0 Deprecations (#6773) |

---

## (d) Behavior changes (not under a "Breaking" header, but migration-relevant)

1. **Service `init()` registration timing (v1.0.1).** "Fix service properties and event handlers set in `init()` after `super().init()` being omitted from registration. Services now register after `init()` returns, so handlers are available for events raised during client initialization. Failed registrations also no longer leave invalid entries that break later registrations ([#6736](https://github.com/flet-dev/flet/discussions/6736), [#6858](https://github.com/flet-dev/flet/pull/6858))" with "**Compatibility:** `init()` overrides now register even without calling `super().init()`. Use `ft.context.page` inside `init()`; `self.page` and `self.update()` are only available after attachment. Fields set in `init()` now participate in serialization, so keep Python-only state in undeclared attributes or fields with `metadata={"skip": True}`." (Source: v1.0.1 Bug fixes, @ndonkoHenri) — this is also the root cause of the v0.86.5-era `flet_ads` crash fixed in v0.86.5: "The mobile-only platform guard read `self.page` from `init()`, which runs at construction — before the control is attached to the page… The guard is back in `before_update()`, a post-mount hook where `self.page` resolves" (Source: v0.86.5 Bug fixes, #6726/#6735, @ndonkoHenri). I.e. touching `self.page` inside `init()` was already broken in 0.86.x and is now contractually unavailable.

2. **Children matched by control id, not position (v1.0.3).** "Fix controls losing their state (a `TextField` its focus and cursor, a list its scroll position) when a sibling before them in a `Column`, `Row` or other multi-child control became visible or hidden: children were matched by position, so the shift rebuilt them. Children are now matched by control id ([#6901](https://github.com/flet-dev/flet/pull/6901))" (Source: v1.0.3 Bug fixes, @FeodorFitsner)

3. **Component child reconciling — equal children no longer skipped (v1.0.0).** "Fix a control losing its events after its parent component re-rendered it unchanged… The frozen diff that reconciles a component's output skipped any child in a single-control or list property (`Container.content`, `DataCell.content`, `DataColumn.label`, `DataTable.columns`, …) that compared equal to the previous render's — and control equality ignores the control id, so that is every rebuilt child with stable handlers (module-level functions, `use_callback`, cached lambdas) or a cached subtree… Such children are now reconciled like any other, which emits no patch operations but migrates the id, stamps the parent and refreshes the index." (Source: v1.0.0 Bug fixes, @davidlawson)

4. **Built-app exit contract — no `atexit`/`__del__`/flush guarantee (v1.0.0).** "The desktop runners now `_exit` (`TerminateProcess` on Windows, since `_exit`/`ExitProcess` still run `DLL_PROCESS_DETACH` and would not help), and the `sys.exit` path routes through a new `serious_python_hard_exit` in `dart_bridge` 1.9.0… The trade-off is now a documented contract: **Python `atexit` handlers, `__del__` finalizers and unflushed buffered writes are not guaranteed to run on exit** - persist what matters before exiting rather than relying on shutdown cleanup. `SharedPreferences` writes are unaffected and were verified to survive both paths." (Source: v1.0.0 Improvements, @FeodorFitsner)

5. **`UrlTarget.BLANK` value `"blank"` → `"_blank"` (v1.0.0).** "Its value was `"blank"` while `SELF`, `PARENT` and `TOP` all carry the leading underscore the HTML spec defines, so the value reached `window.open()` as an ordinary window *name* rather than the reserved `_blank` keyword: the first such link opened a tab called `blank` and every later one reused that same tab instead of opening its own… The enum value is now `"_blank"`" (Source: v1.0.0 Bug fixes, @FeodorFitsner) — any code persisting/comparing the raw string value changes behavior.

6. **`flet build` default excludes dotfiles/venvs (v1.0.2).** "Fix `flet build` packaging virtual environments, `.git`, `.flet` and other development files into the app. Hidden entries in the app root (a leading `.`, or the hidden attribute on Windows), virtual environments detected by `pyvenv.cfg`, and `__pycache__` directories are now excluded by default, and the build prints what was excluded" with "**Compatibility:** `.env` and other dot-prefixed files in the app root are no longer packaged. Keep them with `--include .env` or `include = [".env"]` under `[tool.flet.app]`, or turn default exclusions off with `--no-default-excludes` / `default_excludes = false`. Apps built with earlier versions may already contain `.venv` or `.flet`." (Source: v1.0.2 Bug fixes, #6839/#6890, @FeodorFitsner)

7. **Empty platform list/table no longer falls back to global (v1.0.2).** "Fix an empty list or table under `[tool.flet.<PLATFORM>]` falling back to the global `[tool.flet]` value. `app.exclude`, `source_packages`, `dev_packages`, `target_arch`, `extract_packages`, `cleanup.app_files`, `cleanup.package_files` and `flutter.build_args` now treat `[]` or `{}` in a platform section as "none for this platform" ([#6890](https://github.com/flet-dev/flet/pull/6890))" (Source: v1.0.2 Bug fixes, @FeodorFitsner)

8. **`FilePicker.pick_files()` raises instead of hanging (v1.0.0).** "`pick_files()` also no longer hangs for its full one-hour timeout when a browser has already reported it will not open the dialog: it raises straight away, pointing at `ft.PickFiles`" — with the new gesture-gated client-action alternative: "These operations are now available as client actions - `ft.PickFiles`, `ft.CopyToClipboard`, `ft.ShareText`, `ft.OpenUrl` - assigned to a control's `action` property and performed by the client inside the original gesture." (Source: v1.0.0 Bug fixes, #3710, @FeodorFitsner)

9. **`flet run --web` no longer needs `flet_desktop` (v1.0.0).** "The web branch installed `flet-web`, but the next line imported `flet_desktop` unconditionally - and that is only an optional extra of `flet`, so a plain `pip install flet` or a headless CI image never got past it. `--web`, `--ios` and `--android` all serve the app over the web server and none opens a native window, so they now ensure `flet-web`, and the desktop teardown is imported lazily and runs only when a window was opened." (Source: v1.0.0 Bug fixes, #5826/#6822, @ndonkoHenri)

10. **Generator event handlers flush each `yield` (v1.0.0).** "Each generator step - sync and async - now yields to the event loop after its update, so queued patches are flushed before the handler continues. The yield is scoped to the generator boundary, so ordinary handlers gain no new suspension point mid-dispatch" (Source: v1.0.0 Bug fixes, #6764, @PythBuster) — the classic `status.value = "Working..."; yield; time.sleep(2)` progress pattern now paints.

11. **`SnackBar` duration type.** No direct upstream line states a `SnackBar(duration=...)` type change in the four release bodies; the evidence is indirect: flet-terminal 0.3.9 had to change "example SnackBar `duration` → `ft.Duration`" (Source: flet-terminal CHANGELOG 0.3.9, see §e). The v1.0.0 "property defaults None→constant" item does not name `SnackBar.duration`. Treat a `Duration`-typed duration as observed-downstream, root upstream commit **UNVERIFIED** from release bodies alone.

---

## (e) Verdicts: flet-terminal / httpx / rich

### flet-terminal: UPGRADE 0.3.8 → 0.3.9 (required alongside Flet 1.0.x)

* **No 0.86/1.0-style versions exist.** PyPI lists exactly 13 versions, all `0.x`:
  `0.1.0, 0.2.0, 0.2.1, 0.2.2, 0.3.1, 0.3.2, 0.3.3, 0.3.4, 0.3.5, 0.3.6, 0.3.7, 0.3.8, 0.3.9`
  (Source: `https://pypi.org/pypi/flet-terminal/json`, `releases` keys). Latest = **0.3.9**.
* **Dates:** 0.3.8 — PyPI 2026-08-23T09:13:14Z, GitHub tag 2026-08-22T18:47:33Z; 0.3.9 — PyPI 2026-09-23T14:09:15Z, GitHub tag 2026-09-23T14:08:52Z. (Sources: PyPI JSON; `gh api repos/Nwokike/flet-terminal/releases`, repo `Nwokike/flet-terminal` per PyPI `project_urls.Repository`; the `flet-dev/flet-terminal` path 404s.)
* **Dependency floor:** 0.3.8 `requires_dist: ['flet>=0.86.5']` → 0.3.9 `requires_dist: ['flet>=1.0.1']`; `requires_python >=3.14` both. (Source: `https://pypi.org/pypi/flet-terminal/0.3.8/json` vs `/0.3.9/json`.) 0.3.8's floor **permits** Flet 1.0.3 at the resolver level, but 0.3.9 is the version tested against 1.0.x.
* **0.3.8 → 0.3.9 delta** (5 commits, `v0.3.8...v0.3.9`; release bodies are CI stubs — "Automated multi-platform build generated from commit `<sha>`" — so the delta below comes from the compare + file patches, all observed):
  * `chore: target flet 1.0.1 — fix pending-write flush + Clipboard leak, add consumer API` (`131773ba`): "Fix _mark_dart_ready: flet 1.0 run_task rejects sync callables, so queued send_bytes writes were re-queued forever; now branches coroutine-vs-sync" (patch: `terminal.py` uses `inspect.iscoroutinefunction(task_fn)` — coroutine → `page.run_task`, sync → direct call); "One shared Clipboard service instead of registering a new instance per copy" (patch: `mobile_terminal.py` caches `self._clipboard`, comment: "every Clipboard() construct would auto-register another instance on the page (Flet 1.0)"); "SnackBar duration=2500 -> ft.Duration(milliseconds=2500) (DurationValue)"; "New MobileTerminal API so consumers stop touching _terminal privates: on_mount property, ready, pending_count, clear_pending(), flush(), set_on_unmount()"; "flet floor >=1.0.1".
  * `release: 0.3.9` (`9f52ade0`): "Dart pubspec flet: ^0.86.5 -> ^1.0.0"; "search_bar border_color -> OutlineInputBorder (Flet 1.0 deprecation found by the test run)" (patch: `search_bar.py`: `border_color="#45475A"` → `border=ft.OutlineInputBorder(side=ft.BorderSide(color="#45475A"))`); CHANGELOG 0.3.9 entry, verbatim: "Targets **Flet 1.0.1**: Python floor `flet>=1.0.1`, Dart pubspec `flet: ^1.0.0`. / Fixed pending-write flush — Flet 1.0's `run_task` rejects sync callables, so queued `send_bytes` writes were re-queued forever. / One shared `Clipboard` service instead of registering a new instance on every copy. / New `MobileTerminal` API: `on_mount` property, `ready`, `pending_count`, `clear_pending()`, `flush()`, `set_on_unmount()` — consumers no longer need `_terminal` internals. / Search bar `border_color` → `border=OutlineInputBorder` and example SnackBar `duration` → `ft.Duration` (both deprecated/changed in Flet 1.0)."
  * Two README-only commits + one CI commit (`ci: publish to PyPI on tag push`) — no code impact.
* **Verdict:** pin `flet-terminal>=0.3.9` (floor `flet>=1.0.1` is satisfied by 1.0.3). 0.3.8 will install next to Flet 1.0.3 but carries two live bugs under 1.0 semantics (pending-write infinite re-queue; Clipboard instance leak) plus a deprecated `border_color` — upgrade, don't hold back.

### httpx: NO UPGRADE — 0.28.1 is latest stable

* PyPI `info.version` = **0.28.1** (uploaded 2024-12-06). Flet 1.0.3 requires `httpx>=0.28.1` — installed pin satisfies the floor exactly and there is nothing newer stable to take. (Sources: `https://pypi.org/pypi/httpx/json`; `flet/1.0.3` requires_dist.)
* Caveat, not action: PyPI also lists `1.0.dev1`–`1.0.dev6` pre-releases; resolvers ignore pre-releases by default, so `httpx==0.28.1` remains the resolved version. No change needed.

### rich: NO UPGRADE — 15.0.0 is latest

* PyPI `info.version` = **15.0.0** (uploaded 2026-04-12). `flet-cli`/`flet-desktop` 1.0.3 require only `rich>=13.0.0`; 15.0.0 satisfies with headroom. (Sources: `https://pypi.org/pypi/rich/json`; `flet-cli/1.0.3`, `flet-desktop/1.0.3` requires_dist.) No change needed.

---

## (f) Source index & UNVERIFIED items

* Release bodies: `audit-flet-103/upstream-notes/v0.86.5.md`, `v1.0.0.md`, `v1.0.1.md`, `v1.0.2.md`, `v1.0.3.md` (via `gh api repos/flet-dev/flet/releases/tags/<tag>`); v1.0.0 `html_url` = `https://github.com/flet-dev/flet/releases/tag/v1.0.0`, author `github-actions[bot]`.
* flet-terminal stubs: `upstream-notes/flet-terminal/v0.3.8.md`, `v0.3.9.md`; functional delta via `gh api repos/Nwokike/flet-terminal/compare/v0.3.8...v0.3.9` + commit `131773ba` / `9f52ade0` patches.
* PyPI: `https://pypi.org/pypi/{flet,flet-ads,flet-cli,flet-desktop,flet-terminal,httpx,rich}(/<ver>)/json`.
* **UNVERIFIED** (not checked — out of scope for this inventory, do not assume):
  * Individual PyPI publish dates for `flet-web`, `flet-mcp`, `flet-platform-assets` 1.0.x (referenced only via `requires_dist`).
  * The exact upstream PR that changed `SnackBar.duration` typing (only observed via flet-terminal's fix).
  * Whether `httpx 1.0.dev*` pre-releases are compatible with Flet 1.0.3 (irrelevant — pre-releases don't resolve by default).
  * Contents of the `/docs/updates/breaking-changes/v1-0-0/*` migration guides linked from the v1.0.0 body (linked, not fetched).
  * Any behavioral delta between `1.0.0.dev0`/`1.0.0.dev2` pre-releases and final `1.0.0` (pre-release bodies not collected per task scope).

# Flet API usage in non-UI code — core / services / state / hooks / main / app_shell

DOCUMENT-ONLY audit. No source file was edited. Scope is exactly the files listed
in the task; UI layers (`src/screens/`, `src/components/`, `src/ai/`) are
intentionally excluded.

Scope files (all read fully, line numbers below track the repo at audit time):

- `src/main.py` (673 lines)
- `src/app_shell.py` (462 lines)
- `src/core/__init__.py` (empty, 0 lines)
- `src/core/state.py` (99 lines)
- `src/core/constants.py` (114 lines — zero Flet usage)
- `src/core/styles.py` (224 lines)
- `src/core/theme.py` (172 lines)
- `src/core/tokens.py` (77 lines — zero Flet usage)
- `src/core/storage_patch.py` (317 lines — zero Flet usage)
- `src/core/notifications.py` (55 lines)
- `src/core/shortcuts.py` (159 lines)
- `src/core/stdin_hook.py` (187 lines)
- `src/core/changelog.py` (38 lines — zero Flet usage)
- `src/state/__init__.py` (21 lines)
- `src/state/controller_ctx.py` (53 lines)
- `src/state/service_ctx.py` (26 lines)
- `src/hooks/__init__.py` (1 line docstring — zero Flet usage)
- `src/hooks/use_keyboard_shortcuts.py` (57 lines)
- `src/services/__init__.py` (empty, 0 bytes — zero Flet usage)
- `src/services/ad_service.py` (205 lines)
- `src/services/storage_service.py` (183 lines — `ft.Page` type-hint only)
- `src/services/update_service.py` (88 lines — zero Flet usage)
- `src/services/ipynb_converter.py` (171 lines — zero Flet usage)
- `src/services/colab/__init__.py` (304 lines — zero Flet usage)
- `src/services/colab/auth.py` (248 lines — zero Flet usage)
- `src/services/colab/execution.py` (371 lines — zero Flet usage)
- `src/services/colab/files_ops.py` (318 lines — zero Flet usage)
- `src/services/colab/logs.py` (59 lines — zero Flet usage)
- `src/services/colab/session_ops.py` (437 lines — zero Flet usage)
- `src/services/colab/terminal_client.py` (387 lines — zero Flet usage)
- `src/services/colab/usage_ops.py` (126 lines — zero Flet usage)
- `src/services/colab/vm_ops.py` (95 lines — zero Flet usage)
- `pyproject.toml` (75 lines), `.flet/` dir, `scripts/check_elf_alignment.py` (105 lines)

Method: full Read of every in-scope file + `grep -rn` sweeps over the exact
file set (excluding `__pycache__`). "ABSENT" verdicts below were each verified
by an explicit grep, not by assumption.

All paths below are repo-relative. Absolute root:
`C:\Users\nwoki\.zcode\workspace\default\CollabShell\`.

---

## (a) Per-file inventory — every `ft.*` / `flet` usage in scope

### `src/main.py`

Import: `src/main.py:13` — `import flet as ft`.

| Line(s) | Usage |
|---|---|
| `src/main.py:115` | `def __init__(self, page: ft.Page)` — type hint, `AppController` ctor |
| `src/main.py:167` | `page.theme_mode = ft.ThemeMode.SYSTEM` |
| `src/main.py:168` | `state.theme_mode = page.theme_mode` (plain attribute read) |
| `src/main.py:196` | `file_picker = ft.FilePicker()` |
| `src/main.py:200` | `connectivity = ft.Connectivity()` |
| `src/main.py:208` | `state.is_online = ft.ConnectivityType.NONE not in types` (connectivity-change handler) |
| `src/main.py:376,377,378,379,381` | `ft.ThemeMode.SYSTEM/LIGHT/DARK` reads+writes in `_toggle_theme` |
| `src/main.py:384,386` | `ft.ThemeMode.LIGHT`, `ft.ThemeMode.DARK` comparisons in `_toggle_theme` |
| `src/main.py:442,443,444` | `ft.ThemeMode.DARK/SYSTEM/LIGHT` in `_restore_preferences` theme_map |
| `src/main.py:505` | `state.is_online = ft.ConnectivityType.NONE not in connectivity` (`_bootstrap_state`) |
| `src/main.py:598` | `async def _on_lifecycle_change(e: ft.AppLifecycleStateChangeEvent)` — annotation only |
| `src/main.py:600,601` | `ft.AppLifecycleState.RESUME`, `ft.AppLifecycleState.SHOW` |
| `src/main.py:608` | `state.is_online = ft.ConnectivityType.NONE not in connectivity` (resume re-probe) |
| `src/main.py:663` | `async def main(page: ft.Page)` — `ft.run` target signature |
| `src/main.py:672` | `ft.run(main, assets_dir=assets_path)` under `if __name__ == "__main__"` |

`page.*` API inventory in `src/main.py` (all PRESENT, each verified):

- `src/main.py:158` `page.title`; `src/main.py:159` `page.fonts`
- `src/main.py:163` `page.theme`; `src/main.py:164` `page.dark_theme`
- `src/main.py:165,166` `page.theme.font_family`, `page.dark_theme.font_family`
- `src/main.py:167,168,376-384,447,448` `page.theme_mode`
- `src/main.py:170,171` `page.window.min_width`, `page.window.min_height`
- `src/main.py:172` `page.padding`; `src/main.py:173` `page.spacing`
- `src/main.py:184` `page.on_error`; `src/main.py:193` `page.on_platform_brightness_change`
- `src/main.py:197,201` `page.services.append(...)` (FilePicker, Connectivity)
- `src/main.py:198` `page.file_picker`; `src/main.py:202` `page.connectivity`
- `src/main.py:213` `connectivity.on_change = ...` (control event, not page)
- `src/main.py:219,236,388,431,436` `page.run_task(...)` (5 call sites + `src/main.py:178` context; 11 `page.run_task` hits scope-wide incl. other files)
- `src/main.py:322,646` `page.route` (write in `_navigate`, read in `_on_view_pop`)
- `src/main.py:332` `page.on_route_change`
- `src/main.py:419` `page.render(...)` — mounts the component tree
- `src/main.py:504,607` `self.page.connectivity.get_connectivity()` / `page.connectivity.get_connectivity()`
- `src/main.py:191,211,393,547` `page.update()` / `self.page.update()`
- `src/main.py:595` `page.on_disconnect`; `src/main.py:637` `page.on_app_lifecycle_state_change`
- `src/main.py:644,645,646` `page.views` (`len(page.views)`, `page.views.pop()`, `page.views[-1].route`)
- `src/main.py:648` `page.on_view_pop`

### `src/app_shell.py`

Import: `src/app_shell.py:13` `import flet as ft`; `src/app_shell.py:14` `from flet import Control`.
Docstring refs (not code): `src/app_shell.py:4` `@ft.component`, `src/app_shell.py:5` `page.views[0]`, `use_effect`.

| Line(s) | Usage |
|---|---|
| `src/app_shell.py:27-31` | `ft.Icons.HOME_OUTLINED/EDIT_NOTE_ROUNDED/TERMINAL_OUTLINED/FOLDER_OUTLINED/SETTINGS_OUTLINED` |
| `src/app_shell.py:34-38` | `ft.Icons.HOME_ROUNDED/EDIT_NOTE_ROUNDED/TERMINAL_ROUNDED/FOLDER_ROUNDED/SETTINGS_ROUNDED` |
| `src/app_shell.py:42` | `@ft.component` on `AppShell()` |
| `src/app_shell.py:45` | `controller = ft.use_context(ControllerMethodsCtx)` |
| `src/app_shell.py:46` | `state = ft.use_context(AppStateCtx)` |
| `src/app_shell.py:47` | `page = ft.context.page` |
| `src/app_shell.py:80` | `ft.on_mounted(_register_global_shortcuts)` |
| `src/app_shell.py:109` | `ft.NavigationBarDestination(...)` |
| `src/app_shell.py:118` | `page.views[0].navigation_bar = ft.NavigationBar(...)` |
| `src/app_shell.py:122` | `bgcolor=ft.Colors.SURFACE` (NavigationBar) |
| `src/app_shell.py:123` | `ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY)` (indicator) |
| `src/app_shell.py:124` | `label_behavior=ft.NavigationBarLabelBehavior.ALWAYS_SHOW` |
| `src/app_shell.py:131` | `ft.use_effect(_sync_navigation_bar, [...])` |
| `src/app_shell.py:144,145,147,151,154,160,161,164` | `ft.Container/ft.Column/ft.Image/ft.BoxFit.CONTAIN/ft.ProgressRing/ft.MainAxisAlignment.CENTER/ft.CrossAxisAlignment.CENTER/ft.Alignment.CENTER` (splash) |
| `src/app_shell.py:173` | `ft.ConnectivityType.NONE not in connectivity` (retry handler) |
| `src/app_shell.py:181` | `page.run_task(_on_retry)` |
| `src/app_shell.py:187` | `ft.ValueKey("onboarding")` |
| `src/app_shell.py:191-195,199-202` | `ft.Icons.BRIGHTNESS_AUTO_ROUNDED/LIGHT_MODE_ROUNDED/DARK_MODE_ROUNDED` + `ft.ThemeMode.SYSTEM/LIGHT` comparisons (theme icon block 1) |
| `src/app_shell.py:204` | `ft.IconButton(...)` (theme_btn block 1) |
| `src/app_shell.py:214,215,217,218,220,221,226,229,231,235,238,244,246,247` | history header: `ft.SafeArea/ft.Column/ft.Container/ft.Row/ft.IconButton/ft.Icons.ARROW_BACK_ROUNDED/ft.Text/ft.FontWeight.W_700/ft.CrossAxisAlignment.CENTER/ft.Padding/ft.Colors.SURFACE/ft.ValueKey("history_screen")` |
| `src/app_shell.py:261-299` | files header: `ft.SafeArea/ft.Column/ft.Container/ft.Row/ft.IconButton/ft.Icons.ARROW_BACK_ROUNDED/ft.Text/ft.FontWeight.W_700/ft.Container(expand)/ft.CrossAxisAlignment.CENTER/ft.Padding/ft.Colors.SURFACE/ft.ValueKey(f"files_...")` |
| `src/app_shell.py:309-318` | session subview: `ft.SafeArea` + `ft.ValueKey(f"session_...")` |
| `src/app_shell.py:323-327,331-333` | theme icon block 2 (same `ft.Icons.*` + `ft.ThemeMode.*` set) |
| `src/app_shell.py:336` | `ft.IconButton(...)` (theme_btn block 2) |
| `src/app_shell.py:353,355,360,361,364,368,372` | update pill: `ft.Row/ft.Text/ft.FontWeight.BOLD/ft.Colors.PRIMARY/ft.Container/ft.Colors.PRIMARY/ft.CrossAxisAlignment.CENTER` |
| `src/app_shell.py:374,376,378,379` | update pill container: `ft.Container/ft.Padding/ft.Colors.with_opacity(0.15, ft.Colors.PRIMARY)/ft.Border.all(1.5, ft.Colors.PRIMARY)` |
| `src/app_shell.py:384,385,388,389,392,394` | version chip: `ft.Container/ft.Text/ft.FontWeight.BOLD/ft.Colors.ON_SURFACE_VARIANT/ft.Padding/ft.Colors.with_opacity(0.08, ft.Colors.ON_SURFACE_VARIANT)` |
| `src/app_shell.py:400,401,403,406,407,409,410,411,421,424,427` | header bar: `ft.Container/ft.Row/ft.Text/ft.FontWeight.BOLD/ft.Colors.ON_SURFACE/ft.Container(expand)/ft.IconButton/ft.Icons.HISTORY_ROUNDED/ft.CrossAxisAlignment.CENTER/ft.Padding/ft.Colors.SURFACE` |
| `src/app_shell.py:433,437,441,445,449` | `ft.ValueKey("notebook_tab"/"terminal_tab"/"files_tab"/"settings_tab"/"home_tab")` |
| `src/app_shell.py:451,452,455` | `ft.SafeArea/ft.Column/ft.Container(content=screen, expand=True)` |
| `src/app_shell.py:85,95,96,118` | `page.views` reads/writes (nav-bar sync); `src/app_shell.py:98,127` `page.update()` |

### `src/core/state.py`

| Line(s) | Usage |
|---|---|
| `src/core/state.py:7` | `import flet as ft` |
| `src/core/state.py:10` | `@ft.observable` on `AppState` |
| `src/core/state.py:37` | `theme_mode: ft.ThemeMode = ft.ThemeMode.SYSTEM` (annotation + default) |

No other `ft.*` in this file.

### `src/core/theme.py`

| Line(s) | Usage |
|---|---|
| `src/core/theme.py:3` | `import flet as ft` |
| `src/core/theme.py:66` | `def _resolve_page(page: ft.Page \| None) -> ft.Page \| None` |
| `src/core/theme.py:71` | `return ft.context.page` |
| `src/core/theme.py:76` | `def is_light_theme(page: ft.Page \| None = None)` |
| `src/core/theme.py:99` | `if tm == ft.ThemeMode.LIGHT` |
| `src/core/theme.py:101` | `if tm == ft.ThemeMode.DARK` |
| `src/core/theme.py:105` | `if brightness == ft.Brightness.DARK` |
| `src/core/theme.py:107` | `if brightness == ft.Brightness.LIGHT` |
| `src/core/theme.py:112,117` | `def adaptive_glass_bg/bg_border(page: ft.Page \| None = None)` |
| `src/core/theme.py:128,129,130` | `-> ft.Theme: return ft.Theme(color_scheme=ft.ColorScheme(...))` (dark) |
| `src/core/theme.py:151,152,153` | `-> ft.Theme: return ft.Theme(color_scheme=ft.ColorScheme(...))` (light) |

Docstring-only mentions: `src/core/theme.py:79` ("page.theme_mode"), `src/core/theme.py:81`
("page.platform_brightness"), `src/core/theme.py:82` ("ft.context.page"),
`src/core/theme.py:85` ("state.theme_mode/revision"). `AppColors` itself uses
only hardcoded hex strings — zero `ft.Colors`.

### `src/core/styles.py`

Import: `src/core/styles.py:5` `import flet as ft`.

| Line(s) | Usage |
|---|---|
| `src/core/styles.py:12,13,14,17,18,19,21` | `-> ft.Container / ft.Container / ft.Text / ft.FontWeight.W_700 / ft.Colors.PRIMARY / ft.TextStyle / ft.Padding` (`section_header`) |
| `src/core/styles.py:31` | `icon: ft.Icons = None` (annotation) |
| `src/core/styles.py:35-46,64,66` | `-> ft.Container / ft.Container/ft.Row/ft.Icon/ft.Colors.ON_SURFACE_VARIANT/ft.Container/ft.Column/ft.Text/ft.FontWeight.W_500/ft.Text/ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE)/ft.CrossAxisAlignment.CENTER/ft.Padding` (`setting_tile`) |
| `src/core/styles.py:76,79,81,89` | `content: ft.Control / ft.Container / ft.Padding / ft.Border.all` (`glass_card`) |
| `src/core/styles.py:94,95,97` | `content: ft.Control / ft.Container / ft.Padding` (`solid_card`) |
| `src/core/styles.py:108` | `def build_banner_ad(page: ft.Page, ...)` |
| `src/core/styles.py:110` | `ft.PagePlatform.ANDROID, ft.PagePlatform.IOS` |
| `src/core/styles.py:111,132,134,135,139,142,147` | `ft.Container / ft.Column / ft.CrossAxisAlignment.CENTER / ft.Alignment.CENTER / ft.Border.all / ft.Margin` (`build_banner_ad`) |
| `src/core/styles.py:153,165,166,169,170,174` | `-> ft.Container / ft.Container/ft.Text/ft.FontWeight.W_700/ft.Colors.WHITE/ft.Padding` (`hardware_badge`; colors themselves from `AppColors`) |
| `src/core/styles.py:180,189,190,193,194,198` | same control set (`shape_chip`) |
| `src/core/styles.py:204,208` | `-> ft.Container / ft.Container(...)` (`status_dot`) |
| `src/core/styles.py:216,218,221` | `-> ft.Text / ft.Text / ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE)` (`tip_text`) |

### `src/core/notifications.py`

| Line(s) | Usage |
|---|---|
| `src/core/notifications.py:7` | `import flet as ft` |
| `src/core/notifications.py:15` | `page: ft.Page \| None` (annotation) |
| `src/core/notifications.py:39` | `snack = ft.SnackBar(...)` |
| `src/core/notifications.py:40` | `content=ft.Text(message, color=ft.Colors.WHITE)` |
| `src/core/notifications.py:43` | `behavior=ft.SnackBarBehavior.FLOATING` |
| `src/core/notifications.py:44` | `dismiss_direction=ft.DismissDirection.HORIZONTAL` |
| `src/core/notifications.py:48` | `page.overlay.append(snack)` |
| `src/core/notifications.py:49` | `page.update()` |

Docstring: `src/core/notifications.py:22` mentions `page.overlay` in prose.

### `src/core/shortcuts.py`

| Line(s) | Usage |
|---|---|
| `src/core/shortcuts.py:17` | `import flet as ft` |
| `src/core/shortcuts.py:50` | `def matches(self, e: ft.KeyboardEvent)` (annotation) |
| `src/core/shortcuts.py:86` | `def resolve(self, e: ft.KeyboardEvent)` (annotation) |

No control construction; `e.ctrl/e.meta/e.shift/e.alt/e.key` attribute reads
in `src/core/shortcuts.py:51-57`. Docstring `src/core/shortcuts.py:3`
references `page.on_keyboard_event` in prose.

### `src/core/stdin_hook.py`

Import: `src/core/stdin_hook.py:5` `import flet as ft`.

| Line(s) | Usage |
|---|---|
| `src/core/stdin_hook.py:12` | `def show_stdin_dialog(page: ft.Page, ...)` |
| `src/core/stdin_hook.py:40` | `dialog_field = ft.TextField(...)` |
| `src/core/stdin_hook.py:53,104,176` | `page.update()` |
| `src/core/stdin_hook.py:68` | `dialog.title = ft.Text("Verifying Authorization...")` |
| `src/core/stdin_hook.py:69,71,73,78,81,86,89` | `ft.Column/ft.Row/ft.ProgressRing/ft.Text/ft.FontWeight.BOLD/ft.Text/ft.Colors.ON_SURFACE_VARIANT` (verifying state) |
| `src/core/stdin_hook.py:96` | `ft.TextButton("Cancel", ...)` |
| `src/core/stdin_hook.py:101` | `dialog.update()` |
| `src/core/stdin_hook.py:128` | `ft.Text(display_text, ...)` |
| `src/core/stdin_hook.py:132` | `await ft.UrlLauncher().launch_url(extracted_url)` |
| `src/core/stdin_hook.py:135` | `await ft.Clipboard().set(extracted_url)` |
| `src/core/stdin_hook.py:140,142,146,147` | `ft.Row/ft.FilledButton/ft.IconButton/ft.Icons.COPY_ROUNDED` |
| `src/core/stdin_hook.py:144,149` | `page.run_task(_launch_url_task/_copy_url_task, e)` |
| `src/core/stdin_hook.py:158-160,164,165` | `ft.AlertDialog/title=ft.Text/content=ft.Column/ft.TextButton/ft.FilledButton` |
| `src/core/stdin_hook.py:174` | `page.show_dialog(dialog)` |
| `src/core/stdin_hook.py:178` | `page.run_task(_show)` |
| `src/core/stdin_hook.py:183` | `def setup_global_stdin_hook(page: ft.Page, ...)` |

### `src/state/__init__.py`

| Line(s) | Usage |
|---|---|
| `src/state/__init__.py:5` | `import flet as ft` |
| `src/state/__init__.py:11` | `AppStateCtx = ft.create_context(state)` |

Docstring `src/state/__init__.py:1` mentions "context" in prose only.

### `src/state/controller_ctx.py`

| Line(s) | Usage |
|---|---|
| `src/state/controller_ctx.py:12` | `import flet as ft` |
| `src/state/controller_ctx.py:51` | `ControllerMethodsCtx = ft.create_context(ControllerMethods())` |

Docstring `src/state/controller_ctx.py:3` references
`ft.use_context(ControllerMethodsCtx)` in prose.

### `src/state/service_ctx.py`

| Line(s) | Usage |
|---|---|
| `src/state/service_ctx.py:11` | `import flet as ft` |
| `src/state/service_ctx.py:21` | comment-only `ft.Page` mention (`page: object = None  # ft.Page ref ...`) |
| `src/state/service_ctx.py:24` | `ServiceCtx = ft.create_context(Services())` |

Docstring `src/state/service_ctx.py:3` references `ft.use_context(ServiceCtx)`
in prose.

### `src/hooks/use_keyboard_shortcuts.py`

| Line(s) | Usage |
|---|---|
| `src/hooks/use_keyboard_shortcuts.py:20` | `import flet as ft` |
| `src/hooks/use_keyboard_shortcuts.py:29` | `from flet import context as _ctx` |
| `src/hooks/use_keyboard_shortcuts.py:32` | `page = _ctx.page` |
| `src/hooks/use_keyboard_shortcuts.py:36` | `previous = page.on_keyboard_event` |
| `src/hooks/use_keyboard_shortcuts.py:38` | `async def _handler(e: ft.KeyboardEvent)` |
| `src/hooks/use_keyboard_shortcuts.py:50` | `page.on_keyboard_event = _handler` |
| `src/hooks/use_keyboard_shortcuts.py:53` | `page.on_keyboard_event = previous` (cleanup) |
| `src/hooks/use_keyboard_shortcuts.py:57` | `ft.on_mounted(_install)` |

Docstring lines `src/hooks/use_keyboard_shortcuts.py:3` (`page.on_keyboard_event`)
are prose.

### `src/services/ad_service.py`

Import: `src/services/ad_service.py:13` `import flet as ft`; test import
`src/services/ad_service.py:18-19` (`import flet as ft`, `import flet_ads as fta`).

| Line(s) | Usage |
|---|---|
| `src/services/ad_service.py:40` | `def __init__(self, page: ft.Page)` |
| `src/services/ad_service.py:68` | `self.page.platform.is_mobile()` |
| `src/services/ad_service.py:81` | `self.page.services.append(self._consent_manager)` |
| `src/services/ad_service.py:97` | `fta.PrivacyOptionsRequirementStatus.REQUIRED` (flet_ads, not core flet) |
| `src/services/ad_service.py:105` | `def get_banner_ad(self) -> ft.Control` |
| `src/services/ad_service.py:108` | `return ft.Container(width=0, height=0)` (non-mobile fallback) |
| `src/services/ad_service.py:118,122` | `return ft.Container(...)` + `alignment=ft.Alignment.CENTER` |
| `src/services/ad_service.py:132` | `return ft.Container(width=0, height=0)` (exception fallback) |
| `src/services/ad_service.py:191,192` | `self.page.run_task(_show/_close, e)` (rewarded interstitial callbacks) |

`fta.BannerAd/InterstitialAd/ConsentManager` (`src/services/ad_service.py:80,112,140,189`)
are `flet_ads`, not core `flet`.

### `src/services/storage_service.py`

| Line(s) | Usage |
|---|---|
| `src/services/storage_service.py:16` | `import flet as ft` |
| `src/services/storage_service.py:39` | `def __init__(self, page: ft.Page)` — hint only; `page` is stored as `self._page` but never calls a Flet API in this file |

No other `ft.*` in this file. Deliberately file-based JSON storage; does NOT use
`page.shared_preferences` / `page.client_storage`.

### Zero-Flet files in scope (verified by grep, no `flet`/`ft.` hits)

- `src/core/__init__.py:1` — empty file (0 content lines).
- `src/core/constants.py` — pure constants.
- `src/core/tokens.py` — pure numeric tokens.
- `src/core/changelog.py` — pure `CHANGELOG` dict + `notes_for()`.
- `src/core/storage_patch.py` — stdlib `os`/`logging`/`pathlib` + `FLET_APP_STORAGE_DATA` **env-var name as a string** (`src/core/storage_patch.py:20`); no flet import.
- `src/hooks/__init__.py:1` — docstring only.
- `src/services/__init__.py` — empty (0 bytes).
- `src/services/update_service.py` — `httpx` only.
- `src/services/ipynb_converter.py` — stdlib `uuid` only.
- `src/services/colab/__init__.py`, `auth.py`, `execution.py`, `files_ops.py`, `logs.py`, `session_ops.py`, `terminal_client.py`, `usage_ops.py`, `vm_ops.py` — no `flet`/`ft.` hits (explicit grep returned empty).

### Cross-file `page.<accessor>` frequency (scope only, for migration triage)

Counts from `grep -rhoP "page\.[a-z_]+"` over the scope set:
`page.theme_mode` x13, `page.run_task` x11, `page.update` x10, `page.views` x8,
`page.on_keyboard_event` x5 (incl. prose), `page.connectivity` x4,
`page.services` x3, `page.window` x2, `page.theme` x2, `page.route` x2,
`page.render` x2, `page.platform` x2, `page.overlay` x2,
`page.on_route_change` x2, `page.dark_theme` x2, and x1 each:
`page.title/fonts/padding/spacing/show_dialog/platform_brightness/on_view_pop/on_platform_brightness_change/on_error/on_disconnect/on_app_lifecycle_state_change/file_picker`.

### `ft.Colors` token census (scope only)

Exactly 5 distinct tokens, all canonical theme roles (no legacy/bare aliases):
`ft.Colors.PRIMARY` x6, `ft.Colors.SURFACE` x4,
`ft.Colors.ON_SURFACE_VARIANT` x4, `ft.Colors.WHITE` x3,
`ft.Colors.ON_SURFACE` x3 — plus `ft.Colors.with_opacity(...)` call sites in
`src/app_shell.py:123,378,394`, `src/core/styles.py:56,221`. Full per-line map
is in the table rows above.

---

## (b) HOT LIST — checklist vs 1.0.0 removals / renames

Each verdict was verified by an explicit grep over the scope file set (+
`pyproject.toml` where noted). "PRESENT" cites the exact line; "ABSENT" means
the grep returned zero hits.

| # | API / key | Verdict |
|---|---|---|
| 1 | `ft.app()` / `app_async()` | **ABSENT** — no `ft.app`, `ft.app_async`, or `app_async` hits in scope or `pyproject.toml`. Entry point is `src/main.py:672` `ft.run(main, assets_dir=...)`. |
| 2 | `ft.run()` / `ft.run_async()` | `ft.run` **PRESENT** `src/main.py:672`. `ft.run_async` **ABSENT** (zero hits). |
| 3 | `Page.go()` | **ABSENT** — `\.go\(` grep returns zero hits in scope. Internal navigation assigns `page.route = ...` (`src/main.py:322`, `src/main.py:646`) instead of calling `go()`. |
| 4 | `Page.launch_url()` | **ABSENT** — no `page.launch_url` / `page.launch` hits. External links use the service form `await ft.UrlLauncher().launch_url(extracted_url)` at `src/core/stdin_hook.py:132`. |
| 5 | `Page.can_launch_url()` | **ABSENT** — zero hits for `can_launch_url`. |
| 6 | `Page.close_in_app_web_view()` | **ABSENT** — zero hits for `close_in_app`. |
| 7 | `Page.url_launcher` accessor | **ABSENT** — zero hits for `url_launcher` (case-sensitive). Only the constructor form `ft.UrlLauncher()` at `src/core/stdin_hook.py:132`. |
| 8 | `Page.browser_context_menu` | **ABSENT** — zero hits. |
| 9 | `Page.shared_preferences` / `SharedPreferences` | **ABSENT** — zero hits for both spellings. `StorageService` (`src/services/storage_service.py`) is file-backed JSON, never touches the accessor. |
| 10 | `Page.clipboard` accessor | **ABSENT** as an accessor — zero hits for `page.clipboard`. Only the service form `await ft.Clipboard().set(extracted_url)` at `src/core/stdin_hook.py:135`. |
| 11 | `Page.storage_paths` / `StoragePaths` | **ABSENT** — zero hits for both spellings. Sandbox paths are read via the `FLET_APP_STORAGE_DATA` env var string at `src/core/storage_patch.py:20`. |
| 12 | `UrlLauncher` service | **PRESENT** `src/core/stdin_hook.py:132` — `await ft.UrlLauncher().launch_url(extracted_url)`. |
| 13 | `Clipboard` service | **PRESENT** `src/core/stdin_hook.py:135` — `await ft.Clipboard().set(extracted_url)`. |
| 14 | `SharedPreferences` service | **ABSENT** — zero hits. |
| 15 | `StoragePaths` service | **ABSENT** — zero hits. |
| 16 | `ConstrainedControl` | **ABSENT** — zero hits (also case-insensitive sweep of `src/` returned nothing). Only `ft.Control` (`src/app_shell.py:14`, `src/core/styles.py:76,94`, `src/services/ad_service.py:105`). |
| 17 | `ElevatedButton` | **ABSENT** — zero hits. Buttons in scope are `ft.FilledButton`, `ft.TextButton`, `ft.IconButton` only. |
| 18 | Non-underscored `Colors` aliases | **ABSENT** — all 20 `ft.Colors.*` hits use canonical roles (`PRIMARY/SURFACE/ON_SURFACE/ON_SURFACE_VARIANT/WHITE`). No bare aliases (e.g. `RED`, `BLUE`) appear. |
| 19 | `ControlState` `""` key | **ABSENT** — `ControlState` has zero hits repo-wide in `src/`; the empty-string-key grep (`""`:) also returned nothing in scope. |
| 20 | `flet.utils.cleanup_path` | **ABSENT** — zero hits for `cleanup_path` and for `flet\.utils`. |
| 21 | `--clear-cache` CLI flag | **ABSENT** — zero hits for `clear-cache` / `clear_cache`. |
| 22 | `[tool.flet.app.boot_screen]` / `startup_screen` fallback keys | `boot_screen` **PRESENT** `pyproject.toml:36`; `startup_screen` **ABSENT** (zero hits). `splash`, `icon_bgcolor`, `icon_background` all **ABSENT** (zero hits each). |
| 23 | `page.show_dialog` / `page.pop_dialog` | `show_dialog` **PRESENT** `src/core/stdin_hook.py:174`; `pop_dialog` **ABSENT** (dialog closes via `dialog.open = False` at `src/core/stdin_hook.py:52,103`). |
| 24 | `page.connectivity` / `ft.Connectivity` | **PRESENT** — `ft.Connectivity()` `src/main.py:200`; attached `src/main.py:201-203`; probed `src/main.py:504`, `src/main.py:607`, `src/app_shell.py:172`. |
| 25 | `page.views` / `page.route` | **PRESENT** — views `src/main.py:644-646`, `src/app_shell.py:85,95,96,118`; route `src/main.py:322,332,646`. |
| 26 | `ft.component` | **PRESENT** `src/app_shell.py:42`. |
| 27 | `ft.observable` | **PRESENT** `src/core/state.py:10`. |
| 28 | `ft.use_context` / `ft.create_context` / `ft.context.page` | **PRESENT** — `use_context` `src/app_shell.py:45,46`; `create_context` `src/state/__init__.py:11`, `src/state/controller_ctx.py:51`, `src/state/service_ctx.py:24`; `ft.context.page` `src/app_shell.py:47`, `src/core/theme.py:71`. |
| 29 | `ft.use_state` / `ft.use_ref` | Both **ABSENT** — zero hits. State flows through the `@ft.observable` singleton + contexts. |
| 30 | `ft.use_effect` | **PRESENT** `src/app_shell.py:131`. |
| 31 | `ft.on_mounted` / `ft.on_unmounted` | `on_mounted` **PRESENT** `src/app_shell.py:80`, `src/hooks/use_keyboard_shortcuts.py:57`; `on_unmounted` **ABSENT** (cleanup is returned from the `on_mounted` callback: `src/hooks/use_keyboard_shortcuts.py:52-55`, `src/core/shortcuts.py:75-84`). |
| 32 | `ft.ThemeMode` / `ft.Colors` | Both **PRESENT** — ThemeMode 15+ sites (`src/main.py`, `src/app_shell.py`, `src/core/state.py`, `src/core/theme.py`); Colors 20 sites (§(a) census). |
| 33 | `target` / `main` params of entry | `async def main(page: ft.Page)` at `src/main.py:663`; `ft.run(main, assets_dir=assets_path)` at `src/main.py:672` with `assets_path` built at `src/main.py:671`. No `target=` kwarg, no `view=`/`port=`/`upload_strategy=` args. |

---

## (c) `pyproject.toml` `[tool.flet]` table + 1.0.3 compatibility notes

### Verbatim table copy (with line numbers)

Source: `pyproject.toml:27-60` (project pins `flet>=0.86.5`, `flet-ads>=0.86.5` at `pyproject.toml:8-9`; locked to `flet 0.86.5` / `flet_ads 0.86.5` in `uv.lock:390-413`):

```toml
# pyproject.toml:27
[tool.flet] # pyproject.toml:27
org = "ng.kiri" # pyproject.toml:28
product = "Colab Shell" # pyproject.toml:29
build_number = 12 # pyproject.toml:30
# pyproject.toml:31 (blank)
[tool.flet.app] # pyproject.toml:32
path = "src" # pyproject.toml:33
# pyproject.toml:34 (blank)
# pyproject.toml:35 (blank)
[tool.flet.app.boot_screen] # pyproject.toml:36
startup_message = "Initializing Collab Shell..." # pyproject.toml:37
# pyproject.toml:38 (blank)
[tool.flet.android] # pyproject.toml:39
bundle_id = "ng.kiri.collabshell" # pyproject.toml:40
# pyproject.toml:41 (blank)
# Google Play requires 16 KB ELF page alignment on 64-bit ABIs; pyzmq 27.2.0's # pyproject.toml:42 (comment)
# android x86_64 wheel ships 4 KB-aligned libs (libzmq + libc++_shared), so # pyproject.toml:43 (comment)
# x86_64 is dropped. armeabi-v7a is kept: 32-bit ABIs are exempt from the # pyproject.toml:44 (comment)
# 16 KB check, and it preserves phone/tablet/TV device reach. # pyproject.toml:45 (comment)
target_arch = ["arm64-v8a", "armeabi-v7a"] # pyproject.toml:46
# pyproject.toml:47 (blank)
[tool.flet.android.meta_data] # pyproject.toml:48
"com.google.android.gms.ads.APPLICATION_ID" = "ca-app-pub-5679949845754640~7138516733" # pyproject.toml:49
# pyproject.toml:50 (blank)
[tool.flet.android.manifest_application] # pyproject.toml:51
allowBackup = "false" # pyproject.toml:52
# pyproject.toml:53 (blank)
[tool.flet.android.permission] # pyproject.toml:54
"android.permission.INTERNET" = true # pyproject.toml:55
"android.permission.ACCESS_NETWORK_STATE" = true # pyproject.toml:56
# pyproject.toml:57 (blank)
[tool.flet.android.signing] # pyproject.toml:58
key_store = "../../../../kiri_keystore.jks" # pyproject.toml:59
key_alias = "upload" # pyproject.toml:60
```

(`pyproject.toml:61-63` are trailing blanks; no further `[tool.flet.*]` keys exist.)

### Per-key 1.0.3 compatibility notes

- `[tool.flet]` / `org` (`pyproject.toml:27-28`), `product` (`pyproject.toml:29`), `build_number` (`pyproject.toml:30`): unchanged top-level identity keys. `build_number = 12` matches `APP_BUILD_NUMBER = 12` (`src/core/constants.py:6`) and the `2.1.2` changelog note about the build-number sync (`src/core/changelog.py:6-10`). No migration action implied by the audit corpus.
- `[tool.flet.app] path = "src"` (`pyproject.toml:32-33`): only key in this sub-table. Confirm the 1.0.x `path`/entry semantics still resolve `src/main.py:663 main()` + `src/main.py:672 ft.run(...)`; nothing else in scope references the app path.
- `[tool.flet.app.boot_screen]` + `startup_message` (`pyproject.toml:36-37`): the table the task flags for the `splash` rename family (`icon_bgcolor` -> `icon_background`, `boot_screen` table shape, `startup_screen` fallback keys) — **none of the rename-sensitive keys are present**: `splash`, `startup_screen`, `icon_bgcolor`, `icon_background` all grep ABSENT (scope + `pyproject.toml`). Only `startup_message` is set, so there is no legacy key left to rename in this repo; verify at migration time that `boot_screen.startup_message` is still honored verbatim in 1.0.3 and whether the table now expects additional/renamed siblings.
- `[tool.flet.android] bundle_id` (`pyproject.toml:39-40`) + `target_arch` (`pyproject.toml:46`): `target_arch = ["arm64-v8a", "armeabi-v7a"]` with the 16 KB rationale in comments (`pyproject.toml:42-45`). No 1.0.3 key-name signal inside this audit; keep the exclusion until the gate script (§(d)) passes on a rebuilt artifact.
- `[tool.flet.android.meta_data]` AdMob ID (`pyproject.toml:48-49`): consumed by `AdService`/UMP flow (`src/services/ad_service.py:74-87`); no config-key rename visible in scope.
- `[tool.flet.android.manifest_application] allowBackup = "false"` (`pyproject.toml:51-52`): no rename signal in scope.
- `[tool.flet.android.permission]` INTERNET + ACCESS_NETWORK_STATE (`pyproject.toml:54-56`): matches the `ft.Connectivity` + `httpx` usage (`src/main.py:200`, `src/services/update_service.py:15`); no key change in scope.
- `[tool.flet.android.signing]` (`pyproject.toml:58-60`): relative `key_store` path outside the repo; orthogonal to Flet API migration.
- **Build-exclusions / `.env` / dotfiles behavior change**: **no exclusion keys exist anywhere in `pyproject.toml`** (verified — the whole `[tool.flet]` block is copied above; there is no `exclude`/`include`/`ignore` key). The repo root `.gitignore` was not in audit scope, but `.flet/.gitignore` contains a single `*` (`C:\Users\nwoki\.zcode\workspace\default\CollabShell\.flet\.gitignore:1`). Because the app ships no exclusion config today, the noted 1.0.3 "exclusions now also filter `.env`/dotfiles" change can only *remove* files from the package vs 0.86.5 behavior — confirm at build time that nothing the app needs at runtime (e.g. `src/assets/*`, `token.json`/`storage.json` flows via `src/core/storage_patch.py:12-28`) was previously swept in by accident and now gets excluded.

---

## (d) `.flet/` directory + `scripts/check_elf_alignment.py` relevance

- `.flet/README.md:1-12` — stock Flet dev-state readme: `.flet/` is created by `flet run`, holds per-project dev state, is git-ignored, safe to delete. Documents `storage/data|cache|temp` + `FLET_APP_STORAGE_*` env vars matching packaged-device behavior.
- `.flet/.gitignore:1` — single `*` (everything under `.flet/` untracked).
- `.flet/storage/data/colab-cli/*` — live dev-run data only (history `.jsonl`, `sessions.json`, `storage.json`, `token.json`, notebook caches). This is the on-disk counterpart of `resolve_storage_dir()` (`src/core/storage_patch.py:12-28`) when `FLET_APP_STORAGE_DATA` points at `.flet/storage/data`. No Flet API surface; relevant only as the reason `storage_patch`/`StorageService` branch on that env var.
- `scripts/check_elf_alignment.py:1-105` — zero Flet API usage (stdlib `struct/zipfile/pathlib` only). Relevance is indirect but recorded per the task: it gates Android artifacts on the same 16 KB page-alignment requirement cited in the `target_arch` comment (`pyproject.toml:42-45`), i.e. the reason `x86_64` was dropped from `pyproject.toml:46`. Usage: `python scripts/check_elf_alignment.py <path.aab|.apk>` (`scripts/check_elf_alignment.py:4-5`); fail = any 64-bit ABI lib with `p_align < 16384` (`scripts/check_elf_alignment.py:24-25,78-82`); 32-bit ABIs warn-only (`scripts/check_elf_alignment.py:83-86`).

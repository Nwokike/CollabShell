# Flet Satellite Packages Audit — CollabShell

**Repo:** `/home/maikel/Desktop/kiri-apps/CollabShell` (HEAD 76a9d4b)  
**Venv:** `.venv/lib/python3.14/site-packages/`  
**Packages:** `flet_ads` (1.0.4), `flet_notifications` (0.1.4), `flet_desktop` (1.0.4), `flet_terminal` (0.3.9), `flet_platform_assets` (1.0.4), `flet_cli` (1.0.4)

---

## 1. flet_ads (1.0.4)

### What the package exposes

| Symbol | File:Line | Type | Notes |
|--------|-----------|------|-------|
| `BannerAd` | `flet_ads/banner_ad.py:9` | `@ft.control("BannerAd")` class | Extends `ft.LayoutControl, BaseAd`; requires `unit_id`; events: `on_load`, `on_error`, `on_open`, `on_close`, `on_impression`, `on_click`, `on_will_dismiss` (iOS only), `on_paid` (allowlisted) |
| `InterstitialAd` | `flet_ads/interstitial_ad.py:6` | `@ft.control("InterstitialAd")` class | Extends `ft.Service, BaseAd`; **single-use** — `show()` only once; events inherited from `BaseAd`: `on_load`, `on_error`, `on_open`, `on_close`, `on_impression`, `on_click`, `on_paid`; **no `on_reward` event** |
| `NativeAd` | `flet_ads/native_ad.py:9` | `@ft.control("NativeAd")` class | Extends `BannerAd`; requires `factory_id` OR `template_style` |
| `ConsentManager` | `flet_ads/consent_manager.py:14` | `@ft.control("ConsentManager")` class | Extends `ft.Service`; methods: `request_consent_info_update(params?)`, `is_consent_form_available()`, `get_consent_status()`, `can_request_ads()`, `get_privacy_options_requirement_status()`, `load_and_show_consent_form_if_required()`, `show_privacy_options_form()`, `reset()` |
| `BaseAd` | `flet_ads/base_ad.py:9` | `@dataclass` base | Fields: `unit_id: str`, `request: AdRequest`, `on_load`, `on_error`, `on_open`, `on_close`, `on_impression`, `on_click`; raises `FletUnsupportedPlatformException` on non-mobile |
| `AdRequest` | `flet_ads/types.py:62` | `@ft.value` class | `keywords`, `content_url`, `neighboring_content_urls`, `non_personalized_ads`, `http_timeout` (Android only), `extras` |
| `PaidAdEvent` | `flet_ads/types.py:40` | `@ft.value` event | `value: float`, `precision: PrecisionType`, `currency_code: str` |
| Enums | `flet_ads/types.py` | | `PrecisionType`, `ConsentStatus`, `PrivacyOptionsRequirementStatus`, `DebugGeography`, `NativeAdTemplateType`, `NativeTemplateFontStyle` |

### What the app uses

| Location | Code snippet |
|----------|--------------|
| `src/services/ad_service.py:145-150` | `fta.BannerAd(unit_id=self.banner_id, width=tokens.BANNER_WIDTH, height=tokens.BANNER_HEIGHT, on_error=lambda e: None)` |
| `src/services/ad_service.py:180-185` | `fta.InterstitialAd(unit_id=self.interstitial_id, on_load=self._handle_loaded, on_error=self._handle_error, on_close=self._handle_close)` |
| `src/services/ad_service.py:107-112` | `self._consent_manager = fta.ConsentManager()`; `await self._consent_manager.request_consent_info_update()`; `await self._consent_manager.load_and_show_consent_form_if_required()`; `self._can_request_ads = await self._consent_manager.can_request_ads()` |
| `src/services/ad_service.py:122-127` | `status = await self._consent_manager.get_privacy_options_requirement_status()`; `if status == fta.PrivacyOptionsRequirementStatus.REQUIRED: await self._consent_manager.show_privacy_options_form()` |
| `src/core/styles.py:132-136` | `fta.BannerAd(unit_id=unit_id, width=320, height=50, on_error=lambda e: None)` |

### Gap table — flet_ads

| # | Severity | App location | Package source | Problem | Better way |
|---|----------|--------------|----------------|---------|------------|
| 1 | **critical** | `ad_service.py:294-350` `show_rewarded_interstitial` | `interstitial_ad.py:6` | Uses `InterstitialAd` for rewarded ads; **no `on_reward` event exists** in `BaseAd` — reward is granted on `on_close` (line 320) which fires when user closes the ad, not when reward is earned. This grants reward even if user dismisses without watching. | Package lacks `RewardedAd` control. Use `InterstitialAd` only for non-rewarded interstitials. For rewarded, wait for upstream `RewardedAd` or implement server-side verification. |
| 2 | **high** | `ad_service.py:180-185` | `interstitial_ad.py:30-37` | `InterstitialAd` is documented as **single-use** ("Each instance is allowed to be shown only once"), but `ad_service.py` reuses the same instance in `_handle_close` → `preload_interstitial` (line 239) creating new instance. This is correct, but `_show_loaded` (line 216) calls `await self.interstitial.show()` without guarding against double-show if `_interstitial_shown` race occurs. | Keep current pattern (new instance per show) but add `if self._interstitial_shown: return` guard at top of `_show_loaded`. |
| 3 | **medium** | `ad_service.py:145` `styles.py:132` | `banner_ad.py:28` | `BannerAd` has `on_will_dismiss` (iOS only) and `on_paid` (allowlisted) — **not used**. App only uses `on_error`. | If revenue tracking needed, add `on_paid` handler (requires allowlist). |
| 4 | **medium** | `ad_service.py:107` | `consent_manager.py:44-58` | `request_consent_info_update` accepts `ConsentRequestParameters` with `tag_for_under_age_of_consent` and `consent_debug_settings` — **not used**. App calls without params. | Pass `ConsentRequestParameters(consent_debug_settings=...)` in debug builds to test EEA/US-state flows. |
| 5 | **low** | `ad_service.py:122` | `consent_manager.py:94-106` | `get_privacy_options_requirement_status` returns `PrivacyOptionsRequirementStatus` enum — app compares to `.REQUIRED` correctly. | No issue. |
| 6 | **info** | `ad_service.py:35-43` | `types.py` | Test IDs hardcoded in app (`BANNER_ID_ANDROID_TEST`, etc.) match package docs exactly. | Good — keep in sync with AdMob test IDs. |

### Options not exposed (flet_ads)

- `RewardedAd` control — does not exist in 1.0.4; only `InterstitialAd` available
- `AdRequest` advanced targeting (`keywords`, `content_url`, `neighboring_content_urls`, `extras`) — not used by app
- `ConsentDebugSettings` for test-device geography simulation — not used
- `NativeAdTemplateStyle` customization — not used (app doesn't use `NativeAd`)

---

## 2. flet_notifications (0.1.4)

### What the package exposes

| Symbol | File:Line | Type | Notes |
|--------|-----------|------|-------|
| `LocalNotifications` | `flet_notifications/local_notifications.py:43` | `@ft.control("LocalNotifications")` class | Extends `ft.Service`; headless — no need to add to page.controls; **cross-platform** (Android, iOS, macOS, Windows, Linux, Web) |
| `LocalNotifications.initialize()` | `line 147` | async method | Auto-called on mount; can re-init |
| `LocalNotifications.show()` | `line 155` | async method | Immediate notification; args: `id`, `title`, `body`, `payload`, `actions`, `style`, `show_progress`, `max_progress`, `progress`, `indeterminate`, `group_key`, `set_as_group_summary`, `group_alert_behavior`, `channel_id`, `options` |
| `LocalNotifications.schedule()` | `line 244` | async method | Scheduled notification; `when: datetime \| timedelta`, `match_components`, `schedule_mode`, `time_zone` |
| `LocalNotifications.periodically_show()` | `line 318` | async method | Repeating at fixed interval (`RepeatInterval` enum); **not supported on Linux/Web/Windows** |
| `LocalNotifications.cancel(id, tag?)` / `cancel_all()` | `line 216/230` | async methods | Cancel shown/scheduled |
| `LocalNotifications.request_permissions()` | `line 234` | async method | Returns `bool`; triggers OS prompt on Android 13+, iOS, Windows |
| `LocalNotifications` **events** | `lines 98-107` | | `on_tap`, `on_action`, `on_dismissed` — all receive `NotificationEvent(id, action_id, payload, input, response_type)` |
| `NotificationChannel` | `flet_notifications/channels.py:12` | `@dataclass` | Android 8.0+ channels; `id`, `name`, `description`, `group_id`, `importance`, `bypass_dnd`, `play_sound`, `sound`, `enable_vibration`, `vibration_pattern`, `show_badge`, `enable_lights`, `led_color` |
| `NotificationAction` / `NotificationActionInput` | `flet_notifications/actions.py:32/10` | `@dataclass` | Action buttons + inline reply |
| `NotificationOptions` + per-platform options | `flet_notifications/options.py:328` | `@dataclass` | `AndroidOptions`, `DarwinOptions`, `LinuxOptions`, `WindowsOptions`, `WebOptions` — full escape hatch |
| `Style` classes | `flet_notifications/styles.py` | | `BigTextStyle`, `BigPictureStyle`, `InboxStyle`, `MessagingStyle` |
| Enums | `flet_notifications/types.py` | | `RepeatInterval`, `DateTimeComponents`, `AndroidScheduleMode`, `Importance`, `GroupAlertBehavior`, `Priority`, `Visibility`, `InterruptionLevel`, `LinuxUrgency`, `WindowsScenario` |

### What the app uses

| Location | Usage |
|----------|-------|
| **NOWHERE in src/** | The app **does not import or use** `flet_notifications` at all. |
| `src/core/notifications.py` | Uses `ft.SnackBar` (flet core) for in-app toasts — **not** `flet_notifications.LocalNotifications`. |
| `version.json` | Claims: "Notifications system removed entirely" |

### Gap table — flet_notifications

| # | Severity | App location | Package source | Problem | Better way |
|---|----------|--------------|----------------|---------|------------|
| 1 | **critical** | `pyproject.toml:9` + `.venv/` | — | `flet_notifications==0.1.4` is **installed in venv** and listed as dependency (transitive via `flet-cli`?), but **zero usage** in app source. `version.json` says "removed entirely" yet package remains. | Remove from dependencies if truly unused. If local notifications needed (background, scheduled, cross-platform), migrate `core/notifications.py` to use `LocalNotifications`. |
| 2 | **high** | `src/core/notifications.py:14-51` | `local_notifications.py:155` | App implements custom `show_notification` using `ft.SnackBar` (in-app only, requires app running). `flet_notifications` provides **OS-level notifications** that work when app is backgrounded/killed, with scheduling, actions, channels. | If background notifications needed (e.g., Colab session expiry, long-running cell completion), replace `show_notification` with `LocalNotifications.show()` / `schedule()`. |
| 3 | **medium** | — | `local_notifications.py:234` | `request_permissions()` required on Android 13+, iOS — app never calls it. | Add permission request flow on first launch if adopting `flet_notifications`. |
| 4 | **info** | — | `patcher.py` | `flet-notifications-patch` CLI patches Android manifest for receivers, permissions, desugaring — **not run** in CI. | If adopting, add `flet-notifications-patch --project-root build/flutter` to build workflow. |

### Options not exposed (flet_notifications)

- All package features are unused — entire API surface is available but not leveraged.
- Key capabilities not used: **scheduled notifications** (`schedule`, `periodically_show`), **Android channels** (`create_notification_channel`), **foreground service** (`start_foreground_service`), **actions with inline reply**, **rich styles** (`BigPictureStyle`, `MessagingStyle`), **launch details** (`get_notification_app_launch_details`), **badge management** (iOS/macOS), **Do Not Disturb bypass** (`has_notification_policy_access`).

---

## 3. flet_desktop (1.0.4)

### What the package exposes

| Symbol | File:Line | Type | Notes |
|--------|-----------|------|-------|
| `open_flet_view(page_url, assets_dir, hidden)` | `flet_desktop/__init__.py:490` | sync function | Returns `(subprocess.Popen, pid_file)`; launches desktop client |
| `open_flet_view_async(page_url, assets_dir, hidden)` | `line 514` | async function | Returns `(asyncio.subprocess.Process, pid_file)` |
| `close_flet_view(pid_file)` | `line 558` | sync function | Terminates desktop process via PID file |
| `ensure_client_cached()` | `line 334` | sync function | Downloads/extracts Flet desktop client to `~/.flet/client/`; handles fingerprinting for patched clients |
| `get_artifact_filename()` | `line 147` | function | Returns platform-specific artifact name (e.g., `flet-linux-ubuntu22.04-light-x86_64.tar.gz`) |
| `flet_desktop.version.version` | `flet_desktop/version.py:1` | str | `"1.0.4"` |
| `win_taskbar.apply_relaunch_props_async(pid)` | `flet_desktop/win_taskbar.py:252` | async function | Stamps `System.AppUserModel.*` properties on Windows client window for correct taskbar identity |

### What the app uses

| Location | Usage |
|----------|-------|
| **NOWHERE in src/** | App **does not directly import** `flet_desktop`. |
| Used **indirectly** via `flet_cli.commands.run` (Handler.open_flet_view_and_wait → `flet_desktop.open_flet_view`) and `flet_cli.commands.pack` (compresses patched client). |

### Gap table — flet_desktop

| # | Severity | App location | Package source | Problem | Better way |
|---|----------|--------------|----------------|---------|------------|
| 1 | **info** | `pyproject.toml:12` | — | `flet-desktop==1.0.4` declared as Windows-only dependency; used by `flet run`/`flet pack` internally. No direct app usage. | Correct — keep as build-time dependency. |
| 2 | **low** | `.github/workflows/build-all.yml:106` | `__init__.py:334` | Linux build uses `flet build linux` which downloads client via `ensure_client_cached`. CI does not pre-warm cache. | Consider caching `~/.flet/client/` in CI for faster builds. |

### Options not exposed (flet_desktop)

- `FLET_DESKTOP_FLAVOR` env var (`full` vs `light`) — controls which client binary is downloaded (line 61-96)
- `FLET_LINUX_DISTRO` override for glibc matching (line 129-144)
- `FLET_CLIENT_URL` override for custom client download URL (line 325)
- `FLET_APP_ID` for Linux taskbar identity (line 466-487)
- `FLET_APP_USER_MODEL_ID` / `FLET_APP_RELAUNCH_COMMAND` / `FLET_APP_RELAUNCH_DISPLAY_NAME` / `FLET_APP_RELAUNCH_ICON` for Windows taskbar (win_taskbar.py:266-278)

---

## 4. flet_terminal (0.3.9)

### What the package exposes

| Symbol | File:Line | Type | Notes |
|--------|-----------|------|-------|
| `Terminal` | `flet_terminal/terminal.py:28` | `@control("FletTerminal")` class | Extends `ft.LayoutControl`; GPU-accelerated xterm.dart backend; props: `scrollback`, `font_family`, `font_size`, `cursor_blink`, `cursor_style`, `theme`, `read_only`, `auto_focus`, `ctrl_active`, `alt_active` |
| `Terminal` **events** | `lines 48-59` | | `on_data`, `on_resize`, `on_modifier_reset`, `on_title_change`, `on_bell`, `on_selection_change`, `on_copy`, `on_mount`, `on_shortcut` (ShortcutEvent) |
| `Terminal.write(data)` / `write_async` | `lines 181/153` | sync/async | Sends text/bytes to terminal via DataChannel (fast) or method invoke (fallback) |
| `Terminal.clear()` / `clear_async` | `lines 218/201` | sync/async | Clears scrollback & buffer |
| `Terminal.focus()` / `focus_async` | `lines 247/230` | sync/async | Requests keyboard focus |
| `Terminal.search(query, start, direction)` / `search_async` | `lines 290/259` | sync/async | Searches scrollback; results via `on_selection_change` |
| `Terminal.clear_selection()` / `select_all()` / `get_selection_async()` | `lines 323/352/364` | sync/async | Selection management |
| `Terminal.paste()` / `paste_async` | `lines 394/377` | sync/async | Reads system clipboard → feeds PTY |
| `Terminal.send_bytes(payload)` | `line 123` | sync | Raw bytes to Dart canvas |
| `Terminal.send_input(payload)` | `line 136` | sync | Virtual key payload to PTY input handler |
| `Terminal.set_on_bytes(handler)` | `line 117` | sync | Registers callback for raw bytes from Dart |
| `ShortcutEvent` | `flet_terminal/terminal.py:17` | `@dataclass` | `shortcut: str` — machine name (e.g., `"new_terminal"`) |
| `MobileTerminal` | `flet_terminal/mobile_terminal.py:22` | `ft.Column` composite | Combines `Terminal` + `ExtraKeysBar` + `TerminalSearchBar`; props: `show_extra_keys`, `show_search`, `show_settings`, all Terminal props + `extra_keys` |
| `MobileTerminal` **forwarded methods** | `lines 245-336` | | `send_bytes`, `send_input`, `write`, `clear`, `focus`, `search`, `clear_selection`, `select_all`, `get_selection_async`, `copy_selection_async`, `paste`, `set_on_bytes` |
| `MobileTerminal` **settings methods** | `lines 156-215` | | `set_theme(name)`, `set_cursor_style(style)`, `toggle_cursor_blink()`, `zoom_in/out/reset()`, `toggle_search()` |
| `MobileTerminal` **properties** | `lines 219-270` | | `ctrl_active`, `alt_active`, `font_size`, `cursor_blink`, `cursor_style`, `theme_name`, `ready`, `pending_count` |
| `BUILTIN_THEMES` / `get_theme()` | `flet_terminal/themes.py:9/69` | dict / function | `"Dracula"`, `"JetBrains Dark"`, `"Matrix Green"`, `"Colab Light"` |
| `ExtraKeysBar` | `flet_terminal/extra_keys.py:87` | `ft.Container` | Virtual keyboard toolbar with sticky modifiers, settings menu |
| `TerminalSearchBar` | `flet_terminal/search_bar.py:18` | `ft.Container` | Live search with match counter, next/prev stepping |
| `DEFAULT_EXTRA_KEYS` | `flet_terminal/extra_keys.py:70` | list[tuple] | `[("ESC", b"\x1b"), ("TAB", b"\t"), ("CTRL", None), ("ALT", None), ...]` |

### What the app uses

| Location | Code snippet |
|----------|--------------|
| `src/screens/session/terminal_panel.py:30` | `from flet_terminal import BUILTIN_THEMES, MobileTerminal` |
| `lines 339-348` | `mt = MobileTerminal(show_search=False, show_settings=False, scrollback=10000, font_family="JetBrains Mono", font_size=ps.zoom, theme=BUILTIN_THEMES.get(_active_theme_name(page)), auto_focus=False, expand=True)` |
| `lines 350-352` | `if not ps.blink: mt.toggle_cursor_blink()` |
| `lines 356-367` | `mt.set_on_bytes(handlers["on_bytes"])`; `mt.on_data = ...`; `mt.on_resize = handlers["on_resize"]`; `mt.on_mount = handlers["on_mount"]`; `mt.on_shortcut = lambda e: on_shortcut(e.shortcut)` |
| `lines 585-587` | `mt.set_theme(name)` |
| `lines 590-602` | `mt.zoom_in()` / `mt.zoom_out()` / `mt.reset_zoom()` |
| `lines 611-614` | `mt.toggle_cursor_blink()` |
| `lines 616-620` | `mt.toggle_search()` |
| `line 626` | `page.run_task(entry.client.send_input, b"\x0c")` (Ctrl+L via client, not `mt.clear()`) |
| `lines 628-650` | `await entry.mt.get_selection_async()` → `ft.Clipboard().set(text)` → `entry.mt.clear_selection()` |
| `lines 661-665` | `entry.mt.paste()` |
| `lines 364-367` | `mt.on_shortcut = lambda e: on_shortcut(e.shortcut)` — handles `"new_terminal"`, `"close_terminal"`, `"switch_terminal_N"`, `"prev_terminal"`, `"next_terminal"`, `"toggle_search"`, `"clear"`, `"copy"`, `"paste"`, `"zoom_in"`, `"zoom_out"`, `"zoom_reset"`, `"help"` |

### Gap table — flet_terminal

| # | Severity | App location | Package source | Problem | Better way |
|---|----------|--------------|----------------|---------|------------|
| 1 | **high** | `terminal_panel.py:364-367` | `terminal.py:56` | `on_shortcut` handler receives `ShortcutEvent` with `e.shortcut` — app handles `"clear"` by sending `b"\x0c"` (Ctrl+L) to Colab client (line 626) instead of calling `mt.clear()` which clears **local xterm buffer only**. This is correct for Colab (remote shell), but doc should clarify. | Keep current — `mt.clear()` would only clear local view, not remote PTY. |
| 2 | **medium** | `terminal_panel.py:345` | `themes.py:9` | `BUILTIN_THEMES.get(_active_theme_name(page))` — `_active_theme_name` returns `"Colab Light"` or `"JetBrains Dark"`; both exist in `BUILTIN_THEMES`. | Good. |
| 3 | **medium** | `terminal_panel.py:632` | `mobile_terminal.py:296` | `copy_selection_async` uses `ft.Clipboard()` (flet core) not `mt.copy_selection_async()` which exists in `MobileTerminal` (line 296-320). `mt.copy_selection_async` does same thing but also fires `on_copy` event. | Use `mt.copy_selection_async()` for consistency. |
| 4 | **low** | `terminal_panel.py:356` | `terminal.py:117` | `mt.set_on_bytes(handlers["on_bytes"])` registers raw bytes callback — used for PTY input (line 292). Correct. | Good. |
| 5 | **low** | `terminal_panel.py:264-278` | `terminal.py:259` | `replay_scrollback` calls `mt.clear_pending()` then `mt.send_bytes(chunk)` for each buffered chunk. `send_bytes` queues when channel not ready. Correct. | Good. |
| 6 | **info** | `terminal_panel.py:364` | `terminal.py:56` | `on_shortcut` event names match `DEFAULT_EXTRA_KEYS` / `ExtraKeysBar` internal shortcuts: `"new_terminal"`, `"close_terminal"`, `"switch_terminal_N"`, `"prev_terminal"`, `"next_terminal"`, `"toggle_search"`, `"clear"`, `"copy"`, `"paste"`, `"zoom_in"`, `"zoom_out"`, `"zoom_reset"`, `"help"`. | Good — app handles all documented shortcuts. |

### Options not exposed (flet_terminal)

- `Terminal` DataChannel direct access (`_channel`, `_on_bytes_handler`) — internal
- `ExtraKeysBar` custom key layouts — `keys` parameter accepted but not used (app uses `DEFAULT_EXTRA_KEYS`)
- `TerminalSearchBar` debounce timing (hardcoded 350ms) — not configurable
- `frozen_support.thaw` / `control_update` — internal imperative update helpers for declarative components

---

## 5. flet_platform_assets (1.0.4)

### What the package exposes

| Symbol | File:Line | Type | Notes |
|--------|-----------|------|-------|
| `load_source(path)` | `flet_platform_assets/_source.py:24` | function | Returns `(RGBA Image, pre_rendered: bool)`; handles EXIF, animated GIF, .ico/.icns, non-square, >2048px |
| `render_icons(source, options, spec, platform, pre_rendered, derived)` | `_icons.py:202` | function | Pure render → `RenderResult(assets, warnings, ico, stale)`; platforms: `ios`, `macos`, `android`, `windows`, `web`, `linux` |
| `render_splash(light, dark, options, platform, derived)` | `_splash.py:67` | function | Pure render → `RenderResult`; platforms: `android`, `ios`, `web` |
| `write(result, project_dir, declared_only=True)` | `_write.py:13` | function | Persists assets to Flutter project; `declared_only` prevents writing undeclared files |
| `IconOptions` / `SplashOptions` | `_models.py:65/89` | `@dataclass` | `background`, `macos_style` (`auto`/`grid`/`raw`), `application_id` / `color`, `dark_color`, `icon_background`, `icon_fit` |
| `AssetSpec` / `Target` | `_models.py:45/23` | `@dataclass` | Declarative file list per platform; `relative_path`, `size`, `opaque`, `frame` |
| `DEFAULT_SPECS` | `_icons.py:166` | dict | Stock Flutter project layout per platform |
| `linux_targets(application_id)` | `_icons.py:436` | function | Builds hicolor icon targets for Linux desktop entry |

### What the app uses

| Location | Usage |
|----------|-------|
| **NOWHERE in src/** | App **does not import** `flet_platform_assets`. |
| Used **indirectly** by `flet_cli.commands.build` → `customize_icons()` / `customize_splash_images()` during `flet build`. |

### Gap table — flet_platform_assets

| # | Severity | App location | Package source | Problem | Better way |
|---|----------|--------------|----------------|---------|------------|
| 1 | **info** | `pyproject.toml` (not listed) | — | Not a direct dependency; pulled transitively by `flet-cli`. Used at build time only. | Correct — no action needed. |
| 2 | **low** | `.github/workflows/build-all.yml` | `_icons.py:497` | `web_targets_from_manifest(manifest)` can generate web icon spec from project's `manifest.json` — not used (build uses `DEFAULT_SPECS`). | If PWA manifest customized, build would auto-adapt. |

### Options not exposed (flet_platform_assets)

- All rendering options (`IconOptions.macos_style`, `SplashOptions.icon_fit`, `FRAMING` margins per platform) — configurable via `pyproject.toml` `[tool.flet.icons]` / `[tool.flet.splash]` but not used in this project.

---

## 6. flet_cli (1.0.4)

### What the package exposes (entry points)

| Command | Module | Description |
|---------|--------|-------------|
| `flet create` | `commands/create.py` | Scaffold new Flet project |
| `flet run` | `commands/run.py` | Hot-reload dev server; `flet run [script] [--web|--ios|--android] [-d] [-r] [-n] [-w] [-a] [-- --script-args]` |
| `flet build` | `commands/build.py` | Multi-platform build: `macos`, `linux`, `windows`, `web`, `apk`, `aab`, `ipa`, `ios-simulator`; `flet build <target> [--output] [--split-per-abi] [-- --flutter-args]` |
| `flet pack` | `commands/pack.py` | PyInstaller desktop packaging; `flet pack <script> [-i icon] [-n name] [--onedir] [--add-data] [--hidden-import] [--codesign-identity] [--bundle-id] [--debug-console] [--uac-admin] [-- --pyinstaller-args]` |
| `flet serve` | `commands/serve.py` | Static web server for `flet build web` output |
| `flet test` | `commands/test.py` | Run pytest with Flet test utilities |
| `flet debug` | `commands/debug.py` | Debug Flutter build |
| `flet devices` / `emulators` | `commands/devices.py` / `emulators.py` | List/start Android/iOS devices & emulators |
| `flet doctor` | `commands/doctor.py` | Environment health check |
| `flet clean` | `commands/clean.py` | Remove build artifacts |
| `flet publish` | `commands/publish.py` | Publish to app stores |
| `flet mcp` | `commands/mcp.py` | MCP server (if `flet-mcp` installed) |
| `flet --version [-V] [--json]` | `cli.py:37` | Version info |

### What the app uses

| Location | Usage |
|----------|-------|
| `.github/workflows/build-all.yml:106` | `uv run flet build apk --yes --project collabshell --product "Collab Shell" --org ng.kiri --build-version ${{ env.BUILD_VERSION }} --build-number ${{ env.BUILD_NUMBER }} --split-per-abi -v --exclude pyarrow --skip-flutter-doctor` |
| `.github/workflows/build-all.yml:152` | `uv run flet build aab ...` (with `CHANNEL = "play"` marker) |
| `.github/workflows/build-all.yml:173` | `uv run flet build windows ...` |
| `.github/workflows/build-all.yml:242` | `uv run flet build linux ...` |
| `pyproject.toml:11` | `flet-cli==1.0.4; sys_platform == 'win32'` (Windows-only dep) |

### Gap table — flet_cli

| # | Severity | App location | Package source | Problem | Better way |
|---|----------|--------------|----------------|---------|------------|
| 1 | **info** | `build-all.yml:106` | `build.py:106` | `--split-per-abi` used for APK; `flet_cli` passes `--split-per-abi` to `flutter build apk` (line 166-167). Correct. | Good. |
| 2 | **info** | `build-all.yml:144` | `build.py:306` | AAB build writes `CHANNEL = "play"` to `src/core/channel.py` before build — consumed by app at runtime. `flet_cli` doesn't know about this; it's a project convention. | Works but fragile; consider `--dart-define=CHANNEL=play` instead. |
| 3 | **low** | `pack.py:500` | `pack.py:500` | `copy_flet_bin()` copies `flet_desktop` client binaries into temp dir, patches icon/version info, compresses to `flet-windows.zip` / `flet-macos.tar.gz` / Linux artifact so `flet_desktop.ensure_client_cached()` finds patched client at runtime. | Correct — this is how `flet pack` embeds custom icon/metadata. |

### Options not exposed (flet_cli)

- `flet build` per-platform options: `--macos-distribution` (`none`/`developer-id`/`app-store`), `--macos-signing-identity`, `--macos-installer-identity`, `--macos-provisioning-profile`, `--macos-notary-profile`, `--ios-provisioning-profile`, `--ios-team-id`, `--android-key-store`, `--android-key-alias`, etc. — used via `pyproject.toml` `[tool.flet.android/macos/ios]`
- `flet pack` PyInstaller passthrough `--pyinstaller-build-args` — not used in CI

---

## Summary: Version.json vs Reality

| Claim in `version.json` | Reality |
|-------------------------|---------|
| "Notifications system removed entirely" | **False** — `flet_notifications 0.1.4` is installed in venv (transitive dep). App's `src/core/notifications.py` exists and uses `ft.SnackBar` (flet core), **not** `flet_notifications`. Package is unused but present. |
| "Ad Service fixed to DDGS parity" | **Mostly true** — `ad_service.py` correctly uses `InterstitialAd` (single-use), consent flow, 60s cooldown, premium gate. **Critical gap**: `show_rewarded_interstitial` uses `InterstitialAd` which has **no `on_reward` event** — reward granted on `on_close` (user dismisses), not on actual reward completion. |

---

## Ad Service vs flet_ads: When is reward legitimately granted?

**Package reality (flet_ads 1.0.4):**
- Only `BannerAd`, `InterstitialAd`, `NativeAd` exist — **no `RewardedAd` control**
- `InterstitialAd` events: `on_load`, `on_error`, `on_open`, `on_close`, `on_impression`, `on_click`, `on_paid`
- **No `on_reward` / `on_rewarded` / `on_user_earned_reward` event**

**App code (`ad_service.py:294-350`):**
```python
self._active_rewarded_ad = fta.InterstitialAd(
    unit_id=self.interstitial_id,  # Uses INTERSTITIAL ID, not rewarded ID!
    on_load=lambda e: self.page.run_task(_show, e),
    on_close=lambda e: self.page.run_task(_close, e),  # ← reward granted HERE
    on_error=...
)
```

**Problem:** The app uses an **interstitial ad unit ID** (`INTERSTITIAL_ID_ANDROID_PROD`) for "rewarded" ads, and grants the reward in `on_close` — which fires when the user **closes the ad for any reason** (watched fully, dismissed early, error). This is **not a legitimate rewarded ad implementation**.

**Legitimate rewarded ad requires:**
1. A dedicated **rewarded ad unit ID** (different from interstitial)
2. A **`RewardedAd` control** with `on_reward` / `on_user_earned_reward` callback
3. Server-side reward validation (recommended)

**Current state:** `flet_ads 1.0.4` does not expose `RewardedAd`. The app's "rewarded interstitial" is a misnomer — it's just an interstitial that grants a reward on close. This will **over-grant rewards** and violate AdMob policy.

**Recommendation:** Wait for `flet_ads` to add `RewardedAd` (track upstream), or implement server-side reward verification with a dedicated rewarded ad unit. Do not use current `show_rewarded_interstitial` for production rewards.

---

## Cross-Package Dead Imports / Unused Dependencies

| Package | Installed? | Imported in src/ | Used at build? | Verdict |
|---------|------------|------------------|----------------|---------|
| `flet_ads` | ✅ | ✅ (`ad_service.py`, `styles.py`) | — | **Used** |
| `flet_notifications` | ✅ | ❌ | — | **Dead weight** — remove from deps if not adopting |
| `flet_desktop` | ✅ | ❌ | ✅ (via `flet run`/`pack`) | **Transitive build dep** — keep |
| `flet_terminal` | ✅ | ✅ (`terminal_panel.py`) | — | **Used** |
| `flet_platform_assets` | ✅ | ❌ | ✅ (via `flet build`) | **Transitive build dep** — keep |
| `flet_cli` | ✅ (Windows) | ❌ | ✅ (CI `flet build`) | **Build tool** — keep |

---

## Final Recommendations

1. **Remove `flet_notifications`** from dependency resolution (not in `pyproject.toml` directly but pulled transitively) unless adopting OS-level notifications.
2. **Fix rewarded ads**: Do not grant rewards on `InterstitialAd.on_close`. Wait for `RewardedAd` in `flet_ads` or implement server-side verification.
3. **Adopt `flet_notifications`** if background/scheduled notifications needed (Colab session alerts, long-running task completion).
4. **Add `flet-notifications-patch`** to CI if adopting `flet_notifications` for Android.
5. **Consider `flet_desktop` cache warming** in CI for faster Linux/macOS builds.
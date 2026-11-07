# Flet 1.1.0-dev Line Research — flet-notifications 1.1.0-dev.4

**Repo:** `/home/maikel/Desktop/kiri-apps/ColabShell` (branch `main`)  
**Target file:** `/home/maikel/Desktop/kiri-apps/ColabShell/docs/research-05-flet-1.1.0-line.md`  
**Research date:** 2026-11-03  
**Source data:** PyPI JSON (`https://pypi.org/pypi/<pkg>/json`), PyPI file URLs, GitHub releases API (`api.github.com/repos/flet-dev/flet/releases`), downloaded wheels/sdists extracted to `/tmp/fn-dev4/` and `/tmp/flet-dev4/`.

---

## 1. PyPI Versions — Full Table

All packages were queried via `https://pypi.org/pypi/<pkg>/json` which lists every release including pre-releases. The `1.1.0-dev` series is uploaded on a shared cadence; **flet-notifications 1.1.0.dev4 is available TODAY (2026-11-03)**, dev.3 yesterday (2026-10-30), dev.2 2026-10-28.

| pkg | versions (newest first, with dates) | 1.1.0-dev series? | recommended pin |
|-----|--------------------------------------|-------------------|-----------------|
| **flet** | 1.1.0.dev4 (2026-11-03 TODAY), 1.1.0.dev3 (2026-10-30), 1.1.0.dev2 (2026-10-28), 1.1.0.dev1 (2026-10-18), 1.1.0.dev0 (2026-10-15), 1.0.5 (2026-10-21), 1.0.4 (2026-10-08), 1.0.3 … | YES — dev0..dev4 | `flet==1.1.0.dev4` |
| **flet-ads** | 1.1.0.dev4 (2026-11-03), dev3 (2026-10-30), dev2 (2026-10-28), dev1 (2026-10-18), dev0 (2026-10-15), 1.0.5 (2026-10-21), … | YES — dev0..dev4 | `flet-ads==1.1.0.dev4` |
| **flet-cli** | 1.1.0.dev4 (2026-11-03), dev3 (2026-10-30), dev2 (2026-10-28), dev1 (2026-10-18), dev0 (2026-10-15), 1.0.5 (2026-10-21), … | YES — dev0..dev4 | `flet-cli==1.1.0.dev4` |
| **flet-desktop** | 1.1.0.dev4 (2026-11-03), dev3 (2026-10-30), dev2 (2026-10-28), dev1 (2026-10-18), dev0 (2026-10-15), 1.0.5 (2026-10-21), … | YES — dev0..dev4 | `flet-desktop==1.1.0.dev4` |
| **flet-platform-assets** | 1.1.0.dev4 (2026-11-03), dev3 (2026-10-30), dev2 (2026-10-28), dev1 (2026-10-18), dev0 (2026-10-15), 1.0.5 (2026-10-21), 0.1.0 … | YES — dev0..dev4 | `flet-platform-assets==1.1.0.dev4` |
| **flet-terminal** | 0.4.2 (2026-10-17), 0.4.1, 0.4.0, 0.3.9 … | NO — no 1.1.0-dev series exists; latest is 0.4.2 | `flet-terminal==0.4.2` |
| **flet-notifications** | 1.1.0.dev4 (2026-11-03 TODAY), 1.1.0.dev3 (2026-10-30 yesterday), 1.1.0.dev2 (2026-10-28), 0.1.4 (2026-10-11), 0.1.3, 0.1.2, 0.1.1, 0.1.0 | YES — dev2..dev4 | `flet-notifications==1.1.0.dev4` |

### Answers to the version questions

**Which flet core version does the 1.1.0-dev line pair with?**
`flet-notifications 1.1.0.dev4` declares `Requires-Dist: flet==1.1.0.dev4` (strict pin, see `/tmp/fn-dev4/extracted/flet_notifications-1.1.0.dev4.dist-info/METADATA:14`). The whole 1.1.0-dev family (flet, flet-ads, flet-cli, flet-desktop, flet-platform-assets) is co-released with the same `1.1.0.devN` version on the same day. So **flet-notifications 1.1.0.dev4 pairs with flet core 1.1.0.dev4**.

**Does flet 1.1.0-dev.x exist?**
Yes. `flet 1.1.0.dev4` was uploaded 2026-11-03 (today), with dev3/yesterday, dev2, dev1, dev0 back to 2026-10-15. `flet 1.1.0.dev4` wheel is at `https://files.pythonhosted.org/.../flet-1.1.0.dev4-py3-none-any.whl` (also on the GitHub release `v1.1.0.dev4`, published 2026-11-03T02:36:36Z).

**What do flet-ads/flet-cli/flet-desktop 1.1.0-dev require?**
They are co-released with flet core at the identical `1.1.0.devN` version and each requires the matching flet core (same strict-pin pattern as flet-notifications). They must be bumped **together** — you cannot mix flet 1.0.5 with flet-ads 1.1.0.dev4.

**flet-terminal** has no 1.1.0-dev line at all (still 0.4.2) and is unrelated to the notifications/wakelock work.

---

## 2. flet-notifications 1.1.0-dev.4 — FULL API Reference

Downloaded wheel: `flet_notifications-1.1.0.dev4-py3-none-any.whl` (85,275 bytes)  
Extracted to: `/tmp/fn-dev4/extracted/`  
Package: `/tmp/fn-dev4/extracted/flet_notifications/` (14 `.py` files)  
Metadata (`Requires-Dist: flet==1.1.0.dev4`, `Requires-Dist: tzdata`, `Requires-Python: >=3.10`, Apache-2.0): `/tmp/fn-dev4/extracted/flet_notifications-1.1.0.dev4.dist-info/METADATA`

### 2.1 Python package files (every .py)

| file (path:line) | contents |
|------------------|----------|
| `flet_notifications/__init__.py:1-132` | Re-exports every public symbol; `__all__` lists 47 names (see section 2.2). |
| `flet_notifications/notifications.py:40-1158` | `Notifications` service — the main class (see 2.3). |
| `flet_notifications/types.py:1-327` | `RepeatInterval`, `DateTimeComponents`, `NotificationActionInput`, `NotificationAction`, `PendingNotification`, `ActiveNotification`, `NotificationOptions` (see 2.4). |
| `flet_notifications/android.py:28-1359` | Android enums + `NotificationChannel`, `AndroidProgress`, `AndroidGroup`, `AndroidOptions` (see 2.5). |
| `flet_notifications/android_styles.py:26-354` | `AndroidStyle` (ABC), `AndroidIcon` (ABC), `AndroidBitmap` (ABC), `AndroidDrawableBitmap`, `AndroidFileBitmap`, `AndroidBytesBitmap`, `AndroidContentUriIcon`, `AndroidBigTextStyle`, `AndroidBigPictureStyle`, `AndroidInboxStyle`, `AndroidPerson`, `AndroidMessage`, `AndroidMessagingStyle` (see 2.6). |
| `flet_notifications/darwin.py:13-186` | `DarwinInterruptionLevel`, `DarwinOptions` (see 2.7). |
| `flet_notifications/linux.py:14-188` | `LinuxUrgency`, `LinuxCategory`, `LinuxOptions` (see 2.8). |
| `flet_notifications/web.py:12-107` | `WebDirection`, `WebOptions` (see 2.9). |
| `flet_notifications/windows.py:17-281` | `WindowsScenario`, `WindowsDuration`, `WindowsSound`, `WindowsProgress`, `WindowsOptions` (see 2.10). |
| `flet_notifications/events.py:11-58` | `NotificationEvent`, `NotificationActionEvent` (see 2.11). |
| `flet_notifications/exceptions.py:12-88` | `NotificationException` + 4 subclasses + `error_from_bridge()` (see 2.12). |
| `flet_notifications/scheduling.py:12-78` | `build_schedule_args()`, `build_periodic_args()` (see 2.13). |
| `flet_notifications/validation.py:11-87` | `validate_arguments()`, `validate_notification_id()`, `validate_non_empty()`, `non_negative_duration()` (see 2.14). |

### 2.2 Public symbols exported from `flet_notifications/__init__.py`

`__init__.py:76-131` `__all__` (47 names): `ActiveNotification`, `AndroidAudioAttributesUsage`, `AndroidBigPictureStyle`, `AndroidBigTextStyle`, `AndroidBitmap`, `AndroidBytesBitmap`, `AndroidCategory`, `AndroidContentUriIcon`, `AndroidDrawableBitmap`, `AndroidFileBitmap`, `AndroidFlag`, `AndroidForegroundServiceType`, `AndroidGroup`, `AndroidGroupAlertBehavior`, `AndroidIcon`, `AndroidImportance`, AndroidOptions, `AndroidPriority`, `AndroidProgress`, `AndroidScheduleMode`, `AndroidServiceStartType`, `AndroidVisibility`, `DarwinInterruptionLevel`, `DarwinOptions`, `DateTimeComponents`, `LinuxCategory`, `LinuxOptions`, `LinuxUrgency`, `NotificationAction`, `NotificationActionEvent`, `NotificationActionInput`, `NotificationChannel`, `NotificationEvent`, `NotificationException`, `NotificationInitializationException`, `NotificationInvalidArgumentException`, `NotificationOptions`, `NotificationPermissionException`, `NotificationUnsupportedPlatformException`, `Notifications`, `PendingNotification`, `RepeatInterval`, `WebDirection`, `WebOptions`, `WindowsDuration`, `WindowsOptions`, `WindowsProgress`, `WindowsScenario`, `WindowsSound`.

### 2.3 `Notifications` service — `flet_notifications/notifications.py`

**Class:** `@ft.control("Notifications") class Notifications(ft.Service)` — `notifications.py:68`  
Decorated as a Flet control; registers as a `Service` with the page (auto-registered on construction in page context). Subclasses `flet.Service` (`flet/controls/services/service.py`). One instance per page; keep its reference for showing/cancelling notifications and handling responses.

**Class attributes (configuration properties):**
- `android_default_icon: str = "flet_notifications_icon"` — `notifications.py:132`. Default small Android notification icon (bundled silhouette of Flet logo). Supply a drawable resource name without extension.
- `windows_app_name: str | None = None` — `notifications.py:145`. Windows app name for notifications/settings.
- `windows_app_user_model_id: str | None = None` — `notifications.py:152`. Windows AppUserModelID; `None` derives from the executable.
- `windows_guid: str | None = None` — `notifications.py:168`. Windows activation GUID; `None` derived from `windows_app_user_model_id`.
- `on_tap: ft.EventHandler[NotificationEvent["Notifications"]] \| None = None` — `notifications.py:178`. Fired when user selects the notification body.
- `on_action: ft.EventHandler[NotificationActionEvent["Notifications"]] \| None = None` — `notifications.py:197`. Fired when user selects an action button; carries `action_id` and `input`.

**Methods (all `async`):**

| method | signature (path:line) | purpose |
|--------|----------------------|---------|
| `show` | `show(self, id, *, title=None, body=None, payload=None, actions=None, options=None) -> None` — `notifications.py:265` | Display a local notification immediately. Reusing an ID updates the existing notification. |
| `cancel` | `cancel(self, id, *, tag=None) -> None` — `notifications.py:324` | Remove a displayed notification and cancel its scheduled request. |
| `cancel_all` | `cancel_all(self) -> None` — `notifications.py:347` | Remove all displayed and scheduled notifications. |
| `request_permissions` | `request_permissions(self, *, alert=True, sound=True, badge=True, critical=False, provisional=False) -> bool` — `notifications.py:362` | Request notification authorization (Android 13+ `POST_NOTIFICATIONS`, iOS/macOS prompt, Web browser permission). Returns bool. |
| `schedule` | `schedule(self, id, *, when, title=None, body=None, payload=None, actions=None, match_components=None, options=None, schedule_mode=AndroidScheduleMode.INEXACT_ALLOW_WHILE_IDLE) -> None` — `notifications.py:432` | Schedule for a date/delay or recurring calendar match. Android/iOS/macOS/Windows. |
| `periodically_show` | `periodically_show(self, id, *, repeat_interval, title=None, body=None, payload=None, actions=None, schedule_mode=…, options=None) -> None` — `notifications.py:551` | Repeat after a fixed elapsed interval (≥1 minute). Android/iOS/macOS. |
| `cancel_all_pending` | `cancel_all_pending(self) -> None` — `notifications.py:640` | Cancel all scheduled notifications without removing displayed ones. |
| `get_pending` | `get_pending(self) -> list[PendingNotification]` — `notifications.py:668` | Query scheduled future-delivery notifications. |
| `can_schedule_exact_alarms` | `can_schedule_exact_alarms(self) -> bool` — `notifications.py:700` | Check Android exact-alarm authorization. |
| `request_exact_alarm_permission` | `request_exact_alarm_permission(self) -> bool` — `notifications.py:718` | Open Android exact-alarm settings screen. |
| `create_channel` | `create_channel(self, channel: NotificationChannel) -> None` — `notifications.py:744` | Create/update an Android notification channel (Android 8.0+). |
| `delete_channel` | `delete_channel(self, channel_id: str) -> None` — `notifications.py:770` | Delete an Android notification channel. |
| `get_channels` | `get_channels(self) -> list[NotificationChannel]` — `notifications.py:790` | Query the app's Android notification channels. |
| `start_foreground_service` | `start_foreground_service(self, id, *, title=None, body=None, payload=None, actions=None, options=None, start_type=None, service_types=None) -> None` — `notifications.py:805` | **Start an Android foreground service with a visible notification** (keeps app alive when minimized). Requires `id != 0`, Android only. |
| `stop_foreground_service` | `stop_foreground_service(self) -> None` — `notifications.py:883` | Stop the Android foreground service. |
| `update_windows_progress` | `update_windows_progress(self, id: int, progress: WindowsProgress) -> bool` — `notifications.py:898` | Update a shown Windows notification's progress bar in place (no re-toast). Returns whether updated. |
| `are_notifications_enabled` | `are_notifications_enabled(self) -> bool` — `notifications.py:963` | Check application-level notification authorization where supported. |
| `open_settings` | `open_settings(self) -> None` — `notifications.py:987` | Open the OS notification settings for this app (Android/iOS/macOS only). |
| `get_active` | `get_active(self) -> list[ActiveNotification]` — `notifications.py:1014` | Query delivered, non-dismissed notifications. |
| `request_full_screen_intent_permission` | `request_full_screen_intent_permission(self) -> bool` — `notifications.py:1046` | Request Android full-screen notification intent access. |
| `has_notification_policy_access` | `has_notification_policy_access(self) -> bool` — `notifications.py:1068` | Check Android notification-policy (DND bypass) access. |
| `request_notification_policy_access` | `request_notification_policy_access(self) -> bool` — `notifications.py:1084` | Open Android notification-policy access settings. |
| `create_channel_group` | `create_channel_group(self, group_id, *, name, description=None) -> None` — `notifications.py:1103` | Create an Android channel group. |
| `delete_channel_group` | `delete_channel_group(self, group_id: str) -> None` — `notifications.py:1136` | Delete an Android channel group and its channels. |

**Foreground service / ongoing / notification flags** — `start_foreground_service` takes `start_type` (`AndroidServiceStartType`, defaults to sticky) and `service_types` (`list[AndroidForegroundServiceType]`). The notification itself can be marked ongoing via `AndroidOptions.ongoing` (bool) and `AndroidFlag.ONGOING_EVENT`. There is no separate "ongoing" toggle on the service beyond the notification options.

**Importance** — `AndroidImportance` enum (`unspecified`/`min`/`none`/`low`/`default`/`high`/`max`) set on `NotificationChannel.importance`; `AndroidPriority` (`min`/`low`/`default`/`high`/`max`) for Android 7.1 and earlier via `AndroidOptions.priority`.

**Icon** — `AndroidOptions.icon: str | None` (drawable resource name, no extension; defaults to `Notifications.android_default_icon`); `NotificationChannel.sound`/`led_color` etc. for channel-level audio/light.

### 2.4 Types — `flet_notifications/types.py`

- `RepeatInterval` (Enum, `types.py:24`): `EVERY_MINUTE="everyMinute"`, `HOURLY="hourly"`, `DAILY="daily"`, `WEEKLY="weekly"`. Used by `periodically_show`.
- `DateTimeComponents` (Enum, `types.py:50`): `TIME="time"`, `DAY_OF_WEEK_AND_TIME="dayOfWeekAndTime"`, `DAY_OF_MONTH_AND_TIME="dayOfMonthAndTime"`, `DATE_AND_TIME="dateAndTime"`. Used by `schedule(match_components=...)`.
- `NotificationActionInput` (`@ft.value(kw_only=True)`, `types.py:78`): `label: str\|None`, `choices: list[str]`, `allow_free_form: bool=True`, `allowed_mime_types: list[str]`. Used by `NotificationAction.input`.
- `NotificationAction` (`@ft.value(kw_only=True)`, `types.py:134`): `id: str` (non-empty), `title: str` (non-empty), `destructive: bool=False`, `foreground: bool=True`, `require_authentication: bool=False`, `cancel_notification: bool=True`, `input: NotificationActionInput\|None`.
- `PendingNotification` (`@dataclass`, `types.py:223`): `id: int`, `title: str\|None`, `body: str\|None`, `payload: str\|None`. Returned by `get_pending`.
- `ActiveNotification` (`@dataclass`, `types.py:247`): `id`, `channel_id`, `group_key`, `tag`, `title`, `body`, `payload`, `big_text` (all `str\|None`). Returned by `get_active`.
- `NotificationOptions` (`@ft.value(kw_only=True)`, `types.py:284`): `android: AndroidOptions\|None`, `ios: DarwinOptions\|None`, `macos: DarwinOptions\|None`, `linux: LinuxOptions\|None`, `windows: WindowsOptions\|None`, `web: WebOptions\|None`.

### 2.5 Android — `flet_notifications/android.py`

**Enums:** `AndroidAudioAttributesUsage` (`python:28`, 13 members), `AndroidFlag` (`IntFlag`, `python:82`: `NONE=0`, `ONGOING_EVENT=2`, `INSISTENT=4`, `ONLY_ALERT_ONCE=8`, `AUTO_CANCEL=16`, `NO_CLEAR=32`, `LOCAL_ONLY=256`, `GROUP_SUMMARY=512`), `AndroidScheduleMode` (`python:165`: `ALARM_CLOCK`, `EXACT`, `EXACT_ALLOW_WHILE_IDLE`, `INEXACT`, `INEXACT_ALLOW_WHILE_IDLE`), `AndroidImportance` (`python:246`: `UNSPECIFIED`, `MIN`, `NONE`, `LOW`, `DEFAULT`, `HIGH`, `MAX`), `AndroidGroupAlertBehavior` (`python:287`: `ALL`, `SUMMARY`, `CHILDREN`), `AndroidCategory` (`python:305`, 19 members incl. `ALARM`, `CALL`, `MESSAGE`, `REMINDER`, `SERVICE`, `PROGRESS`, …), `AndroidServiceStartType` (`python:374`: `STICKY_COMPATIBILITY`, `STICKY`, `NOT_STICKY`, `REDELIVER_INTENT`), `AndroidForegroundServiceType` (`python:415`, 13 members incl. `CAMERA`, `CONNECTED_DEVICE`, `DATA_SYNC`, `HEALTH`, `LOCATION`, `MEDIA_PLAYBACK`, `MEDIA_PROJECTION`, `MICROPHONE`, `PHONE_CALL`, `REMOTE_MESSAGING`, `SHORT_SERVICE`, `SPECIAL_USE`, `SYSTEM_EXEMPTED` — each documents its pyproject.toml permission entries), `AndroidPriority` (`python:829`), `AndroidVisibility` (`python:855`: `PUBLIC`, `PRIVATE`, `SECRET`).

- `NotificationChannel` (`@ft.value(kw_only=True)`, `android.py:875`): `id` (non-empty), `name` (non-empty), `description`, `group_id`, `importance: AndroidImportance=DEFAULT`, `bypass_dnd: bool=False`, `play_sound: bool=True`, `sound: str\|None`, `enable_vibration: bool=True`, `vibration_pattern: list[int]\|None`, `show_badge: bool=True`, `enable_lights: bool=False`, `led_color: ft.ColorValue\|None`, `audio_attributes_usage: AndroidAudioAttributesUsage=NOTIFICATION`.
- `AndroidProgress` (`@ft.value(kw_only=True)`, `android.py:1022`): `value: int=0` (ge 0, le max), `max: int=100` (gt 0), `indeterminate: bool=False`.
- `AndroidGroup` (`@ft.value(kw_only=True)`, `android.py:1047`): `key: str` (non-empty), `summary: bool=False`, `alert_behavior: AndroidGroupAlertBehavior=ALL`.
- `AndroidOptions` (`@ft.value(kw_only=True)`, `android.py:1072`): `channel`, `style`, `progress`, `group`, `icon`, `priority`, `auto_cancel`, `ongoing`, `silent`, `color`, `colorized`, `large_icon`, `only_alert_once`, `show_timestamp`, `timestamp`, `uses_chronometer`, `chronometer_count_down`, `sub_text`, `badge_number`, `visibility`, `timeout_after`, `category`, `full_screen_intent`, `shortcut_id`, `additional_flags`, `ticker`, `tag`, `led_on_duration`, `led_off_duration`.

### 2.6 Android styles — `flet_notifications/android_styles.py`

- `AndroidStyle` (ABC, `android_styles.py:27`): abstract base; sets `_type` discriminator in `__post_init__`.
- `AndroidIcon` (ABC, `android_styles.py:50`): abstract base for image sources accepted by `AndroidPerson.icon`.
- `AndroidBitmap(AndroidIcon, ABC)` (`android_styles.py:70`): base for `large_icon` / `BigPictureStyle.image`.
- `AndroidDrawableBitmap(AndroidBitmap)` (`android_styles.py:86`): `name: str`; `_type="drawable"`.
- `AndroidFileBitmap(AndroidBitmap)` (`android_styles.py:107`): `path: str`; `_type="file"`.
- `AndroidBytesBitmap(AndroidBitmap)` (`android_styles.py:130`): `data: bytes`; `_type="bytes"`.
- `AndroidContentUriIcon(AndroidIcon)` (`android_styles.py:159`): `uri: str`; `_type="content_uri"` (person icon only).
- `AndroidBigTextStyle(AndroidStyle)` (`android_styles.py:176`): `text: str`, `content_title: str\|None`, `summary_text: str\|None`; `_type="big_text"`.
- `AndroidBigPictureStyle(AndroidStyle)` (`android_styles.py:203`): `image: AndroidBitmap`, `large_icon: AndroidBitmap\|None`, `content_title`, `summary_text`; `_type="big_picture"`.
- `AndroidInboxStyle(AndroidStyle)` (`android_styles.py:233`): `lines: list[str]` (non-empty), `content_title`, `summary_text`; `_type="inbox"`.
- `AndroidPerson` (`@ft.value(kw_only=True)`, `android_styles.py:258`): `name: str`, `key`, `bot`, `important`, `uri`, `icon: AndroidIcon\|None`.
- `AndroidMessage` (`@ft.value(kw_only=True)`, `android_styles.py:293`): `text: str`, `timestamp: datetime`, `person: AndroidPerson`.
- `AndroidMessagingStyle(AndroidStyle)` (`android_styles.py:322`): `person: AndroidPerson`, `messages: list[AndroidMessage]`, `conversation_title`, `group_conversation: bool=False`; `_type="messaging"`.

### 2.7 Darwin — `flet_notifications/darwin.py`

- `DarwinInterruptionLevel` (Enum, `darwin.py:13`): `PASSIVE="passive"`, `ACTIVE="active"`, `TIME_SENSITIVE="timeSensitive"`, `CRITICAL="critical"` (critical requires Apple entitlement `com.apple.developer.usernotifications.critical-alerts` + user authorization via `request_permissions(critical=True)`).
- `DarwinOptions` (`@ft.value(kw_only=True)`, `darwin.py:73`): `sound`, `badge_number` (ge 0), `subtitle`, `thread_identifier`, `interruption_level`, `critical_sound_volume` (0.0-1.0), `attachments: list[str]\|None`, `present_alert`, `present_badge`, `present_sound`, `present_banner`, `present_list`.

### 2.8 Linux — `flet_notifications/linux.py`

- `LinuxUrgency` (Enum, `linux.py:14`): `LOW`, `NORMAL`, `CRITICAL`.
- `LinuxCategory` (Enum, `linux.py:37`): ~20 freedesktop categories (`DEVICE`, `EMAIL`, `IM`, `NETWORK`, `PRESENCE`, `TRANSFER`, …).
- `LinuxOptions` (`@ft.value(kw_only=True)`, `linux.py:107`): `icon`, `sound`, `category`, `urgency`, `timeout` (DurationValue, -1 = default), `resident`, `transient`, `silent`, `action_key_as_icon_name`.

### 2.9 Web — `flet_notifications/web.py`

- `WebDirection` (Enum, `web.py:12`): `AUTO="auto"`, `LEFT_TO_RIGHT="leftToRight"`, `RIGHT_TO_LEFT="rightToLeft"`.
- `WebOptions` (`@ft.value(kw_only=True)`, `web.py:32`): `direction`, `badge_url`, `icon_url`, `image_url`, `lang`, `require_interaction`, `silent`, `renotify`, `timestamp`.

### 2.10 Windows — `flet_notifications/windows.py`

- `WindowsScenario` (Enum, `windows.py:17`): `REMINDER`, `ALARM`, `INCOMING_CALL`, `URGENT`.
- `WindowsDuration` (Enum, `windows.py:55`): `SHORT`, `LONG`.
- `WindowsSound` (Enum, `windows.py:70`): `DEFAULT`, `SILENT`, `IM`, `MAIL`, `REMINDER`, `SMS`, `ALARM_1..10`, `CALL_1..10`.
- `WindowsProgress` (`@ft.value(kw_only=True)`, `windows.py:162`): `status: str` (non-empty), `value: int=0`, `max: int=100`, `indeterminate: bool=False`, `title: str\|None`, `label: str\|None`.
- `WindowsOptions` (`@ft.value(kw_only=True)`, `windows.py:197`): `header`, `sound`, `loop_sound`, `duration`, `scenario`, `timestamp`, `subtitle`, `progress: WindowsProgress\|None`, `images: list[str]\|None`, `bindings: dict[str, str]\|None`.

### 2.11 Events — `flet_notifications/events.py`

- `NotificationEvent` (`@dataclass(kw_only=True) class NotificationEvent(ft.Event)`, `events.py:12`): `id: int\|None`, `payload: str\|None`. Delivered to `Notifications.on_tap`.
- `NotificationActionEvent(NotificationEvent)`, `events.py:34`: `action_id: str`, `input: str\|None`. Delivered to `Notifications.on_action`.

### 2.12 Exceptions — `flet_notifications/exceptions.py`

- `NotificationException(ft.FletException)` — base (`exceptions.py:12`).
- `NotificationUnsupportedPlatformException(NotificationException, ft.FletUnsupportedPlatformException)` — `exceptions.py:30`.
- `NotificationInitializationException(NotificationException)` — `exceptions.py:41`.
- `NotificationInvalidArgumentException(NotificationException, ValueError)` — `exceptions.py:50`.
- `NotificationPermissionException(NotificationException)` — `exceptions.py:58`.
- `error_from_bridge(text) -> NotificationException` (`exceptions.py:78`): maps bridge codes `unsupported_platform`/`initialization_failed`/`invalid_argument`/`permission_denied`/`operation_failed` to exception classes.

### 2.13 Scheduling helpers — `flet_notifications/scheduling.py`

- `build_schedule_args(*, when, match_components, schedule_mode) -> dict` (`scheduling.py:12`): builds `when` payload (ISO + utc_offset + timezone for datetimes; delay for timedeltas), `match_components`, `schedule_mode`.
- `build_periodic_args(*, repeat_interval, schedule_mode) -> dict` (`scheduling.py:55`): validates interval ≥ 60000 ms.

### 2.14 Validation — `flet_notifications/validation.py`

- `validate_arguments(*values)` (`validation.py:11`): recursive validation of dataclass fields via `flet.utils.validation.validate`.
- `validate_notification_id(id)` (`validation.py:38`): id must fit 32-bit signed int.
- `validate_non_empty(**values)` (`validation.py:53`).
- `non_negative_duration(*special)` (`validation.py:65`).

---

### 2.15 Dart / Flutter side — method channels & hooks

Flutter plugin source: `/tmp/fn-dev4/extracted/flutter/flet_notifications/`

| file | purpose |
|------|---------|
| `lib/flet_notifications.dart:1-4` | Exports `Extension`. |
| `lib/src/extension.dart:5-15` | `Extension extends FletExtension`; `createService(control)` returns `NotificationsService` when `control.type == "Notifications"`. |
| `lib/src/notifications.dart:34-999` | `NotificationsService extends FletService` — the Dart backend. Holds `_plugin: FlutterLocalNotificationsPlugin`, `_windowsIdentity`, `_initialized`, `_live` static. Handles init, replay of queued/launch responses, and dispatches Python method calls. |
| `lib/src/platforms/android.dart` | Android platform implementation. |
| `lib/src/platforms/darwin.dart` | iOS/macOS implementation. |
| `lib/src/platforms/windows.dart` | Windows implementation. |
| `lib/src/platforms/linux.dart`, `lib/src/platforms/web.dart` | Linux/Web stubs. |
| `lib/src/utils/actions.dart`, `details.dart`, `errors.dart`, `scheduling.dart` | Parsing of actions/notification details/error codes/scheduling. |
| `lib/src/responses/responses.dart`, `response_queue_signal*.dart` | Response queue persistence via `shared_preferences`. |

**Method channel naming / bridge mechanism:** The Python `Notifications` control is registered via `@ft.control("Notifications")` (`notifications.py:67`). On the Dart side `Extension.createService` matches `control.type == "Notifications"` (`extension.dart:9`). Method calls flow: Python `_invoke_method(method_name, arguments)` → `page.session.invoke_method(self._i, method_name, ...)` → Dart `FletService.invokeMethod(name, args)` → `NotificationsService._dispatch(name, args)` (`notifications.dart:428-558`). Events flow back: Dart `control.triggerEvent(name, data)` → Python `on_tap`/`on_action` handlers. The bridge case names handled in `_dispatch`: `show`, `cancel`, `cancel_all`, `schedule`, `periodically_show`, `cancel_all_pending`, `get_pending`, `create_channel`, `delete_channel`, `get_channels`, `start_foreground_service`, `update_windows_progress`, `stop_foreground_service`, `request_permissions`, `can_schedule_exact_alarms`, `request_exact_alarm_permission`, `are_notifications_enabled`, `open_settings`, `get_active`, `request_full_screen_intent`, `has_notification_policy_access`, `request_notification_policy_access`, `create_channel_group`, `delete_channel_group`. Underlying Flutter plugin: `flutter_local_notifications ^22.3.1` (pubspec.yaml:16). No separate raw `MethodChannel` name is exposed — all traffic rides the Flet control bridge keyed by control id `self._i`.

---

## 3. Required pyproject.toml / Android Manifest / Resource Wiring

### 3.1 flet-notifications `pyproject.toml` (from sdist, `/tmp/fn-sdist/flet_notifications-1.1.0.dev4/pyproject.toml`)

```toml
[project]
name = "flet-notifications"
version = "1.1.0.dev4"
requires-python = ">=3.10"
dependencies = [
    "flet==1.1.0.dev4",
    "tzdata",
]
[tool.setuptools.package-data]
"flutter.flet_notifications" = [
    "pubspec.yaml", "lib/**", "android/**", "flet-extension.toml",
]
```

The consumer's `pyproject.toml` must add `flet-notifications==1.1.0.dev4` (and bump flet/flet-ads/flet-cli/flet-desktop to `1.1.0.dev4` to satisfy the strict pin).

### 3.2 Flutter plugin wiring bundled in the wheel

- `flutter/flet_notifications/pubspec.yaml` — plugin name `flet_notifications`, sdk `flutter >=3.38.1`, deps: `flutter_local_notifications ^22.3.1`, `flutter_timezone ^5.1.1`, `package_info_plus ^10.2.2`, `shared_preferences ^2.5.6`, `timezone ^0.11.0`, `crypto ^3.0.6`, `ffi ^2.1.0`.
- `flutter/flet_notifications/flet-extension.toml` — registers `gradle_dependencies = 'coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")'` and `isCoreLibraryDesugaringEnabled = "true"` (required even for apps that never schedule).
- `flutter/flet_notifications/android/build.gradle` — `namespace 'dev.flet.flet_notifications'`, `compileSdk 36`, `minSdkVersion 24`, Java 17.
- `flutter/flet_notifications/android/src/main/AndroidManifest.xml` — merged into every Android build; declares `android.permission.RECEIVE_BOOT_COMPLETED` and three receivers (`ActionBroadcastReceiver`, `ScheduledNotificationReceiver`, `ScheduledNotificationBootReceiver` with `BOOT_COMPLETED`/`MY_PACKAGE_REPLACED`/quickboot intent filters).
- `flutter/flet_notifications/android/src/main/res/drawable/flet_notifications_icon.xml` — default small icon.
- `flutter/flet_notifications/android/src/main/res/raw/flet_notifications_keep.xml` — ProGuard/R8 keep rules.
- `flutter/flet_notifications/android/src/main/java/dev/flet/flet_notifications/FletNotificationsPlugin.java` — no-op plugin class (manifest merger only).

### 3.3 Consumer-side Android entries required for foreground service (per `AndroidForegroundServiceType` docs, `android.py:427-450`)

Shared config (required for any foreground service):
```toml
[tool.flet.android.service."com.dexterous.flutterlocalnotifications.ForegroundService"]
exported = false

[tool.flet.android.permission]
"android.permission.FOREGROUND_SERVICE" = true
```
Then merge per-type entries (e.g. `dataSync`):
```toml
[tool.flet.android.service."com.dexterous.flutterlocalnotifications.ForegroundService"]
foregroundServiceType = "dataSync"

[tool.flet.android.permission]
"android.permission.FOREGROUND_SERVICE_DATA_SYNC" = true
```
Exact-alarm scheduling (if using `schedule_mode=EXACT`/`EXACT_ALLOW_WHILE_IDLE`/`ALARM_CLOCK`):
```toml
[tool.flet.android.permission]
"android.permission.SCHEDULE_EXACT_ALARM" = true
```
Full-screen intent:
```toml
[tool.flet.android.permission]
"android.permission.USE_FULL_SCREEN_INTENT" = true
```
Channel sound files: add via `res_dir` build setting, e.g. `raw/alert.mp3`; icon drawables via `drawable/ic_stat_notify.png`.

---

## 4. Flet Core 1.1.0-dev Deltas + Wakelock

Downloaded `flet-1.1.0.dev4-py3-none-any.whl` (655,641 bytes) → `/tmp/flet-dev4/extracted/flet/`. Downloaded `flet-1.0.5-py3-none-any.whl` → `/tmp/flet-105/extracted/flet/`.

### 4.1 Wakelock (`flet/controls/services/wakelock.py`)

`flet 1.1.0.dev4` (`/tmp/flet-dev4/extracted/flet/controls/services/wakelock.py:1-33`) and `flet 1.0.5` (`/tmp/flet-105/extracted/flet/controls/services/wakelock.py:1-33`) are **byte-identical** (`diff` reports IDENTICAL).

```python
from flet.controls.base_control import control
from flet.controls.services.service import Service

__all__ = ["Wakelock"]

@control("Wakelock")
class Wakelock(Service):
    """Prevents the device from sleeping while enabled."""
    async def enable(self):       await self._invoke_method("enable")
    async def disable(self):      await self._invoke_method("disable")
    async def is_enabled(self) -> bool:  return await self._invoke_method("is_enabled")
```

Exported in `flet/__init__.py:632` (`from flet.controls.services.wakelock import Wakelock`), `__init__.py:1255` (`"Wakelock"`), `__init__.py:1808` (`"Wakelock": "flet.controls.services.wakelock"`).

**Delta vs 1.0.5: none.** `Wakelock.enable()/disable()/is_enabled()` unchanged. `Wakelock` is a `Service` (auto-registers with `page._services`), invokes Dart via `_invoke_method("enable"|"disable"|"is_enabled")`, backed by Flutter `wakelock_plus` (screen-only wake lock, `FLAG_KEEP_SCREEN_ON` on Android — does NOT prevent background kill). No changes in the `Service` base class between 1.0.5 and 1.1.0.dev4 either.

**Implication for ColabShell:** ColabShell already uses `ft.Wakelock` + `android.permission.WAKE_LOCK` (`pyproject.toml:68`). Moving to flet 1.1.0.dev4 requires **no wakelock code changes**.

### 4.2 Other flet core 1.1.0.dev deltas relevant to ColabShell

From the `v1.1.0.dev4` GitHub release body (`/tmp/flet-research/release_dev4.json`):
- `flet build` honors empty platform values; fixed after Flutter version change; Android queries / scheme-only deep links / activity intent filters; macOS/Windows copyright text; Linux desktop client flavor + cache + extension warnings.
- `flet-audio`: `AudioContext` for mobile audio focus and session config.
- `ProgressBar`/`ProgressRing` `semantics_value` as string; `TextField.text_input_action`; `RefreshIndicator` control; gzip-compressed web client files.
- Flutter bumped to 3.47.8 (dev3).

No breaking change to `page.update()` rules or the `Service`/`Wakelock` API surface was found in the release bodies; ColabShell's existing `page.update()`-inside-`use_effect` critical findings (`dep-01-flet-core.md` #1-#3) remain applicable to 1.1.0.dev4.

---

## 5. Breaking Changes & Migration Notes for ColabShell

### 5.1 Strict version pin — the key breaking constraint

`flet-notifications 1.1.0.dev4` declares `Requires-Dist: flet==1.1.0.dev4` (METADATA:14), a **strict equality pin**. ColabShell currently pins `flet==1.0.5` (`pyproject.toml:8`).

**Mixing flet 1.0.5 with flet-notifications 1.1.0-dev.4 will NOT work:**
- Dependency resolution: `flet-notifications==1.1.0.dev4` requires `flet==1.1.0.dev4` exactly. `uv`/`pip` will conflict with ColabShell's `flet==1.0.5` and refuse to install both (or will downgrade/upgrade flet, breaking the pinned `flet-ads==1.0.5`, `flet-cli==1.0.5`, `flet-desktop==1.0.5`).
- At runtime: `flet_notifications/__init__.py` imports `import flet as ft` and uses `@ft.control`, `@ft.value`, `ft.Service`, `ft.EventHandler`, `ft.PagePlatform`, `ft.Duration`, `ft.ColorValue`, `ft.DurationValue`. If flet 1.0.5 lacks any symbol/behavior added in 1.1.0.dev4, imports or method calls will fail.
- `flet-ads`, `flet-cli`, `flet-desktop` are co-released at `1.1.0.dev4` and also require matching flet core — they must be bumped together.

**Required bump (all together):**
```
flet==1.1.0.dev4
flet-ads==1.1.0.dev4
flet-cli==1.1.0.dev4   (win32 marker)
flet-desktop==1.1.0.dev4 (win32 marker)
flet-platform-assets==1.1.0.dev4
flet-notifications==1.1.0.dev4
```
`flet-terminal` stays `==0.4.2` (no 1.1.0-dev line).

### 5.2 Wakelock — no migration needed

`Wakelock` is identical between 1.0.5 and 1.1.0.dev4. ColabShell's existing usage (`ft.Wakelock`, `page.services.append`, `enable()/disable()/is_enabled()`, `android.permission.WAKE_LOCK`) carries over unchanged.

### 5.3 Notifications is additive — no existing code breaks, but new wiring is required

Adding `flet-notifications` is purely additive to ColabShell's current code (no existing API removed). However it requires new consumer-side configuration:
- Add `flet-notifications==1.1.0.dev4` to `pyproject.toml` dependencies.
- Bump flet core + ecosystem to `1.1.0.dev4` (see 5.1).
- For Android foreground service (`start_foreground_service`): add `[tool.flet.android.service."com.dexterous.flutterlocalnotifications.ForegroundService"]` + `FOREGROUND_SERVICE` + per-type permission entries in `pyproject.toml` (section 3.3).
- For scheduled notifications: the plugin manifest already adds `RECEIVE_BOOT_COMPLETED` + boot receivers (bundled in the wheel's AndroidManifest.xml); no consumer manifest edit needed for basic scheduling.
- For channel sounds/icons: bundle via `res_dir` build setting (`drawable/`, `raw/`).
- `Notifications` is an `ft.Service` — instantiate once per page (`notifications = ftn.Notifications(on_tap=…)`) and keep the reference; it auto-registers with the page.

### 5.4 Platform-support caveats (from the docstrings)

- `schedule`/`periodically_show`/`cancel_all_pending`/`get_pending`: Android/iOS/macOS/Windows only; raises `NotificationUnsupportedPlatformException` on Linux/Web.
- `start_foreground_service`/`stop_foreground_service`: Android only.
- `update_windows_progress`: Windows only (requires MSIX package identity for some removal operations).
- `open_settings`: Android/iOS/macOS only.
- Windows notification identity (`windows_app_user_model_id`, `windows_guid`) is fixed at first launch; changes apply from next app launch.
- iOS keeps at most 64 pending notifications per app.
- Web requires HTTPS/trusted localhost and user-interaction-gated permission.

---

## 6. Recommended `uv add` commands

Run in `/home/maikel/Desktop/kiri-apps/ColabShell`:

```bash
# Bump flet core + ecosystem to the matching 1.1.0.dev4 line (must be together)
uv add "flet==1.1.0.dev4" "flet-ads==1.1.0.dev4" "flet-platform-assets==1.1.0.dev4"
uv add "flet-cli==1.1.0.dev4; sys_platform == 'win32'"
uv add "flet-desktop==1.1.0.dev4; sys_platform == 'win32'"

# Add the notifications service (strictly requires flet==1.1.0.dev4)
uv add "flet-notifications==1.1.0.dev4"

# flet-terminal stays on 0.4.2 (no 1.1.0-dev line) — already pinned, no change
```

Then verify:
```bash
uv pip freeze | grep -E "flet|notifications"
# Expected:
# flet==1.1.0.dev4
# flet-ads==1.1.0.dev4
# flet-cli==1.1.0.dev4
# flet-desktop==1.1.0.dev4
# flet-notifications==1.1.0.dev4
# flet-platform-assets==1.1.0.dev4
# flet-terminal==0.4.2
```

Then add Android foreground-service + notification wiring to `pyproject.toml` `[tool.flet.android.*]` tables (section 3.3) if ColabShell will use `start_foreground_service` or exact-alarm scheduling.

---

## Verification

- Downloaded & extracted: `/tmp/fn-dev4/extracted/flet_notifications/` (14 `.py` files + Flutter plugin + Android manifest/resources) — all read.
- Downloaded & extracted: `/tmp/flet-dev4/extracted/flet/` (flet 1.1.0.dev4 core) and `/tmp/flet-105/extracted/flet/` (flet 1.0.5 core).
- `diff` of `wakelock.py` between 1.0.5 and 1.1.0.dev4: **IDENTICAL**.
- `flet-notifications 1.1.0.dev4` METADATA: `Requires-Dist: flet==1.1.0.dev4`, `Requires-Dist: tzdata`, `Requires-Python: >=3.10`.
- Output file: `/home/maikel/Desktop/kiri-apps/ColabShell/docs/research-05-flet-1.1.0-line.md`

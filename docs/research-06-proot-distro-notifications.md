# Research: proot-distro-flet notification / wakelock / foreground-service pattern (committed tree)

Source: /home/maikel/Desktop/kiri-apps/proot-distro-flet (read-only study, 2026-11-03). This is the
proven pattern to port into ColabShell (session instead of container).

## 1. pyproject.toml snippets to copy

```toml
dependencies = [
    "flet>=1.1.0.dev3",
    "flet-ads>=1.1.0.dev3",
    "flet-notifications>=1.1.0.dev3",
    "httpx>=0.28.1",
    "flet-terminal==0.4.2",
]

[tool.flet.android]
legacy_packaging = true            # ColabShell already has this (9fc237b)
split_per_abi = true
res_dir = "android_res"            # notification small-icon drawables

[tool.flet.android.permission]
"android.permission.INTERNET" = true
"android.permission.ACCESS_NETWORK_STATE" = true
"android.permission.FOREGROUND_SERVICE" = true
"android.permission.FOREGROUND_SERVICE_SPECIAL_USE" = true
"android.permission.POST_NOTIFICATIONS" = true
"android.permission.WAKE_LOCK" = true   # ColabShell already added

[tool.flet.android.service."com.dexterous.flutterlocalnotifications.ForegroundService"]
exported = false
foregroundServiceType = "specialUse"    # camelCase (commit 300253f)

[tool.flet.android.meta_data]
"android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE" = "Linux container sessions stay alive in the background"
```
`android_res/drawable-{hdpi,mdpi,xhdpi,xxhdpi,xxxhdpi}/ic_stat_<app>.png` — white-silhouette small icon.

## 2. Service registration & lifecycle (proot-distro file:line)
- `src/core/shared_services.py:22-52` — `mount_shared_services(page)` mounts `ft.Wakelock` → `page.wakelock`.
- `src/app_controller.py:12,35-47` — `import flet_notifications as ft_notifications`;
  `self.notifications = ft_notifications.Notifications(android_default_icon="ic_stat_prootdistro")`;
  `self.notifications.on_action = self._on_notification_action`; appended to `page.services` at `:156`.
- `app_controller.py:49-52` — `on_action`: `if e.action_id == "exit": page.run_task(self.exit_app)`.
- `app_controller.py:133-139` — request notification permission at startup (`request_permissions()`).
- `src/main.py:25-74` — `page.on_close`/`page.on_disconnect` are NO-OPs (sticky FGS keeps the process
  alive; teardown happens in atexit / exit action); `page.on_view_pop` back-button handler.

## 3. Running-session notification with Exit action (session_actions.py)
```python
await notifications.start_foreground_service(
    id=1,                                  # nonzero
    title="Proot Distro",
    body=f"Linux session running: {container}",
    start_type=AndroidServiceStartType.STICKY,
    service_types=[AndroidForegroundServiceType.SPECIAL_USE],
    actions=[NotificationAction(id="exit", title="Exit")],
)
await notifications.stop_foreground_service()          # on session close / exit
await notifications.request_permissions()             # before FGS start
```
- Posted on session open (`session_actions.py:159-182` `_start_fgs`), cancelled on session close
  (`:188-193`) and on exit (`:195-207` `exit_app`: close all sessions → `_stop_fgs()` →
  `jnius android.os.Process.killProcess(myPid())` with `os._exit(0)` fallback).
- Tap on notification opens/brings-forward the app (default `on_tap`); `on_action` handles Exit.
- flet_notifications API: `Notifications(ft.Service)` (`notifications.py:68`), `show()` :265-322,
  `cancel()` :324-345, `request_permissions()` :362-430, `start_foreground_service()` :805-881,
  `stop_foreground_service()` :883-896; `NotificationAction` in `types.py:133-220`.

## 4. Wakelock
- `src/screens/terminal/__init__.py:56-75` — `ft.on_mounted` effect: `page.run_task(wl.enable)`,
  cleanup `page.run_task(wl.disable)` guarded vs RuntimeError (destroyed session). WAKE_LOCK permission.

## 5. Recent bugfix commits
`ae9b6e6` (flet 1.1.0.dev3 + flet-notifications migration, FGS), `26fb82b` (POST_NOTIFICATIONS + request
permission at startup/before FGS), `300253f` (camelCase foregroundServiceType), `9217361` (allow
FOREGROUND_SERVICE_SPECIAL_USE in AAB manifest audit), `112d094` (WAKE_LOCK, wakelock cleanup guard,
on_close no-op, icon).

## 6. Port-to-ColabShell checklist (session, not terminal)
- deps: `uv add flet==1.1.0.dev4 flet-ads==1.1.0.dev4 flet-notifications==1.1.0.dev4` (+ flet-cli/
  flet-desktop/flet-platform-assets 1.1.0.dev4; flet-terminal stays 0.4.2) — see research-05.
- pyproject android block per §1 (permissions, service, meta_data subtype, res_dir + icon).
- Controller: Notifications service w/ `android_default_icon`, `on_action` → exit; request permission at boot.
- On Colab session open: start FGS `body=f"Colab session running: {name}"` + Exit action;
  on session stop/close: stop FGS. Exit action: stop sessions → stop FGS → kill process.
- Wakelock: keep ft.Wakelock mounted; enable while session view mounted (proot pattern), disable on cleanup.
- main.py: on_close/on_disconnect no-ops (process kept alive by FGS).

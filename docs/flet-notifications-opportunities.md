# Where flet-notifications improves CollabShell

Study of `flet-notifications` (the owner's package: a 1:1 wrap of
`flutter_local_notifications`, same architecture as `flet-ads`). All API claims
below verified against the package source at `../flet-notifications/src/`
with file:line; nothing here is invented.

## The core insight

CollabShell is an app about **waiting**. Every meaningful operation is slow:
a Colab VM takes ~30s to assign, a training cell runs for twenty minutes,
downloading a dataset can take an hour, package installs are slow. The user is
on a **phone**. Today the only way to learn any of it finished is to come back
and look — which means keeping the app foregrounded, which defeats the point
of a phone.

That is precisely the gap `flet-notifications` closes.

## Shipped now (commit 6eb3f74)

| Trigger | What the notification says | Actions |
|---|---|---|
| Cell finishes | "Cell finished" + a short output digest | **Open** |
| Cell fails | "Cell failed" + the first traceback line | **Open**, **Ask AI to fix** |
| Runtime ready | "Runtime ready — CPU and GPU are live" | Open |
| Runtime reaped | "Runtime stopped — idle VMs do not keep running" | — |
| Assistant turn done | "Assistant replied" + preview | Open |
| Credits low | "N left today, resets at 00:00 UTC" | Open |

The action buttons are the part that matters most. A failed cell's **"Ask AI
to fix"** deep-links onto the exact tab and cell
(`collabshell://session?name=s1&tab=nb1&cell=c9`), which is the same
step→cell infrastructure the in-cell actions already built. You are looking at
a traceback on your lock screen and one tap puts you in the cell with the AI
fix queued.

Three channels exist so the phone knows what to make noise about: `runs` is
LOW importance with sound and badge **off** — a finished cell must not buzz.
`session` and `billing` are default.

## High-value, not yet built

### 1. Live progress for a running cell (biggest remaining win)
`show()` documents that re-showing the same id **updates in place** — "this is
how live progress bars are advanced" (`local_notifications.py:169-171`). For a
training loop the kernel already streams output; a cell that reports
`tqdm` progress or an epoch counter could drive a determinate bar on the
lock screen. The phone shows *how far along* you are, not just *that it
finished*.

Shaping: `show(id=ID_CELL_PROGRESS, show_progress=True, max_progress=N,
progress=k, indeterminate=False)` — the kernel stream already arrives via
`on_output`, so the shape of the plumbing exists in `_run_cell`.

### 2. Scheduled warnings for the idle reaper
`schedule()` + `periodically_show()` (`local_notifications.py:244,318`). Colab
reaps idle VMs. A scheduled "your runtime goes idle in 20 minutes" warning,
fired locally with no network, would prevent the single most annoying loss in
the app (a session you forgot about). Needs the Gradle receivers injected via
`flet-notifications-patch` and `RECEIVE_BOOT_COMPLETED` /
`SCHEDULE_EXACT_ALARM` permissions in pyproject.

### 3. Foreground service for long runs
`start_foreground_service()` (`local_notifications.py:461`) keeps the process
alive and visible for a genuinely long operation — the difference between a
download that survives the OS and one that gets killed mid-transfer.

### 4. File transfer completion
`session`-channel notifications for large upload/download, with the byte total
and the output path. Today a 2GB dataset download gives no signal at all.

### 5. Rich styles for real content
`BigTextStyle` for a full traceback (the notification is *readable* rather than
truncated at 180 chars), `BigPictureStyle` for a plot the cell produced, and
`InboxStyle` to group several finished cells into one expandable
notification instead of stacking.

### 6. Inline reply
`NotificationActionInput` (`actions.py:8`) lets a notification carry a text
field. The natural use: an assistant question answered from the lock screen
("rename this to…") with the typed text arriving as `NotificationEvent.input`.

### 7. Channels the user can tune
`open_app_notification_settings()` (`local_notifications.py:524`) — one tap to
the OS settings so a user who finds `runs` chatty can silence it without
losing `session` warnings.

## Gotchas the README flags, all confirmed in source

- **Typed handlers need `ft.EventHandler[NotificationEvent]`**, NOT
  `ft.ControlEventHandler` — the latter double-wraps the type and
  `e.payload` stops existing (`base.py:20`).
- **`flet run` does not work** — notifications need the Dart half, so a built
  app (or artifact) is required. This is why `NotifyService` degrades to a
  no-op rather than erroring.
- **Android scheduling needs permissions** declared in `pyproject.toml`
  (`[tool.flet.android.permission]`) plus the receiver injection script.
- **Cold-start taps are lost** unless `get_notification_app_launch_details()`
  is consulted at boot — `replay_launch()` in `notify.py` does this.
- `NotificationError` carries a stable `code`; the service logs rather than
  surfaces it.
- Linux and Web have no OS scheduler; Windows schedules one-shot only.

## Recommendation

Build (1) live progress next — it is the highest user value per unit of work
and needs no new permissions or Gradle changes, because the kernel stream
already exists. Then (2) the idle-reaper warning, which prevents actual data
loss and justifies the Gradle patch on its own.

---

## Update: items 1–3 built, plus the four dead entry points

`flet-notifications>=0.1.4` is now a dependency. The service
(`services/notify.py`) already had the channels, deep links, action buttons and
`replay_launch()`, but four of its entry points were dead — the design was
right, the wiring was not:

1. **The router was never passed.** `NotifyService(state=state)` was built
   without one, so `on_tap` parsed every payload and then dropped it. Deep
   links were decorative. `main._route_notification_payload` now maps
   `collabshell://session|assistant|home` onto real navigation.
2. **`replay_launch()` was never called** — cold-start taps were lost. It runs
   at boot now.
3. **No on/off switch existed.** `state.notify_enabled` +
   `STORAGE_NOTIFY_ENABLED` are new, with a Settings row under Session
   Behavior. It is a channel switch, not a permission request: the OS grant
   survives, so going quiet costs no dialog.
4. **`cell_done` had no duration threshold**, so every cell would have
   notified. It now takes `duration_sec`, measured in `_run_cell`. A channel
   that pings on a two-second cell gets muted within a day.

Two bugs the new tests caught, both introduced by this change:

- `disable()` set a flag `_wanted()` never read, so the switch did nothing at
  all. `_wanted()` now ANDs the persisted preference with the in-session flag.
- A service was written from scratch before checking for an existing one,
  duplicating a more complete `services/notify.py`. Same mistake as the header
  work; deleted. **Check for the implementation before writing it.**

The two tests asserting "no plugin" now force absence with a fixture rather
than relying on the package not being installed — installing it as a real
dependency silently invalidated them, which is the ambient-assumption trap.

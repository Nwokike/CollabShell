"""OS notifications — the app working while it is in your pocket.

Every long operation in this app has the same failure: you start a cell that
trains for twenty minutes, the phone locks, and the only way to learn it
finished is to come back and look. `flet_notifications` ends that — the OS
tells you, with action buttons that deep-link straight back into the cell.

Three channels, so the phone can be told what to make noise about:

    runs       quiet — cell and file completions (no sound, no badge)
    session    default — a runtime is ready, or one died
    billing    default — credits are low or gone

The service degrades silently: notifications need the Dart half of a built
app, so under `flet run` (or on a platform without support) every call is a
no-op rather than an error. That is deliberate — the caller never has to
branch on "can this even notify".

Action taps arrive as a payload string the router resolves, so "Open" lands on
the exact tab and cell rather than the app's front door. Taps that happen
while the app is dead are replayed on the next start by `replay_launch()`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("notify")

# Notification ids are stable per subject: re-showing the same id updates the
# notification in place instead of stacking a new one, which is also how a
# live progress bar is advanced.
_ID_CELL_DONE = 1001
_ID_SESSION_READY = 1002
_ID_SESSION_LOST = 1003
_ID_TURN_DONE = 1004
_ID_CREDITS = 1005

CHANNEL_RUNS = "collabshell_runs"
CHANNEL_SESSION = "collabshell_session"
CHANNEL_BILLING = "collabshell_billing"

# A payload prefix the app's own router understands. Kept here so the deep
# link is one string the UI can act on without knowing about notifications.
PAYLOAD_PREFIX = "collabshell://"


def _deep_link(path: str, **query) -> str:
    """A payload the app's own router resolves: ``collabshell://<path>?k=v&k=v``.

    Only one ``?`` — everything after it is a ``&``-joined query, matching
    what `urllib.parse` hands back, so the tap handler can split it the same
    way it splits a real route.
    """
    pairs = [f"{key}={value}" for key, value in query.items() if value]
    tail = "&".join(pairs)
    return f"{PAYLOAD_PREFIX}{path.lstrip('/')}" + (f"?{tail}" if tail else "")


@dataclass(kw_only=True)
class _Action:
    """A notification action button.

    Mirrors ``flet_notifications.NotificationAction`` (actions.py:29) so the
    service has an object with ``to_dict()`` even when the plugin is absent.
    The real type is preferred when installed; this keeps the call path free of
    a hard dependency on a package that only matters in a built app.
    """

    id: str
    title: str
    destructive: bool = False
    foreground: bool = True
    cancel_notification: bool = True
    input: dict | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "destructive": self.destructive,
            "foreground": self.foreground,
            "cancel_notification": self.cancel_notification,
            "input": self.input,
        }


def _action(action_id: str, title: str) -> object:
    """The plugin's real action type when present, else the mirror above."""
    try:
        from flet_notifications import NotificationAction

        return NotificationAction(id=action_id, title=title)
    except Exception:
        return _Action(id=action_id, title=title)


def _channel_types():
    """(NotificationChannel, Importance) from the plugin, or (None, None).

    Same rule as ``_action``: the real types when installed, so the service
    works without the package being present at all.
    """
    try:
        from flet_notifications import Importance, NotificationChannel

        return NotificationChannel, Importance
    except Exception:
        return None, None


class NotifyService:
    """Lazy wrapper over flet_notifications.

    Construct once (usually on the Services bundle). Nothing touches the plugin
    until the first real notification, and any failure is logged and swallowed
    — a phone that refuses to notify must never break a cell run.
    """

    def __init__(self, state=None, router=None):
        self.state = state
        self.router = router
        self._service = None
        self._initialised = False
        self._unsupported = False

    # ── lifecycle ──────────────────────────────────────────────────────────

    def _build(self):
        """The plugin service, or None when notifications cannot work here."""
        if self._unsupported:
            return None
        if self._service is not None:
            return self._service
        try:
            from flet_notifications import LocalNotifications

            service = LocalNotifications()
        except Exception as ex:
            # No Dart half (running under `flet run`), or an unsupported
            # platform. Not an error the user needs to know about.
            logger.debug("OS notifications unavailable: %s", ex)
            self._unsupported = True
            return None
        self._service = service
        return service

    async def initialise(self) -> bool:
        """Ask permission and create the channels. Safe to call repeatedly."""
        if self._initialised:
            return True
        service = self._build()
        if service is None:
            return False
        try:
            granted = await service.request_permissions()
            if not granted:
                logger.debug("notification permission not granted")
            await self._ensure_channels(service)
            self._initialised = True
            return True
        except Exception as ex:
            logger.debug("notification init failed: %s", ex)
            return False

    def _wanted_channels(self) -> list:
        """The three channels this app posts on, or [] without the plugin.

        Separated from creation so the channel *policy* (which channel, how
        loud) is testable without the plugin installed.
        """
        channel_type, importance = _channel_types()
        if channel_type is None:
            return []
        wanted = [
            channel_type(
                id=CHANNEL_RUNS,
                name="Runs",
                description="When a cell, a download or an install finishes",
                importance=importance.LOW,
                play_sound=False,
                show_badge=False,
            ),
            channel_type(
                id=CHANNEL_SESSION,
                name="Sessions",
                description="When a runtime is ready, or has been reaped",
                importance=importance.DEFAULT,
            ),
            channel_type(
                id=CHANNEL_BILLING,
                name="Assistant credits",
                description="When assistant credits run low",
                importance=importance.DEFAULT,
            ),
        ]
        return wanted

    async def _ensure_channels(self, service) -> None:
        for channel in self._wanted_channels():
            try:
                await service.create_notification_channel(channel)
            except Exception as ex:
                # Channel creation is idempotent-per-id on Android and can
                # legitimately fail if the OS already has it.
                logger.debug("channel %s: %s", channel.id, ex)

    # ── the calls the app makes ────────────────────────────────────────────

    async def cell_done(
        self,
        *,
        session_name: str,
        tab_id: str,
        cell_id: str,
        ok: bool,
        detail: str = "",
    ) -> None:
        """A finished cell, with an action that opens it.

        `ok` decides the wording; `detail` is the first line of the error for a
        failure, or a short output digest for a success.
        """
        service = self._build()
        if service is None:
            return
        if not await initialise_guard(self):
            return
        title = "Cell finished" if ok else "Cell failed"
        body = detail.strip()[:180] if detail else (
            "Tap to open the notebook." if ok else "Tap to see the traceback."
        )
        actions = (
            [_action("open", "Open")]
            if ok
            else [_action("open", "Open"), _action("fix", "Ask AI to fix")]
        )
        try:
            await service.show(
                id=_ID_CELL_DONE,
                title=title,
                body=body,
                payload=_deep_link(
                    "session", name=session_name, tab=tab_id, cell=cell_id
                ),
                actions=actions,
                channel_id=CHANNEL_RUNS,
            )
        except Exception as ex:
            logger.debug("cell_done notify failed: %s", ex)

    async def session_ready(self, name: str) -> None:
        await self._simple(
            _ID_SESSION_READY,
            CHANNEL_SESSION,
            "Runtime ready",
            f"{name} is connected — CPU and GPU are live.",
            _deep_link("session", name=name),
        )

    async def session_lost(self, name: str) -> None:
        await self._simple(
            _ID_SESSION_LOST,
            CHANNEL_SESSION,
            "Runtime stopped",
            f"{name} was reaped. Idle VMs do not keep running.",
            _deep_link("home"),
        )

    async def turn_done(self, *, preview: str = "", ok: bool = True) -> None:
        """The assistant finished a turn you were not watching."""
        body = preview.strip()[:180] or (
            "Tap to read the answer." if ok else "The assistant could not answer."
        )
        await self._simple(
            _ID_TURN_DONE,
            CHANNEL_RUNS,
            "Assistant replied" if ok else "Assistant failed",
            body,
            _deep_link("assistant"),
        )

    async def credits_low(self, remaining: int) -> None:
        await self._simple(
            _ID_CREDITS,
            CHANNEL_BILLING,
            "Assistant credits low",
            f"{remaining} left today. They reset at 00:00 UTC.",
            _deep_link("assistant"),
        )

    async def _simple(
        self, note_id: int, channel: str, title: str, body: str, payload: str
    ) -> None:
        service = self._build()
        if service is None or not await initialise_guard(self):
            return
        try:
            await service.show(
                id=note_id,
                title=title,
                body=body,
                payload=payload,
                channel_id=channel,
            )
        except Exception as ex:
            logger.debug("notify %s failed: %s", title, ex)

    # ── taps ─────────────────��─────────────────────────────────────────────

    def on_tap(self, event) -> None:
        """A tap or action button. Resolves the payload through the router.

        Registered by the app shell; the handler is an ``ft.EventHandler``, NOT
        ``ft.ControlEventHandler`` — the latter double-wraps the payload type
        and ``e.payload`` stops existing.
        """
        payload = str(getattr(event, "payload", "") or "")
        action = str(getattr(event, "action_id", "") or "")
        if not payload.startswith(PAYLOAD_PREFIX):
            return
        target = payload[len(PAYLOAD_PREFIX):]
        path, _, query = target.partition("?")
        params = dict(
            pair.split("=", 1) for pair in query.split("&") if "=" in pair
        )
        if self.router is not None:
            try:
                self.router(path, params, action)
            except Exception:
                logger.debug("notification route failed", exc_info=True)

    async def replay_launch(self) -> None:
        """Deliver a tap that happened while the app was not running.

        Android replays background taps and iOS/macOS cold-start launches; without
        this they are lost and the notification looks inert.
        """
        service = self._build()
        if service is None:
            return
        try:
            details = await service.get_notification_app_launch_details()
            if details.did_notification_launch_app and details.notification:
                self.on_tap(details.notification)
        except Exception as ex:
            logger.debug("launch replay failed: %s", ex)


async def initialise_guard(service: NotifyService) -> bool:
    """Init on first use, so no caller has to sequence it."""
    if service._initialised:
        return True
    return await service.initialise()

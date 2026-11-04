"""Persistent "session running" notification + Android foreground service.

Ported from proot-distro-flet's committed pattern (flet-notifications
1.1.0-dev): while a Colab session is active, a sticky foreground service
keeps the Android process alive when the app is minimized, showing an
ongoing notification with an Exit action. Tapping the notification restores
the session view; Exit stops the service and kills the process (the only
true "close the app" — minimizing never kills it).
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("session_notify")

FGS_ID = 1  # nonzero: the plugin rejects id=0
ICON = "ic_stat_collabshell"


class SessionNotificationService:
    """Owns the flet_notifications service and the session-running FGS."""

    def __init__(self, page, state, *, on_exit=None, on_tap=None):
        self.page = page
        self.state = state
        self._on_exit = on_exit
        self._on_tap = on_tap
        self.notifications = None
        self._ftn = None
        self._fgs_running = False
        self._fgs_session = ""

    def mount(self) -> None:
        """Create + register the Notifications service (once per page)."""
        try:
            import flet_notifications as ftn
        except ImportError:
            logger.info("flet_notifications not installed; notifications off")
            return
        self._ftn = ftn
        self.notifications = ftn.Notifications(android_default_icon=ICON)
        self.notifications.on_action = self._handle_action
        self.notifications.on_tap = self._handle_tap
        if self.notifications not in self.page.services:
            self.page.services.append(self.notifications)
        logger.info("Notifications service mounted (icon=%s)", ICON)

    async def request_permission(self) -> None:
        """Ask POST_NOTIFICATIONS at boot; never fatal."""
        if self.notifications is None:
            return
        try:
            await self.notifications.request_permissions()
        except Exception as exc:
            logger.debug("notification permission request failed: %s", exc)

    def _is_android(self) -> bool:
        try:
            import flet as ft

            return (
                not getattr(self.page, "web", False)
                and self.page.platform == ft.PagePlatform.ANDROID
            )
        except Exception:
            return False

    async def start_for_session(self, session_name: str) -> None:
        """Show the ongoing FGS notification for a running session."""
        if self.notifications is None or not self._is_android():
            return
        if self._fgs_running and self._fgs_session == session_name:
            return
        ftn = self._ftn
        try:
            await self.request_permission()
            await self.notifications.start_foreground_service(
                id=FGS_ID,
                title="Collab Shell",
                body=f"Colab session running: {session_name}",
                payload=f"session:{session_name}",
                start_type=ftn.AndroidServiceStartType.STICKY,
                service_types=[ftn.AndroidForegroundServiceType.SPECIAL_USE],
                actions=[ftn.NotificationAction(id="exit", title="Exit")],
            )
            self._fgs_running = True
            self._fgs_session = session_name
            logger.info("FGS started for session %s", session_name)
        except Exception as exc:
            logger.warning("FGS start failed: %s", exc)

    async def stop(self) -> None:
        """Remove the FGS notification (session closed / app exiting)."""
        if self.notifications is None or not self._fgs_running:
            return
        try:
            await self.notifications.stop_foreground_service()
            logger.info("FGS stopped")
        except Exception as exc:
            logger.debug("FGS stop failed: %s", exc)
        finally:
            self._fgs_running = False
            self._fgs_session = ""

    def _handle_tap(self, e) -> None:
        """Tap the notification -> bring the app forward on the session."""
        payload = str(getattr(e, "payload", "") or "")
        name = payload.removeprefix("session:") if payload else ""
        if self._on_tap is not None:
            try:
                self._on_tap(name or None)
            except Exception:
                logger.debug("notification tap handler failed", exc_info=True)

    def _handle_action(self, e) -> None:
        if getattr(e, "action_id", "") != "exit":
            return
        if self._on_exit is not None:
            self.page.run_task(self._on_exit)

    async def exit_app(self) -> None:
        """The notification's Exit button: stop work, stop FGS, kill process."""
        await self.stop()
        try:
            from jnius import autoclass  # type: ignore

            proc = autoclass("android.os.Process")
            proc.killProcess(proc.myPid())
            return
        except Exception:
            pass
        os._exit(0)

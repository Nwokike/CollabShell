import asyncio

import flet as ft

from core import constants, tokens


async def check_session(ctrl):
    session = next(
        (s for s in ctrl.state.active_sessions if s.get("name") == ctrl.session_name),
        None,
    )
    if not session:
        if ctrl.snack:
            ctrl.snack("Session is no longer available.")
        return False
    return True


async def on_restart(ctrl, e=None):
    if not await check_session(ctrl):
        return

    def _close_dialog(e=None):
        dialog.open = False
        ctrl.page.update()

    def _close_and_restart(ev):
        _close_dialog()
        ctrl.page.run_task(do_restart, ctrl)

    dialog = ft.AlertDialog(
        title=ft.Text("Restart Kernel?"),
        content=ft.Text(
            "This will restart the Python kernel. All variables will be lost."
        ),
        actions=[
            ft.TextButton("Cancel", on_click=_close_dialog),
            ft.FilledButton("Restart", on_click=_close_and_restart),
        ],
    )
    ctrl.page.show_dialog(dialog)


async def do_restart(ctrl):
    if ctrl.snack:
        ctrl.snack("Restarting kernel...")
    try:
        await ctrl.colab_service.restart_kernel(
            ctrl.session_name, auth_method=ctrl.state.auth_method
        )
        if ctrl.snack:
            ctrl.snack("✅ Kernel restarted")
    except Exception as ex:
        if ctrl.snack:
            ctrl.snack(f"❌ {ex}")


async def on_stop(ctrl, e=None):
    if not await check_session(ctrl):
        return

    def _close_dialog(e=None):
        dialog.open = False
        ctrl.page.update()

    def _close_and_stop(ev):
        _close_dialog()
        ctrl.page.run_task(do_stop, ctrl)

    dialog = ft.AlertDialog(
        title=ft.Text("Stop Session?"),
        content=ft.Text("This will terminate the session and release all resources."),
        actions=[
            ft.TextButton("Cancel", on_click=_close_dialog),
            ft.FilledButton("Stop", on_click=_close_and_stop),
        ],
    )
    ctrl.page.show_dialog(dialog)


async def do_stop(ctrl):
    if ctrl.snack:
        ctrl.snack("Stopping session...")
    try:
        await ctrl.colab_service.stop_session(
            ctrl.session_name, auth_method=ctrl.state.auth_method
        )
        if ctrl.snack:
            ctrl.snack("✅ Session terminated")
        ctrl.state.active_sessions = await ctrl.colab_service.list_sessions(
            auth_method=ctrl.state.auth_method
        )
        if ctrl.on_back:
            ctrl.on_back(None)
    except Exception as ex:
        if ctrl.snack:
            ctrl.snack(f"❌ {ex}")


def action_output(ctrl, prefix: str):
    def _handler(out):
        if not ctrl.snack:
            return
        msg = out if isinstance(out, str) else out.get("text", "")
        msg = msg.strip()
        if msg:
            line = msg.split("\n")[-1] if "\n" in msg else msg
            ctrl.page.loop.call_soon_threadsafe(ctrl.snack, f"{prefix}: {line[:120]}")

    return _handler


_active_auth_dialog = {"current": None}


def _close_active_auth(ctrl):
    if _active_auth_dialog["current"] and _active_auth_dialog["current"].open:
        _active_auth_dialog["current"].open = False
        ctrl.page.update()


async def on_mount_drive(ctrl, e=None):
    dialog = ft.AlertDialog(
        title=ft.Text("Mounting Google Drive..."),
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.ProgressRing(width=24, height=24, stroke_width=3),
                        ft.Text(
                            "Initiating mount on virtual machine...",
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.W_500,
                        ),
                    ],
                    spacing=tokens.SPACE_MD,
                ),
                ft.Text(
                    "Please wait while Colab checks or mounts your Google Drive...",
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            tight=True,
            spacing=tokens.SPACE_SM,
        ),
        actions=[ft.TextButton("Cancel", on_click=lambda e: _close_active_auth(ctrl))],
        modal=True,
    )
    _active_auth_dialog["current"] = dialog
    ctrl.page.show_dialog(dialog)
    ctrl.page.update()

    try:
        await ctrl.colab_service.mount_drive(
            ctrl.session_name,
            path=ctrl.state.drive_mount_path,
            auth_method=ctrl.state.auth_method,
            on_output=action_output(ctrl, "Drive"),
            stdin_hook=ctrl.interactive_stdin_hook,
        )
        if dialog.open:
            dialog.title = ft.Text("Success")
            dialog.content = ft.Row(
                [
                    ft.Icon(ft.Icons.CHECK_CIRCLE_ROUNDED, color="green", size=24),
                    ft.Text(
                        f"Drive mounted at {ctrl.state.drive_mount_path}",
                        size=tokens.FONT_SM,
                        weight=ft.FontWeight.BOLD,
                    ),
                ],
                spacing=tokens.SPACE_SM,
            )
            dialog.actions = [
                ft.FilledButton("Done", on_click=lambda e: _close_active_auth(ctrl))
            ]
            dialog.update()

            async def _auto_close():
                await asyncio.sleep(1.5)
                _close_active_auth(ctrl)

            ctrl.page.run_task(_auto_close)
    except Exception as ex:
        if dialog.open:
            dialog.title = ft.Text("Failed")
            dialog.content = ft.Row(
                [
                    ft.Icon(ft.Icons.ERROR_ROUNDED, color="red", size=24),
                    ft.Text(f"Error: {ex}", size=tokens.FONT_SM),
                ],
                spacing=tokens.SPACE_SM,
            )
            dialog.actions = [
                ft.FilledButton("Close", on_click=lambda e: _close_active_auth(ctrl))
            ]
            dialog.update()


async def on_auth_gcp(ctrl, e=None):
    dialog = ft.AlertDialog(
        title=ft.Text("Authenticating GCP..."),
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.ProgressRing(width=24, height=24, stroke_width=3),
                        ft.Text(
                            "Initiating GCP auth on virtual machine...",
                            size=tokens.FONT_SM,
                            weight=ft.FontWeight.W_500,
                        ),
                    ],
                    spacing=tokens.SPACE_MD,
                ),
                ft.Text(
                    "Please wait while Colab checks or sets up your credentials...",
                    size=tokens.FONT_XS,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            tight=True,
            spacing=tokens.SPACE_SM,
        ),
        actions=[ft.TextButton("Cancel", on_click=lambda e: _close_active_auth(ctrl))],
        modal=True,
    )
    _active_auth_dialog["current"] = dialog
    ctrl.page.show_dialog(dialog)
    ctrl.page.update()

    try:
        await ctrl.colab_service.auth_gcp_on_vm(
            ctrl.session_name,
            auth_method=ctrl.state.auth_method,
            on_output=action_output(ctrl, "Auth GCP"),
            stdin_hook=ctrl.interactive_stdin_hook,
        )
        if dialog.open:
            dialog.title = ft.Text("Success")
            dialog.content = ft.Row(
                [
                    ft.Icon(ft.Icons.CHECK_CIRCLE_ROUNDED, color="green", size=24),
                    ft.Text(
                        "GCP authenticated successfully on VM",
                        size=tokens.FONT_SM,
                        weight=ft.FontWeight.BOLD,
                    ),
                ],
                spacing=tokens.SPACE_SM,
            )
            dialog.actions = [
                ft.FilledButton("Done", on_click=lambda e: _close_active_auth(ctrl))
            ]
            dialog.update()

            async def _auto_close():
                await asyncio.sleep(1.5)
                _close_active_auth(ctrl)

            ctrl.page.run_task(_auto_close)
    except Exception as ex:
        if dialog.open:
            dialog.title = ft.Text("Failed")
            dialog.content = ft.Row(
                [
                    ft.Icon(ft.Icons.ERROR_ROUNDED, color="red", size=24),
                    ft.Text(f"Error: {ex}", size=tokens.FONT_SM),
                ],
                spacing=tokens.SPACE_SM,
            )
            dialog.actions = [
                ft.FilledButton("Close", on_click=lambda e: _close_active_auth(ctrl))
            ]
            dialog.update()


async def on_view_logs(ctrl, e=None):
    if ctrl.navigate:
        await ctrl.navigate(f"/history?session={ctrl.session_name}")


async def on_keep_alive(ctrl, e=None):
    ctrl.state.keep_alive_enabled = e.control.value
    await ctrl.storage.set(constants.STORAGE_KEEP_ALIVE, str(e.control.value).lower())


async def on_keep_alive_disconnect(ctrl, e=None):
    ctrl.state.keep_alive_on_disconnect = e.control.value
    await ctrl.storage.set(
        constants.STORAGE_KEEP_ALIVE_ON_DISCONNECT,
        str(e.control.value).lower(),
    )

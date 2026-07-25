import asyncio
import logging
import threading

import flet as ft

from core import tokens

logger = logging.getLogger("session_dialogs")


def show_interactive_stdin_dialog(ctrl, prompt, *args, **kwargs):
    input_event = threading.Event()
    user_input = {"value": ""}

    if isinstance(prompt, dict):
        content_dict = prompt.get("content", {})
        prompt_str = content_dict.get("prompt", str(prompt))
        is_password = content_dict.get("password", False)
    else:
        prompt_str = str(prompt) if prompt else "Input required"
        is_password = any(
            kw in prompt_str.lower()
            for kw in ("password", "token", "secret", "hf_", "api_key", "getpass")
        )

    extracted_url = None
    for word in prompt_str.split():
        if word.startswith(("http://", "https://")):
            extracted_url = word.strip("'\"),;:")
            break

    is_ephemeral_drive_oauth = bool(
        extracted_url and "authorize-for-drive-credentials-ephem" in extracted_url
    )

    dialog_field = ft.TextField(
        label="Verification Code (Paste code here and click Submit)"
        if extracted_url
        else "Verification Code / Input",
        autofocus=False,
        password=is_password and not bool(extracted_url),
        can_reveal_password=is_password and not bool(extracted_url),
    )

    def _close_dialog(success=True, message=None):
        if not dialog.open:
            return
        dialog.open = False
        ctrl.page.update()
        if ctrl.snack and success and is_ephemeral_drive_oauth:
            ctrl.snack("✅ Google Drive authorized successfully!")
        elif ctrl.snack and not success and message:
            ctrl.snack(f"❌ {message}")

    on_complete = kwargs.get("on_complete")
    if isinstance(on_complete, dict):
        on_complete["fn"] = _close_dialog

    def _submit_input(e=None):
        if not dialog.open:
            return
        user_input["value"] = dialog_field.value or ""
        if is_ephemeral_drive_oauth:
            dialog.title = ft.Text("Verifying Authorization...")
            dialog.content = ft.Column(
                [
                    ft.Row(
                        [
                            ft.ProgressRing(width=24, height=24, stroke_width=3),
                            ft.Text(
                                "Checking credentials with Google servers...",
                                size=tokens.FONT_SM,
                                weight=ft.FontWeight.BOLD,
                            ),
                        ],
                        spacing=tokens.SPACE_MD,
                    ),
                    ft.Text(
                        "Please wait up to 20 seconds while Google syncs your authorization across their backend...",
                        size=tokens.FONT_XS,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                tight=True,
                spacing=tokens.SPACE_SM,
            )
            dialog.actions = [
                ft.TextButton(
                    "Cancel",
                    on_click=lambda e: _close_dialog(False, "Authorization cancelled"),
                )
            ]
            dialog.update()
        else:
            dialog.open = False
            ctrl.page.update()
        input_event.set()

    dialog_field.on_submit = _submit_input

    display_text = prompt_str
    if extracted_url and len(extracted_url) > 60:
        display_text = display_text.replace(extracted_url, "").strip()
        if not display_text or "Google Drive Authorization Required" in display_text:
            if is_ephemeral_drive_oauth:
                display_text = (
                    "Google Drive Authorization Required.\n\n"
                    "1. Click '🌐 Open Link in Browser' below and choose your Google account.\n"
                    "2. Click 'Allow' on the Google permission page.\n\n"
                    "Once the web page says 'Please close this window', return here and click 'Confirm & Continue' below!"
                )
            else:
                display_text = (
                    "GCP / Google Cloud Authorization Required.\n\n"
                    "1. Click '🌐 Open Link in Browser' below and sign into your Google account.\n"
                    "2. Click 'Allow' to grant credentials access.\n"
                    "3. Copy the verification code (`4/0AX...`), paste it into the box below, and click 'Submit'!"
                )

    content_controls = [ft.Text(display_text, size=tokens.FONT_SM, selectable=True)]
    if extracted_url:

        async def _launch_url_task(e=None):
            await ft.UrlLauncher().launch_url(extracted_url)

        async def _copy_url_task(e=None):
            await ft.Clipboard().set(extracted_url)
            if ctrl.snack:
                ctrl.snack("Copied URL to clipboard!")

        content_controls.append(
            ft.Row(
                [
                    ft.FilledButton(
                        "🌐 Open Link in Browser",
                        on_click=lambda e: ctrl.page.run_task(_launch_url_task, e),
                    ),
                    ft.IconButton(
                        ft.Icons.COPY_ROUNDED,
                        tooltip="Copy URL",
                        on_click=lambda e: ctrl.page.run_task(_copy_url_task, e),
                    ),
                ],
                wrap=True,
            )
        )
    if not is_ephemeral_drive_oauth:
        content_controls.append(dialog_field)

    dialog = ft.AlertDialog(
        title=ft.Text("Authentication / Input Required"),
        content=ft.Column(
            controls=content_controls, tight=True, spacing=tokens.SPACE_MD
        ),
        actions=[
            ft.TextButton("Cancel", on_click=lambda e: _submit_input()),
            ft.FilledButton(
                "Confirm & Continue" if is_ephemeral_drive_oauth else "Submit",
                on_click=_submit_input,
            ),
        ],
        modal=True,
    )

    async def _show():
        ctrl.page.show_dialog(dialog)
        await asyncio.sleep(0)
        ctrl.page.update()

    ctrl.page.run_task(_show)
    input_event.wait(timeout=300)
    return user_input["value"]

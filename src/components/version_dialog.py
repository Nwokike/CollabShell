"""Version dialog — always available from the header version chip, the Home
update banner, and the Settings version row.

Two modes:
- Up to date: current version's bundled changelog (works offline) plus a
  Check for Updates button that re-checks live.
- Update available (server build newer): server release notes as Markdown
  with launch buttons — Android gets Play Store + Direct APK (when a
  playstore_url is published), every other platform gets the GitHub
  release only.

Delivery is deliberately browser-based: URLs launch externally; there is
no in-app APK download or install.
"""

import logging

import flet as ft

from core.changelog import notes_for
from core.constants import APP_VERSION, ERR_NETWORK, GITHUB_RELEASES_URL
from core.notifications import show_notification
from core.state import state
from core.theme import AppColors

logger = logging.getLogger(__name__)


def _launch(page: ft.Page, url: str):
    async def _run():
        try:
            await ft.UrlLauncher().launch_url(url)
        except Exception as ex:
            logger.debug("Update URL launch failed: %s", ex)
            show_notification(page, ERR_NETWORK, is_error=True)

    page.run_task(_run)


def _pop_and_launch(page: ft.Page, url: str):
    """Dismiss the dialog, then hand the URL to the browser/app store."""
    try:
        page.pop_dialog()
    except Exception:
        logger.exception("Suppressed exception")
    _launch(page, url)


async def check_from_dialog(page: ft.Page):
    """Live re-check from the up-to-date dialog; morphs it to update mode
    if the server now reports a newer build."""
    from services.update_service import UpdateService

    try:
        page.pop_dialog()
    except Exception:
        logger.exception("Suppressed exception")
    result = await UpdateService().check_for_update()
    if result:
        state.update_available = True
        state.update_data = result
        show_version_dialog(page, result)
    else:
        show_notification(page, f"✓ {APP_VERSION} is up to date")


def _build_update_buttons(page: ft.Page, data: dict) -> list[ft.Control]:
    """Platform rule: Android → Play Store (when published) + Direct APK;
    every other platform → GitHub release only."""
    buttons: list[ft.Control] = []
    is_android = page.platform == ft.PagePlatform.ANDROID
    github_url = data.get("github_url", GITHUB_RELEASES_URL)

    if is_android and data.get("playstore_url"):
        buttons.append(
            ft.FilledButton(
                content=ft.Text("Google Play", font_family="Outfit"),
                icon=ft.Icons.SHOP_ROUNDED,
                on_click=lambda e, u=data["playstore_url"]: _pop_and_launch(page, u),
            )
        )
        buttons.append(
            ft.OutlinedButton(
                content=ft.Text("Direct APK (GitHub)", font_family="Outfit"),
                icon=ft.Icons.DOWNLOAD_ROUNDED,
                on_click=lambda e, u=github_url: _pop_and_launch(page, u),
            )
        )
    else:
        buttons.append(
            ft.FilledButton(
                content=ft.Text("Download from GitHub", font_family="Outfit"),
                icon=ft.Icons.DOWNLOAD_ROUNDED,
                on_click=lambda e, u=github_url: _pop_and_launch(page, u),
            )
        )
    if not data.get("mandatory"):
        buttons.append(
            ft.TextButton(
                content=ft.Text("Later", font_family="Outfit"),
                on_click=lambda e: page.pop_dialog(),
            )
        )
    return buttons


def _build_current_buttons(page: ft.Page) -> list[ft.Control]:
    return [
        ft.OutlinedButton(
            content=ft.Text("Check for Updates", font_family="Outfit"),
            icon=ft.Icons.SYNC_ROUNDED,
            on_click=lambda e: page.run_task(check_from_dialog, page),
        ),
        ft.TextButton(
            content=ft.Text("Close", font_family="Outfit"),
            on_click=lambda e: page.pop_dialog(),
        ),
    ]


def show_version_dialog(page: ft.Page, update_data: dict | None = None):
    """Open the version dialog. Uses a fresh check result when given (the
    dialog's own Check button), else the observable state."""
    data = update_data if update_data is not None else state.update_data
    is_update = bool(data)

    if is_update:
        title_text = data.get("title") or (
            f"Version {data.get('version', '')} Available!"
        )
        icon = (
            ft.Icons.CAMPAIGN_ROUNDED
            if data.get("type") == "announcement"
            else ft.Icons.ROCKET_LAUNCH_ROUNDED
        )
        icon_color = (
            AppColors.WARNING
            if data.get("type") == "announcement"
            else ft.Colors.PRIMARY
        )
        body = ft.Column(
            controls=[
                ft.Text(
                    f"Version {data.get('version', '')} is now available.",
                    size=13,
                ),
                ft.Text("What's New:", size=13, weight=ft.FontWeight.W_600),
                ft.Container(
                    content=ft.Markdown(
                        data.get("release_notes", ""),
                        selectable=True,
                        extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                        on_tap_link=lambda e: _launch(page, e.data),
                    ),
                    width=360,
                ),
            ],
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
            tight=True,
        )
        actions = _build_update_buttons(page, data)
        modal = bool(data.get("mandatory"))
    else:
        title_text = "You're up to date"
        icon = ft.Icons.VERIFIED_ROUNDED
        icon_color = ft.Colors.PRIMARY
        body = ft.Column(
            controls=[
                ft.Text(f"✓ Latest version · v{APP_VERSION}", size=13),
                ft.Text("What's New:", size=13, weight=ft.FontWeight.W_600),
                ft.Container(
                    content=ft.Markdown(
                        notes_for(APP_VERSION),
                        selectable=True,
                        extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                        on_tap_link=lambda e: _launch(page, e.data),
                    ),
                    width=360,
                ),
            ],
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
            tight=True,
        )
        actions = _build_current_buttons(page)
        modal = False

    dlg = ft.AlertDialog(
        modal=modal,
        title=ft.Row(
            controls=[
                ft.Icon(icon, color=icon_color, size=24),
                ft.Text(title_text, weight=ft.FontWeight.BOLD, font_family="Outfit"),
            ],
            spacing=10,
        ),
        content=body,
        actions=actions,
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dlg)

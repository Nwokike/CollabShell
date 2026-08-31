"""UpdateDialog — ported from Sherlock, branded for CollabShell."""
from __future__ import annotations

import asyncio
import logging

import flet as ft

from core.theme import AppColors

logger = logging.getLogger("UpdateDialog")
def show_update_dialog(page: ft.Page, update_data: dict) -> None:
    if not page or not update_data:
        return
    is_mandatory = bool(update_data.get("mandatory", False))
    is_announcement = update_data.get("type") == "announcement"
    title_text = update_data.get("title", "Announcement" if is_announcement else f"New Version {update_data.get('version','')} Available!")
    release_notes = update_data.get("release_notes", "")
    github_url = update_data.get("github_url", "")
    playstore_url = update_data.get("playstore_url", "")
    action_url = update_data.get("action_url") or github_url
    is_android = page.platform == ft.PagePlatform.ANDROID
    async def _launch(url: str):
        page.pop_dialog()
        try:
            await ft.UrlLauncher().launch_url(url)
        except Exception as exc:
            logger.warning("Failed to launch %s: %s", url, exc)
    def _dismiss(e): page.pop_dialog()
    actions: list[ft.Control] = []
    if is_announcement:
        if action_url: actions.append(ft.FilledButton(content=ft.Text("Learn More", weight=ft.FontWeight.W_600, color=ft.Colors.WHITE), icon=ft.Icons.OPEN_IN_NEW_ROUNDED, on_click=lambda e: asyncio.create_task(_launch(action_url))))
    else:
        if is_android:
            if playstore_url: actions.append(ft.FilledButton(content=ft.Text("Google Play", weight=ft.FontWeight.W_600, color=ft.Colors.WHITE), icon=ft.Icons.SHOP_ROUNDED, on_click=lambda e: asyncio.create_task(_launch(playstore_url))))
            if github_url: actions.append(ft.OutlinedButton(content=ft.Text("Direct APK (GitHub)", weight=ft.FontWeight.W_600), icon=ft.Icons.DOWNLOAD_ROUNDED, on_click=lambda e: asyncio.create_task(_launch(github_url))))
        else:
            if github_url: actions.append(ft.FilledButton(content=ft.Text("Download from GitHub", weight=ft.FontWeight.W_600, color=ft.Colors.WHITE), icon=ft.Icons.DOWNLOAD_ROUNDED, on_click=lambda e: asyncio.create_task(_launch(github_url))))
    if not is_mandatory: actions.append(ft.TextButton("Later", on_click=_dismiss, style=ft.ButtonStyle(color=ft.Colors.with_opacity(0.5, ft.Colors.ON_SURFACE))))
    content_controls: list[ft.Control] = []
    if not is_announcement and update_data.get("version"):
        content_controls.append(ft.Text(f"Version {update_data['version']} is now available.", size=12, color=ft.Colors.ON_SURFACE, weight=ft.FontWeight.W_500))
        content_controls.append(ft.Container(height=8))
    if release_notes:
        if not is_announcement: content_controls.extend([ft.Text("What's New:", size=12, weight=ft.FontWeight.W_600, color=AppColors.PRIMARY), ft.Container(height=4)])
        content_controls.append(ft.Markdown(release_notes, selectable=True, extension_set=ft.MarkdownExtensionSet.GITHUB_WEB, on_tap_link=lambda e: asyncio.create_task(ft.UrlLauncher().launch_url(e.data))))
    icon_data = ft.Icons.CAMPAIGN_ROUNDED if is_announcement else ft.Icons.ROCKET_LAUNCH_ROUNDED
    icon_color = AppColors.ACCENT if is_announcement else AppColors.PRIMARY
    dlg = ft.AlertDialog(modal=is_mandatory, title=ft.Row([ft.Icon(icon_data, color=icon_color, size=24), ft.Text(title_text, size=14, weight=ft.FontWeight.BOLD, font_family="Outfit", expand=True)], spacing=8), content=ft.Container(content=ft.Column(controls=content_controls, tight=True, spacing=0, scroll=ft.ScrollMode.AUTO), width=360), actions=actions, actions_alignment=ft.MainAxisAlignment.END)
    page.show_dialog(dlg)

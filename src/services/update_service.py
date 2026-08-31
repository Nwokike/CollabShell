"""UpdateService — checks version.json on GitHub for app updates and announcements."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger("UpdateService")
try:
    import tomllib
    from pathlib import Path
    _pp = Path(__file__).resolve().parent.parent.parent / "pyproject.toml"
    with open(_pp, "rb") as f:
        _pdata = tomllib.load(f)
    _APP_VERSION = _pdata["project"]["version"]
    _APP_BUILD = int(_pdata["tool"]["flet"]["build_number"])
    _APP_REPO = "CollabShell"
except Exception:
    _APP_VERSION = "2.1.0"; _APP_BUILD = 9; _APP_REPO = "CollabShell"
UPDATE_CONFIG_URL = f"https://raw.githubusercontent.com/Nwokike/{_APP_REPO}/main/version.json"
GITHUB_RELEASES_URL = f"https://github.com/Nwokike/{_APP_REPO}/releases/latest"
PLAY_STORE_URL = "https://play.google.com/store/apps/details?id=ng.kiri.collabshell"
@dataclass
class UpdateInfo:
    version: str; build_number: int; type: str; title: str
    release_notes: str; mandatory: bool; github_url: str; playstore_url: str; action_url: str | None = None
    def to_dict(self) -> dict:
        return {"version": self.version, "build_number": self.build_number, "type": self.type, "title": self.title, "release_notes": self.release_notes, "mandatory": self.mandatory, "github_url": self.github_url, "playstore_url": self.playstore_url, "action_url": self.action_url}
class UpdateService:
    def __init__(self, config_url: str = UPDATE_CONFIG_URL):
        self.config_url = config_url
    async def check_for_update(self) -> dict | None:
        try:
            async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as client:
                resp = await client.get(self.config_url)
                if resp.status_code != 200:
                    return None
                data = resp.json()
                if not isinstance(data, dict):
                    return None
                server_build = data.get("build_number", 0)
                if server_build > _APP_BUILD:
                    info = UpdateInfo(version=str(data.get("version", _APP_VERSION)), build_number=int(server_build), type=str(data.get("type", "update")), title=str(data.get("title", f"Version {data.get('version', '')} Available!" if data.get("type") != "announcement" else "Announcement")), release_notes=str(data.get("release_notes", "")), mandatory=bool(data.get("mandatory", False)), github_url=str(data.get("github_url", GITHUB_RELEASES_URL)), playstore_url=str(data.get("playstore_url", PLAY_STORE_URL)), action_url=data.get("action_url"))
                    logger.info("New update/announcement: build %s (current %s)", server_build, _APP_BUILD)
                    return info.to_dict()
        except Exception as ex:
            logger.debug("Update check failed (expected if offline): %s", ex)
        return None

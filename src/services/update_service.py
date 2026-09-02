"""Update service — checks version.json on the repo's main branch and
reports whether a newer build is available (or an announcement is set).

Deliberately browser-based delivery: the dialog launches the release/Play
Store URL externally; there is no in-app APK download or install.

The local version truth is core.constants (APP_VERSION / APP_BUILD_NUMBER),
which ships inside the packaged app — pyproject.toml is not available at
runtime in production builds.
"""

import logging
from dataclasses import dataclass

import httpx

from core.constants import (
    APP_BUILD_NUMBER,
    APP_VERSION,
    GITHUB_RELEASES_URL,
    UPDATE_CONFIG_URL,
)

logger = logging.getLogger(__name__)


@dataclass
class UpdateInfo:
    version: str
    build_number: int
    type: str = "update"
    title: str = ""
    release_notes: str = ""
    mandatory: bool = False
    github_url: str = GITHUB_RELEASES_URL
    playstore_url: str | None = None

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "build_number": self.build_number,
            "type": self.type,
            "title": self.title,
            "release_notes": self.release_notes,
            "mandatory": self.mandatory,
            "github_url": self.github_url,
            "playstore_url": self.playstore_url,
        }


class UpdateService:
    def __init__(self, config_url: str = UPDATE_CONFIG_URL):
        self.config_url = config_url

    async def check_for_update(self) -> dict | None:
        """Return an UpdateInfo dict when the server build is newer (or an
        announcement is set), else None. Every failure path is silent —
        an offline or unreachable check must never disturb the user."""
        try:
            async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as client:
                resp = await client.get(self.config_url)
                if resp.status_code != 200:
                    logger.debug("Update check non-200: %s", resp.status_code)
                    return None
                data = resp.json()
            if not isinstance(data, dict):
                return None

            server_build = data.get("build_number", 0)
            if not isinstance(server_build, int) or server_build <= APP_BUILD_NUMBER:
                return None

            info_type = data.get("type", "update")
            return UpdateInfo(
                version=data.get("version", APP_VERSION),
                build_number=server_build,
                type=info_type,
                title=data.get("title")
                or (f"Version {data.get('version', '')} Available!"),
                release_notes=data.get("release_notes", ""),
                mandatory=bool(data.get("mandatory", False)),
                github_url=data.get("github_url", GITHUB_RELEASES_URL),
                playstore_url=data.get("playstore_url"),
            ).to_dict()
        except Exception as ex:
            logger.debug("Update check failed (expected if offline): %s", ex)
            return None

"""Platform-resilient key-value storage service.

Settings live in Flet's native SharedPreferences, which writes immediately —
there is no debounce window that can lose the last change on exit. Notebook
snapshots stay as individual JSON files beside them. A one-time import
carries any values previously kept in storage.json, which stays on disk as a
backup.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path

import flet as ft

# Shared storage directory resolver — matches core.storage_patch so desktop
# and mobile never diverge.
from core.storage_patch import resolve_storage_dir

logger = logging.getLogger(__name__)

_STORAGE_DIR = Path(resolve_storage_dir())
_LEGACY_STORAGE_FILE = _STORAGE_DIR / "storage.json"


def _slugify(name: str) -> str:
    """Sanitize session names into valid filename tokens."""
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", name)


class StorageService:
    """Key-value settings on SharedPreferences + JSON notebook snapshots."""

    def __init__(self, page: ft.Page):
        self._page = page
        # Service auto-registers with the current page; hold a reference so
        # flet doesn't unregister it while the app runs.
        self._prefs = ft.SharedPreferences()
        self._lock = asyncio.Lock()
        self._migrated = False
        logger.info("StorageService: using native SharedPreferences")

    async def _ensure_migrated(self) -> None:
        if self._migrated:
            return
        async with self._lock:
            if self._migrated:
                return
            try:
                if _LEGACY_STORAGE_FILE.exists():
                    raw = await asyncio.to_thread(_LEGACY_STORAGE_FILE.read_bytes)
                    legacy = json.loads(raw.decode("utf-8")) if raw else {}
                    imported = 0
                    for key, value in legacy.items():
                        if isinstance(
                            value, str
                        ) and not await self._prefs.contains_key(key):
                            await self._prefs.set(key, value)
                            imported += 1
                    logger.info(
                        "Imported %d legacy storage.json settings (of %d)",
                        imported,
                        len(legacy),
                    )
            except Exception as e:
                logger.warning("Legacy settings import failed: %s", e)
            finally:
                self._migrated = True

    async def get(self, key: str, default=None) -> str | None:
        await self._ensure_migrated()
        value = await self._prefs.get(key)
        return default if value is None else str(value)

    async def set(self, key: str, value) -> None:
        if not isinstance(value, str):
            value = str(value)
        await self._ensure_migrated()
        await self._prefs.set(key, value)

    async def remove(self, key: str) -> None:
        await self._ensure_migrated()
        await self._prefs.remove(key)

    async def contains(self, key: str) -> bool:
        await self._ensure_migrated()
        return bool(await self._prefs.contains_key(key))

    async def delete(self, key: str) -> None:
        await self.remove(key)

    async def flush(self) -> None:
        """No-op: SharedPreferences writes land immediately."""

    def _get_notebook_file(self, session_name: str) -> Path:
        return _STORAGE_DIR / f"notebook_{_slugify(session_name)}.json"

    async def save_notebook(self, session_name: str, cells: list[dict]) -> None:
        try:
            nb_file = self._get_notebook_file(session_name)
            # Atomic write: temp + rename
            data_bytes = json.dumps(cells, ensure_ascii=False, indent=2).encode("utf-8")
            tmp = nb_file.with_suffix(".json.tmp")
            tmp.write_bytes(data_bytes)
            tmp.replace(nb_file)
        except Exception as e:
            logger.warning("StorageService.save_notebook failed: %s", e)

    async def load_notebook(self, session_name: str) -> list[dict]:
        try:
            nb_file = self._get_notebook_file(session_name)
            if nb_file.exists():
                raw = nb_file.read_bytes()
                if raw:
                    return json.loads(raw.decode("utf-8"))
        except Exception as e:
            logger.warning("StorageService.load_notebook failed: %s", e)
        return []

    async def cleanup_orphaned_notebooks(self, active_session_names: list[str]) -> None:
        """Deletes notebook history for sessions that no longer exist.

        Safety: if *active_session_names* is empty we short-circuit so that a
        transient failure when refreshing the session list does **not** delete
        every cached notebook (data-loss prevention).
        """
        if not active_session_names:
            logger.debug("cleanup_orphaned_notebooks: empty list — skipped")
            return
        try:
            if not _STORAGE_DIR.exists():
                return

            active_files = {
                f"notebook_{_slugify(name)}.json" for name in active_session_names
            }

            for f in _STORAGE_DIR.glob("notebook_*.json"):
                if f.name not in active_files:
                    logger.info("Cleaning up orphaned notebook: %s", f.name)
                    f.unlink(missing_ok=True)
        except Exception as e:
            logger.warning("StorageService.cleanup_orphaned_notebooks failed: %s", e)

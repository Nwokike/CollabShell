"""Platform-resilient key-value storage service.

Uses a single local JSON file approach for desktop (storage/storage.json beside src),
and the mobile sandbox directory for Android.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path

import flet as ft

logger = logging.getLogger(__name__)

# Use Flet sandbox data storage path on Android/iOS mobile to avoid permission issues
storage_env = os.getenv("FLET_APP_STORAGE_DATA")
if storage_env:
    _STORAGE_DIR = Path(storage_env) / "colab-cli"
else:
    # On desktop, the user wants the storage folder beside src.
    _STORAGE_DIR = Path.cwd() / "storage"

_STORAGE_FILE = _STORAGE_DIR / "storage.json"
_WRITE_DEBOUNCE_SEC = 1.0


class StorageService:
    """Wraps persistent key-value storage mimicking Sherlock/DDGS."""

    def __init__(self, page: ft.Page):
        self._page = page
        self._data: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._dirty = False
        self._last_write: float = 0.0
        self._pending_write_task: asyncio.Task | None = None

        logger.info("StorageService: using local storage.json")
        self._load()

    def _load(self) -> None:
        _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        if _STORAGE_FILE.exists():
            try:
                raw = _STORAGE_FILE.read_bytes()
                if raw:
                    self._data = json.loads(raw.decode("utf-8"))
                else:
                    self._data = {}
            except Exception as e:
                logger.warning("StorageService._load failed: %s", e)
                self._data = {}
        else:
            self._data = {}

    def _save_now(self) -> None:
        try:
            _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
            _STORAGE_FILE.write_bytes(
                json.dumps(self._data, ensure_ascii=False, indent=2).encode("utf-8")
            )
            self._dirty = False
            self._last_write = time.monotonic()
        except Exception as e:
            logger.warning("StorageService._save_now failed: %s", e)

    def _schedule_write(self) -> None:
        if self._pending_write_task:
            return
        try:
            loop = asyncio.get_running_loop()
            self._pending_write_task = loop.call_later(
                _WRITE_DEBOUNCE_SEC,
                lambda: loop.create_task(self._flush_task()),
            )
        except RuntimeError:
            self._save_now()

    async def _flush_task(self) -> None:
        try:
            await self.flush()
        finally:
            self._pending_write_task = None

    async def get(self, key: str, default=None) -> str | None:
        async with self._lock:
            return self._data.get(key, default)

    async def set(self, key: str, value) -> None:
        if not isinstance(value, str):
            value = str(value)
        async with self._lock:
            self._data[key] = value
            self._dirty = True
        self._schedule_write()

    async def remove(self, key: str) -> None:
        async with self._lock:
            self._data.pop(key, None)
            self._dirty = True
        self._schedule_write()

    async def contains(self, key: str) -> bool:
        async with self._lock:
            return key in self._data

    async def delete(self, key: str) -> None:
        await self.remove(key)

    async def flush(self) -> None:
        async with self._lock:
            if self._dirty:
                self._save_now()

    def _get_notebook_file(self, session_name: str) -> Path:
        return _STORAGE_DIR / f"notebook_{session_name}.json"

    async def save_notebook(self, session_name: str, cells: list[dict]) -> None:
        try:
            nb_file = self._get_notebook_file(session_name)
            nb_file.write_bytes(
                json.dumps(cells, ensure_ascii=False, indent=2).encode("utf-8")
            )
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
        """Deletes notebook history for sessions that no longer exist."""
        try:
            if not _STORAGE_DIR.exists():
                return

            active_files = [f"notebook_{name}.json" for name in active_session_names]

            for f in _STORAGE_DIR.glob("notebook_*.json"):
                if f.name not in active_files:
                    logger.info("Cleaning up orphaned notebook: %s", f.name)
                    f.unlink(missing_ok=True)
        except Exception as e:
            logger.warning("StorageService.cleanup_orphaned_notebooks failed: %s", e)

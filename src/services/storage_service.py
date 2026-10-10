"""Platform-resilient key-value storage service.

Uses a single local JSON file approach for desktop (storage/storage.json beside src),
and the mobile sandbox directory for Android.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path

import flet as ft

# Shared storage directory resolver — matches core.storage_patch so desktop
# and mobile never diverge.
from core.storage_patch import resolve_storage_dir

logger = logging.getLogger(__name__)

# Use Flet sandbox data storage path on Android/iOS mobile to avoid permission issues
_STORAGE_DIR = Path(resolve_storage_dir())

_STORAGE_FILE = _STORAGE_DIR / "storage.json"
_WRITE_DEBOUNCE_SEC = 1.0


def _slugify(name: str) -> str:
    """Sanitize session names into valid filename tokens."""
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", name)


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
            data_bytes = json.dumps(self._data, ensure_ascii=False, indent=2).encode(
                "utf-8"
            )
            # Backup the current file before overwriting (only if content changed)
            if _STORAGE_FILE.exists():
                old = _STORAGE_FILE.read_bytes()
                if old != data_bytes:
                    bak = _STORAGE_FILE.with_suffix(".json.bak")
                    bak.write_bytes(old)
            # Atomic write via temp file + rename
            tmp = _STORAGE_FILE.with_suffix(".json.tmp")
            tmp.write_bytes(data_bytes)
            tmp.replace(_STORAGE_FILE)
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

    def _get_notebook_file(
        self, session_name: str, notebook_id: str | None = None
    ) -> Path:
        base = f"notebook_{_slugify(session_name)}"
        if notebook_id:
            base += f"__{_slugify(notebook_id)}"
        return _STORAGE_DIR / f"{base}.json"

    def _get_tab_index_file(self, session_name: str) -> Path:
        return (
            _STORAGE_DIR / f"notebook_{_slugify(session_name)}__index.json"
        )

    async def save_tab_index(self, session_name: str, tabs: list[dict]) -> None:
        """Persist tab order, names, and view prefs (sidecar to per-tab files).

        Tabs is a list of {"id", "name", "view"}. Kept separate from the cell
        payloads so per-tab files stay unchanged in shape and the legacy
        single-file migration is untouched.
        """
        try:
            index_file = self._get_tab_index_file(session_name)
            payload = {
                "tabs": [
                    {
                        "id": str(t.get("id", "")),
                        "name": str(t.get("name", "")),
                        "view": str(t.get("view") or "notebook"),
                    }
                    for t in tabs
                    if t.get("id")
                ]
            }
            data_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode(
                "utf-8"
            )
            tmp = index_file.with_suffix(".json.tmp")
            tmp.write_bytes(data_bytes)
            tmp.replace(index_file)
        except Exception as e:
            logger.warning("StorageService.save_tab_index failed: %s", e)

    async def load_tab_index(self, session_name: str) -> list[dict] | None:
        """Tab metadata list, or None when no index exists yet.

        None (not an empty list) is the "never written an index" signal so the
        caller can run the glob fallback / legacy migration.
        """
        try:
            index_file = self._get_tab_index_file(session_name)
            if not index_file.exists():
                return None
            raw = index_file.read_bytes()
            if not raw:
                return None
            data = json.loads(raw.decode("utf-8"))
            tabs = data.get("tabs") if isinstance(data, dict) else None
            if not isinstance(tabs, list):
                return None
            return [t for t in tabs if isinstance(t, dict) and t.get("id")]
        except Exception as e:
            logger.warning("StorageService.load_tab_index failed: %s", e)
            return None

    async def save_notebook(
        self,
        session_name: str,
        cells: list[dict],
        notebook_id: str | None = None,
    ) -> None:
        try:
            nb_file = self._get_notebook_file(session_name, notebook_id)
            # Atomic write: temp + rename (same pattern as _save_now)
            data_bytes = json.dumps(cells, ensure_ascii=False, indent=2).encode("utf-8")
            tmp = nb_file.with_suffix(".json.tmp")
            tmp.write_bytes(data_bytes)
            tmp.replace(nb_file)
        except Exception as e:
            logger.warning("StorageService.save_notebook failed: %s", e)

    async def load_notebook(
        self, session_name: str, notebook_id: str | None = None
    ) -> list[dict]:
        try:
            nb_file = self._get_notebook_file(session_name, notebook_id)
            if nb_file.exists():
                raw = nb_file.read_bytes()
                if raw:
                    return json.loads(raw.decode("utf-8"))
            # Legacy migration: pre-tab single file becomes the default tab.
            if notebook_id:
                legacy = self._get_notebook_file(session_name)
                if legacy.exists():
                    raw = legacy.read_bytes()
                    if raw:
                        cells = json.loads(raw.decode("utf-8"))
                        await self.save_notebook(session_name, cells, notebook_id)
                        return cells
        except Exception as e:
            logger.warning("StorageService.load_notebook failed: %s", e)
        return []

    async def list_notebooks(self, session_name: str) -> list[str]:
        """Tab ids with saved files for a session (for tab-bar restore).

        Prefers the tab index because it carries the user's order; falls back
        to the glob when no index exists so installs that already have
        per-tab files migrate instead of losing tabs.
        """
        try:
            prefix = f"notebook_{_slugify(session_name)}__"
            index = await self.load_tab_index(session_name)
            if index is not None:
                return [str(t["id"]) for t in index]
            ids = []
            if _STORAGE_DIR.exists():
                for f in _STORAGE_DIR.glob(f"{prefix}*.json"):
                    tab = f.name[len(prefix) : -len(".json")]
                    # The index sidecar shares the prefix pattern.
                    if tab and tab != "index":
                        ids.append(tab)
            return sorted(ids)
        except Exception as e:
            logger.warning("StorageService.list_notebooks failed: %s", e)
            return []

    async def delete_notebook(
        self, session_name: str, notebook_id: str | None = None
    ) -> None:
        try:
            nb_file = self._get_notebook_file(session_name, notebook_id)
            nb_file.unlink(missing_ok=True)
        except Exception as e:
            logger.warning("StorageService.delete_notebook failed: %s", e)

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

            active_files = set()
            for name in active_session_names:
                slug = _slugify(name)
                active_files.add(f"notebook_{slug}.json")
                # Per-tab files for live sessions are kept; anything else for
                # a live session prefix is also kept (tabs come and go).
                active_files.update(
                    f.name
                    for f in _STORAGE_DIR.glob(f"notebook_{slug}__*.json")
                )
                # The tab index sidecar shares the per-tab prefix and must
                # survive with the tabs it describes.
                active_files.add(f"notebook_{slug}__index.json")

            for f in _STORAGE_DIR.glob("notebook_*.json"):
                if f.name not in active_files:
                    logger.info("Cleaning up orphaned notebook: %s", f.name)
                    f.unlink(missing_ok=True)
        except Exception as e:
            logger.warning("StorageService.cleanup_orphaned_notebooks failed: %s", e)

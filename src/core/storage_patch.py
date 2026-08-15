"""Dynamic patcher to redirect colab_cli storage paths for Android/Local consistency."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import ClassVar


def resolve_storage_dir() -> str:
    """Return the canonical colab-cli storage directory path.

    On mobile the sandbox path (FLET_APP_STORAGE_DATA / colab-cli) is used;
    on desktop the 'storage' folder beside the project root is used.
    Both :func:`apply_storage_patches` and :class:`StorageService` call this
    so they never diverge.
    """
    storage_env = os.getenv("FLET_APP_STORAGE_DATA")
    if storage_env:
        storage_dir = os.path.join(storage_env, "colab-cli")
    else:
        project_root = Path(__file__).resolve().parent.parent.parent
        storage_dir = os.path.join(project_root, "storage")
    return storage_dir


class MemoryLogHandler(logging.Handler):
    """In-memory ring-buffer log handler for live Activity Terminal."""

    _logs: ClassVar[list[str]] = []
    _instance: ClassVar[MemoryLogHandler | None] = None
    _MAX_LOGS = 300

    def emit(self, record):
        try:
            msg = self.format(record)
            MemoryLogHandler._logs.append(msg)
            if len(MemoryLogHandler._logs) > MemoryLogHandler._MAX_LOGS:
                MemoryLogHandler._logs.pop(0)
        except Exception:
            pass

    @classmethod
    def get_instance(cls) -> MemoryLogHandler:
        if cls._instance is None:
            cls._instance = MemoryLogHandler()
        return cls._instance

    @classmethod
    def get_logs(cls) -> list[str]:
        return list(cls._logs)


def apply_storage_patches():
    # 1. Resolve storage directory — shared with StorageService
    storage_dir = resolve_storage_dir()
    os.makedirs(storage_dir, exist_ok=True)

    # 2. Patch colab_cli modules
    import sys
    import types

    # Flet's Android engine strips 'wsgiref' which google_auth_oauthlib depends on.
    if "wsgiref" not in sys.modules:
        wsgiref = types.ModuleType("wsgiref")
        sys.modules["wsgiref"] = wsgiref

        wsgiref_util = types.ModuleType("wsgiref.util")
        sys.modules["wsgiref.util"] = wsgiref_util
        wsgiref_util.request_uri = lambda *a, **k: ""
        wsgiref.util = wsgiref_util

    try:
        import colab_cli.auth.oauth
        import colab_cli.client
        import colab_cli.credentials

        # Patch credential file paths
        colab_cli.credentials.CREDENTIALS_FILE = os.path.join(
            storage_dir, "credentials.json"
        )
        colab_cli.auth.oauth.CREDENTIALS_FILE = os.path.join(
            storage_dir, "credentials.json"
        )
        colab_cli.client.CREDENTIALS_FILE = os.path.join(
            storage_dir, "credentials.json"
        )
        colab_cli.client.SESSIONS_FILE = os.path.join(storage_dir, "sessions.json")
    except ImportError:
        pass

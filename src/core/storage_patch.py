from typing import ClassVar

"""Dynamic patcher to redirect colab_cli storage paths for Android/Local consistency."""

import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


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
        # __file__ …/Collab/src/core/storage_patch.py → project root
        project_root = Path(__file__).resolve().parent.parent.parent
        storage_dir = os.path.join(project_root, "storage")
    return storage_dir


def migrate_legacy_colab_paths() -> int:
    """Copy 2.1.x flat storage into the HOME-redirected layout.

    Up to 2.1.2 the five path monkey-patches forced colab_cli's files
    flat into ``storage/``. With the HOME redirect they resolve under
    ``storage/home/.config/colab-cli/`` instead — so without this an
    upgrading user silently loses their Google login, all sessions, and
    all history. Copies (never moves) and skips anything the new layout
    already has, so it is safe to run on every start.
    """
    base = resolve_storage_dir()
    home = os.path.join(base, "home")
    config_dir = os.path.join(home, ".config", "colab-cli")
    pairs = [
        ("token.json", os.path.join(config_dir, "token.json")),
        ("sessions.json", os.path.join(config_dir, "sessions.json")),
        ("settings.json", os.path.join(config_dir, "settings.json")),
        ("oauth_config.json", os.path.join(home, ".colab-cli-oauth-config.json")),
    ]
    copied = 0
    for name, dst in pairs:
        src = os.path.join(base, name)
        if os.path.isfile(src) and not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1
            logger.info("Migrated %s into the new storage layout", name)
    src_history = os.path.join(base, "history")
    dst_history = os.path.join(config_dir, "history")
    if os.path.isdir(src_history) and not os.path.exists(dst_history):
        os.makedirs(config_dir, exist_ok=True)
        shutil.copytree(src_history, dst_history)
        copied += 1
        logger.info("Migrated history/ into the new storage layout")
    if copied:
        logger.info("Storage migration moved %d item(s) from the old layout", copied)
    return copied


class MemoryLogHandler(logging.Handler):
    """In-memory ring-buffer log handler for live Activity Terminal."""

    _logs: ClassVar[list[str]] = []
    _MAX_LOGS = 300

    def emit(self, record):
        try:
            msg = self.format(record)
            MemoryLogHandler._logs.append(msg)
            if len(MemoryLogHandler._logs) > MemoryLogHandler._MAX_LOGS:
                MemoryLogHandler._logs.pop(0)
        except Exception:
            # Never log here — this IS a logging handler; logging would recurse.
            pass

    @classmethod
    def get_logs(cls) -> list[str]:
        return list(cls._logs)


_memory_log_handler = MemoryLogHandler()
_memory_log_handler.setLevel(logging.DEBUG)
_memory_log_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S"
    )
)
root_logger = logging.getLogger()
if _memory_log_handler not in root_logger.handlers:
    root_logger.addHandler(_memory_log_handler)


_stderr_log_handler: logging.StreamHandler | None = None


def set_log_to_stderr(enabled: bool):
    """Live-toggle routing of all app logs to stderr (Settings → Advanced).

    Adds or removes a dedicated stderr handler on the root logger so the
    toggle takes effect immediately, without a restart.
    """
    global _stderr_log_handler
    import sys

    root = logging.getLogger()
    if enabled and _stderr_log_handler is None:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        root.addHandler(handler)
        _stderr_log_handler = handler
    elif not enabled and _stderr_log_handler is not None:
        root.removeHandler(_stderr_log_handler)
        _stderr_log_handler = None


def apply_storage_patches():
    # 1. Resolve storage directory — shared with StorageService
    storage_dir = resolve_storage_dir()

    os.makedirs(storage_dir, exist_ok=True)

    # 2. Patch colab_cli modules
    import sys
    import types

    # Flet's Android engine strips 'wsgiref' which google_auth_oauthlib depends on.
    # Since we don't run local servers on Android, we can safely mock it.
    if "wsgiref" not in sys.modules:
        wsgiref = types.ModuleType("wsgiref")
        sys.modules["wsgiref"] = wsgiref

        wsgiref_util = types.ModuleType("wsgiref.util")
        sys.modules["wsgiref.util"] = wsgiref_util
        wsgiref_util.request_uri = lambda *a, **k: ""
        wsgiref.util = wsgiref_util

        wsgiref_simple_server = types.ModuleType("wsgiref.simple_server")
        sys.modules["wsgiref.simple_server"] = wsgiref_simple_server

        class MockWSGIRequestHandler:
            pass

        class MockWSGIServer:
            allow_reuse_address = False

        wsgiref_simple_server.WSGIRequestHandler = MockWSGIRequestHandler
        wsgiref_simple_server.WSGIServer = MockWSGIServer
        wsgiref_simple_server.make_server = lambda *a, **k: None
        wsgiref.simple_server = wsgiref_simple_server

    import colab_cli.common
    import colab_cli.state

    # colab_cli's ~/.config paths (token, sessions, settings, history, oauth
    # config) all resolve through the HOME/USERPROFILE redirect set in
    # main.py, and the jupyter-kernel-client symbols the Drive-OAuth hook
    # needs come from the version override in pyproject.toml — neither needs
    # monkey-patching here anymore.

    def patched_setup_logging(log_to_stderr: bool):
        import logging
        import sys

        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)

        has_mem = False
        for handler in logger.handlers:
            if isinstance(handler, MemoryLogHandler):
                has_mem = True
                break
        if not has_mem:
            mem_handler = MemoryLogHandler()
            mem_handler.setFormatter(logging.Formatter(log_format))
            logger.addHandler(mem_handler)

        # Check if already added to avoid duplicates
        has_file = False
        for handler in logger.handlers:
            if isinstance(handler, logging.FileHandler):
                has_file = True
                break
        if not has_file:
            log_path = os.path.join(storage_dir, "colab.log")
            # Simple log rotation: keep last 5 MB before rolling
            _MAX_LOG_BYTES = 5 * 1024 * 1024
            if os.path.exists(log_path) and os.path.getsize(log_path) >= _MAX_LOG_BYTES:
                rotated = log_path + ".1"
                try:
                    os.replace(log_path, rotated)
                except OSError:
                    pass
            file_handler = logging.FileHandler(log_path)
            file_handler.setFormatter(logging.Formatter(log_format))
            logger.addHandler(file_handler)

        if log_to_stderr:
            has_stream = False
            for handler in logger.handlers:
                if (
                    isinstance(handler, logging.StreamHandler)
                    and handler.stream == sys.stderr
                ):
                    has_stream = True
                    break
            if not has_stream:
                stream_handler = logging.StreamHandler(sys.stderr)
                stream_handler.setFormatter(logging.Formatter(log_format))
                logger.addHandler(stream_handler)

    colab_cli.common.setup_logging = patched_setup_logging

    # 3. Defensive patches to eliminate write() str vs bytes TypeErrors when streams or files
    # are wrapped by rich.file_proxy.FileProxy or colab_cli _LockedFileStore.
    try:
        from rich.file_proxy import FileProxy

        _orig_fp_write = FileProxy.write

        def patched_fp_write(self, text):
            if isinstance(text, bytes):
                text = text.decode("utf-8", errors="ignore")
            elif not isinstance(text, str):
                text = str(text)
            return _orig_fp_write(self, text)

        FileProxy.write = patched_fp_write
    except ImportError:
        pass

    try:
        from colab_cli.state import _LockedFileStore

        _orig_write_data = _LockedFileStore._write_data

        def patched_write_data(self, f, data):
            if isinstance(data, bytes):
                data = data.decode("utf-8", errors="ignore")
            elif not isinstance(data, str):
                data = str(data)
            return _orig_write_data(self, f, data)

        _LockedFileStore._write_data = patched_write_data
    except Exception:
        logger.exception("Suppressed exception")

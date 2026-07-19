"""Dynamic patcher to redirect colab_cli storage paths for Android/Local consistency."""

import os
from pathlib import Path


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
        # __file__ …/Colab/src/core/storage_patch.py → project root
        project_root = Path(__file__).resolve().parent.parent.parent
        storage_dir = os.path.join(project_root, "storage")
    return storage_dir


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

    # Android/mobile Jupyter client may be incomplete or missing entirely;
    # ensure all expected attributes exist so downstream imports don't fail.
    if "jupyter_kernel_client" not in sys.modules:
        try:
            import jupyter_kernel_client  # noqa: F401 — ensures it's in sys.modules
        except ImportError:

            def _make_stub_module(fullname):
                mod = types.ModuleType(fullname)
                sys.modules[fullname] = mod
                return mod

            _make_stub_module("jupyter_kernel_client")

    ctx = sys.modules["jupyter_kernel_client"]

    # Patch every public attribute that the real module exposes
    _jupyter_kernel_client_attrs = {
        "JupyterSubprotocol": None,
        "KernelClient": None,
        "KernelHttpManager": None,
        "KernelWebSocketClient": None,
        "KonsoleApp": None,
        "LanguageSnippets": None,
        "SNIPPETS_REGISTRY": None,
        "VariableDescription": None,
        "client": None,
        "constants": None,
        "konsoleapp": None,
        "log": None,
        "manager": None,
        "models": None,
        "shell": None,
        "snippets": None,
        "utils": None,
        "wsclient": None,
    }

    for name in _jupyter_kernel_client_attrs:
        if not hasattr(ctx, name):
            setattr(ctx, name, None)

    # JupyterSubprotocol is special — create a proper enum so code that checks
    # isinstance(value, JupyterSubprotocol) or accesses .value doesn't crash.
    if ctx.JupyterSubprotocol is None:
        import enum

        class MockJupyterSubprotocol(enum.Enum):
            DEFAULT = "v1.kernel.websocket.jupyter.org"
            V1 = "v1.kernel.websocket.jupyter.org"

        ctx.JupyterSubprotocol = MockJupyterSubprotocol

    # Ensure wsclient submodule exists (some imports access it directly)
    if "jupyter_kernel_client.wsclient" not in sys.modules:
        wsclient_mod = types.ModuleType("jupyter_kernel_client.wsclient")
        sys.modules["jupyter_kernel_client.wsclient"] = wsclient_mod
        ctx.wsclient = wsclient_mod
        wsclient_mod.JupyterSubprotocol = ctx.JupyterSubprotocol

    import colab_cli.auth
    import colab_cli.history
    import colab_cli.state
    import colab_cli.common

    # Override token path
    colab_cli.auth.TOKEN_CONFIG_PATH = os.path.join(storage_dir, "token.json")

    # Patch State.__init__ so every new State instance gets the correct paths
    original_state_init = colab_cli.common.State.__init__

    def patched_state_init(self, *args, **kwargs):
        original_state_init(self, *args, **kwargs)
        self.config_path = os.path.join(storage_dir, "sessions.json")
        self.client_oauth_config = os.path.join(storage_dir, "oauth_config.json")

    colab_cli.common.State.__init__ = patched_state_init

    # Override HistoryLogger init so all logs go to canonical storage/history directory
    original_history_init = colab_cli.history.HistoryLogger.__init__
    canonical_history_dir = os.path.join(storage_dir, "history")
    os.makedirs(canonical_history_dir, exist_ok=True)

    def patched_history_init(
        self, log_dir: str = "~/.config/colab-cli/history", *args, **kwargs
    ):
        if (
            not log_dir
            or log_dir == "~/.config/colab-cli/history"
            or log_dir == os.path.expanduser("~/.config/colab-cli/history")
        ):
            log_dir = canonical_history_dir
        original_history_init(self, log_dir, *args, **kwargs)

    colab_cli.history.HistoryLogger.__init__ = patched_history_init

    # Override SettingsStore and StateStore default paths
    colab_cli.state.SettingsStore.__init__.__defaults__ = (
        os.path.join(storage_dir, "settings.json"),
    )
    colab_cli.state.StateStore.__init__.__defaults__ = (
        os.path.join(storage_dir, "sessions.json"),
    )

    # Override colab_cli.common.setup_logging log folder
    def patched_setup_logging(log_to_stderr: bool):
        import logging
        import sys

        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)

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
        pass

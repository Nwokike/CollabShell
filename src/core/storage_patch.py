"""Dynamic patcher to redirect colab_cli storage paths for Android/Local consistency."""

import os
from pathlib import Path


def apply_storage_patches():
    # 1. Resolve storage directory
    storage_env = os.getenv("FLET_APP_STORAGE_DATA")
    if storage_env:
        storage_dir = os.path.join(storage_env, "colab-cli")
    else:
        # Local PC beside 'src'
        # __file__ is /home/.../Colab/src/core/storage_patch.py
        # parent is core/, parent.parent is src/, parent.parent.parent is Colab/ (project root)
        project_root = Path(__file__).resolve().parent.parent.parent
        storage_dir = os.path.join(project_root, "storage")

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

    # Android Jupyter client might be missing JupyterSubprotocol
    try:
        import jupyter_kernel_client.wsclient

        if not hasattr(jupyter_kernel_client, "JupyterSubprotocol"):
            import enum

            class MockJupyterSubprotocol(enum.Enum):
                DEFAULT = "v1.kernel.websocket.jupyter.org"
                V1 = "v1.kernel.websocket.jupyter.org"

            jupyter_kernel_client.JupyterSubprotocol = MockJupyterSubprotocol
            jupyter_kernel_client.wsclient.JupyterSubprotocol = MockJupyterSubprotocol
    except Exception:
        pass

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

    # Override HistoryLogger default path
    colab_cli.history.HistoryLogger.__init__.__defaults__ = (
        os.path.join(storage_dir, "history"),
    )

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
            file_handler = logging.FileHandler(os.path.join(storage_dir, "colab.log"))
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

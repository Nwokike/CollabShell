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
    import colab_cli.auth
    import colab_cli.history
    import colab_cli.state
    import colab_cli.common

    # Override token path
    colab_cli.auth.TOKEN_CONFIG_PATH = os.path.join(storage_dir, "token.json")

    # Override client oauth config path
    colab_cli.common.State.client_oauth_config = os.path.join(
        storage_dir, "oauth_config.json"
    )

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

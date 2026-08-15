"""Central logging configuration for Colab Shell.

Ensures both stdout StreamHandler (for terminal output / debugging)
and MemoryLogHandler (for live in-app Activity Terminal) receive log records.
"""

from __future__ import annotations

import logging
import sys

_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger with stdout StreamHandler and MemoryLogHandler."""
    global _configured
    if _configured:
        return
    _configured = True

    from core.storage_patch import MemoryLogHandler

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)

    existing_types = {type(h) for h in root.handlers}

    if logging.StreamHandler not in existing_types:
        stdout = logging.StreamHandler(sys.stdout)
        stdout.setFormatter(fmt)
        stdout.setLevel(level)
        root.addHandler(stdout)

    memory_handler = MemoryLogHandler.get_instance()
    if memory_handler not in root.handlers:
        memory_handler.setLevel(logging.DEBUG)
        memory_handler.setFormatter(fmt)
        root.addHandler(memory_handler)

    logging.captureWarnings(True)

    logging.getLogger("flet").setLevel(logging.INFO)
    logging.getLogger("flet_controls").setLevel(logging.WARNING)
    logging.getLogger("flet_transport").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

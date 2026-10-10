"""The bundled AI context document, loaded and printed by the app itself.

Copies the `colab_cli` pattern (`colab skill`) exactly: an
`importlib.resources` read with a dev-tree path fallback, so the document ships
inside the package and an agent holding the app can self-fetch it without a
browser or a repo checkout.

Two surfacing modes, both taken from working precedents:
  - `skill_text()` prepends it to the assistant's system prompt (LM Router's
    bundled-guide pattern), behind a default-on setting.
  - `print_skill()` prints it for a human or an external agent.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("ai_context")

_SKILL_FILE = "SKILL.md"


def _importlib_files(filename: str) -> str | None:
    """Read a bundled file through importlib.resources (packaged layout)."""
    from importlib.resources import files

    return files("ai").joinpath(filename).read_text(encoding="utf-8")


def _dev_tree_read(filename: str) -> str | None:
    """Read a bundled file from the dev-tree layout (repo checkout)."""
    import os

    path = os.path.join(
        os.path.dirname(__file__), os.pardir, os.pardir, "ai", filename
    )
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _read_resource(filename: str) -> str | None:
    """Try the packaged layout, then the dev-tree layout.

    Split into two seams so a test can force BOTH to fail and prove the guard
    degrades to None instead of raising. Never raises: a missing or unreadable
    document means the assistant runs on its built-in rules.
    """
    for reader in (_importlib_files, _dev_tree_read):
        try:
            text = reader(filename)
        except Exception:
            logger.debug("%s failed for %s", reader.__name__, filename)
            continue
        if text:
            return text
    return None


def skill_text() -> str:
    """The bundled context document, or "" when unavailable.

    Safe to call on every turn: the file is read from the installed package and
    cached by the filesystem, and a missing file degrades to an empty string
    rather than an exception.
    """
    return _read_resource(_SKILL_FILE) or ""


def print_skill() -> str:
    """The document for external printing (`collab skill` equivalent)."""
    text = skill_text()
    return text if text else "[collabshell] SKILL.md content not available"

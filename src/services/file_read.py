"""Read a session file as text — one place, shared by the assistant and by the
in-context AI buttons (files explain, notebook explain).

The VM is only reachable through the contents API, which *downloads to a local
path*; there is no streaming read. So a "read this file" is really a download
plus a read-back, and the temp file has to be staged and cleaned up. Keeping
that in one function matters because both call sites would otherwise get the
cleanup wrong in a different way.
"""

from __future__ import annotations

import logging
import os
import tempfile

logger = logging.getLogger("file_read")

# Cap on characters handed to the model. A CSV can be gigabytes; the digest
# that matters is the head.
_MAX_CHARS = 12000


def _read_local(path: str) -> str:
    # Read bytes and cap BEFORE decoding: a multi-byte UTF-8 sequence split by
    # the char cap used to decode as garbage, and binary files decoded into
    # mojibake that looked like content. Null bytes in the first chunk mark a
    # binary file — say so instead of handing the model noise.
    with open(path, "rb") as handle:
        raw = handle.read(_MAX_CHARS + 1)
    if b"\x00" in raw[:4096]:
        return "(binary file — contents not shown)"
    return raw.decode("utf-8", errors="replace")


async def read_file_text(
    path: str, *, colab_service, session_name: str, auth_method
) -> str:
    """Return the head of a VM file as text, or "" when it cannot be read.

    Binary files decode badly, so the caller gets whatever survived the
    replace-and-truncate — the AI copes, and a false negative ("(unreadable)")
    is rarer than a failure.
    """
    import asyncio

    # The staged temp file is BOTH the scratch name and the download target:
    # ColabService.download requires a local_path (colab/__init__.py:198), and
    # omitting it raised TypeError, so every read silently returned "".
    fd, local = tempfile.mkstemp(suffix="_ai_read")
    os.close(fd)
    try:
        ok = await colab_service.download(
            path,
            local,
            session_name=session_name,
            auth_method=auth_method,
        )
        if not ok:
            return ""
        # Read off-loop: a blocking read here stalls every other task.
        return await asyncio.to_thread(_read_local, local)
    except Exception as ex:
        logger.debug("read_file_text failed for %s: %s", path, ex)
        return ""
    finally:
        try:
            os.unlink(local)
        except OSError:
            pass


def clip(text: str, max_chars: int = _MAX_CHARS) -> str:
    """Truncate long text with a note so the model knows it is partial."""
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n… ({len(text) - max_chars} more characters)"

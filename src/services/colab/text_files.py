"""UTF-8 text transfers for editable files on a Colab runtime."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

logger = logging.getLogger("colab_text_files")
MAX_EDITABLE_TEXT_BYTES = 512 * 1024


def _remove_temp(path: str) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove temporary text file %s", path, exc_info=True)


async def download_text_file(
    colab_service,
    remote_path: str,
    *,
    session_name: str,
    auth_method: str,
) -> str:
    """Download a bounded UTF-8 text file for editing."""
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as handle:
        local_path = handle.name
    try:
        downloaded = await colab_service.download(
            remote_path,
            local_path,
            session_name=session_name,
            auth_method=auth_method,
        )
        if not downloaded:
            raise OSError(f"Could not download {remote_path}")

        size = Path(local_path).stat().st_size
        if size > MAX_EDITABLE_TEXT_BYTES:
            raise ValueError(
                f"{remote_path} is too large to edit here "
                f"({size} bytes; limit {MAX_EDITABLE_TEXT_BYTES})."
            )
        return await asyncio.to_thread(Path(local_path).read_text, encoding="utf-8")
    finally:
        _remove_temp(local_path)


async def upload_text_file(
    colab_service,
    remote_path: str,
    text: str,
    *,
    session_name: str,
    auth_method: str,
) -> None:
    """Upload UTF-8 text to a remote Colab path."""
    size = len(text.encode("utf-8"))
    if size > MAX_EDITABLE_TEXT_BYTES:
        raise ValueError(
            f"{remote_path} is too large to save here "
            f"({size} bytes; limit {MAX_EDITABLE_TEXT_BYTES})."
        )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as handle:
        handle.write(text)
        local_path = handle.name
    try:
        uploaded = await colab_service.upload(
            local_path,
            remote_path,
            session_name=session_name,
            auth_method=auth_method,
        )
        if not uploaded:
            raise OSError(f"Could not save {remote_path}")
    finally:
        _remove_temp(local_path)

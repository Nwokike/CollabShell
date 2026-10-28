import asyncio
from pathlib import Path

import pytest

from screens.files.text_editor import is_python_file, open_text_file_editor
from services.colab.text_files import (
    MAX_EDITABLE_TEXT_BYTES,
    download_text_file,
    upload_text_file,
)


class FakeColab:
    def __init__(self, content: str):
        self.content = content
        self.uploaded = None

    async def download(self, remote_path, local_path, **kwargs):
        Path(local_path).write_text(self.content, encoding="utf-8")
        return True

    async def upload(self, local_path, remote_path, **kwargs):
        self.uploaded = (remote_path, Path(local_path).read_text(encoding="utf-8"))
        return True


def test_download_text_file_reads_remote_utf8():
    colab = FakeColab("print('hello')\n")

    text = asyncio.run(
        download_text_file(
            colab,
            "/content/hello.py",
            session_name="session",
            auth_method="oauth2",
        )
    )

    assert text == "print('hello')\n"


def test_upload_text_file_writes_remote_utf8():
    colab = FakeColab("")

    asyncio.run(
        upload_text_file(
            colab,
            "/content/hello.py",
            "print('hello')\n",
            session_name="session",
            auth_method="oauth2",
        )
    )

    assert colab.uploaded == ("/content/hello.py", "print('hello')\n")


def test_upload_text_file_surfaces_failed_upload():
    class FailedUpload(FakeColab):
        async def upload(self, local_path, remote_path, **kwargs):
            return False

    with pytest.raises(OSError, match="Could not save"):
        asyncio.run(
            upload_text_file(
                FailedUpload(""),
                "/content/hello.py",
                "print('hello')",
                session_name="session",
                auth_method="oauth2",
            )
        )


def test_upload_text_file_rejects_text_over_edit_limit():
    with pytest.raises(ValueError, match="too large to save"):
        asyncio.run(
            upload_text_file(
                FakeColab(""),
                "/content/hello.py",
                "x" * (MAX_EDITABLE_TEXT_BYTES + 1),
                session_name="session",
                auth_method="oauth2",
            )
        )


@pytest.mark.parametrize(
    ("name", "expected"),
    [("main.py", True), ("MAIN.PY", True), ("main.ipynb", False), ("notes.txt", False)],
)
def test_python_file_detection(name, expected):
    assert is_python_file(name) is expected


def test_text_editor_dialog_uses_installed_flet_controls():
    class FakePage:
        dialog = None

        def show_dialog(self, dialog):
            self.dialog = dialog

    page = FakePage()
    asyncio.run(
        open_text_file_editor(
            page,
            FakeColab("print('hello')\n"),
            "session",
            "oauth2",
            "/content/hello.py",
        )
    )

    assert page.dialog is not None

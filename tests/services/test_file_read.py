"""file_read tests: the download-stage-read-cleanup cycle, and the cap.

The properties that matter:

* **The temp file is always unlinked**, including when the download raises —
  otherwise every explain leaves a file in the temp dir.
* **A failure reads as empty**, so a caller shows "could not be read" rather
  than crashing on an exception it did not expect.
* **Long text is clipped with a note**, so the model knows it is looking at a
  head and not a hallucination of the whole file.
"""

import asyncio
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from services import file_read


class _FakeColab:
    def __init__(self, ok=True, raises=None):
        self.ok = ok
        self.raises = raises
        self.downloads = []

    async def download(self, path, session_name=None, auth_method=None):
        self.downloads.append(path)
        if self.raises:
            raise self.raises
        return self.ok


def _call(colab, tmp_path, monkeypatch, path="/content/x.csv"):
    """Run read_file_text with the staged temp file redirected into tmp_path."""
    made = []

    real_mkstemp = file_read.tempfile.mkstemp

    def fake_mkstemp(**kw):

        fd, name = real_mkstemp(dir=str(tmp_path), **kw)
        made.append(name)
        if colab.ok and not colab.raises:
            with open(name, "w", encoding="utf-8") as fh:
                fh.write("id,v\n1,2\n")
        return fd, name

    monkeypatch.setattr(file_read.tempfile, "mkstemp", fake_mkstemp)
    try:
        return asyncio.run(
            file_read.read_file_text(
                path,
                colab_service=colab,
                session_name="sess",
                auth_method="oauth2",
            )
        ), made
    finally:

        for name in made:
            Path(name).unlink(missing_ok=True)


# ── the read ────────────────────────────────────────────────────────────────


def test_reads_the_staged_file(tmp_path, monkeypatch):
    text, made = _call(_FakeColab(ok=True), tmp_path, monkeypatch)
    assert text.startswith("id,v"), text
    assert made, "a temp file must have been staged"


def test_a_failed_download_reads_as_empty(tmp_path, monkeypatch):
    text, _made = _call(_FakeColab(ok=False), tmp_path, monkeypatch)
    assert text == ""


def test_a_raising_download_reads_as_empty(tmp_path, monkeypatch):
    """A download that throws is still a not-read, not a crash at the caller."""
    text, _ = _call(_FakeColab(raises=RuntimeError("boom")), tmp_path, monkeypatch)
    assert text == ""


# ── the temp file ───────────────────────────────────────────────────────────


def test_the_temp_file_is_unlinked_on_success(tmp_path, monkeypatch):
    created = []
    real = file_read.tempfile.mkstemp

    def spy(**kw):

        fd, name = real(dir=str(tmp_path), **kw)
        created.append(name)
        return fd, name

    monkeypatch.setattr(file_read.tempfile, "mkstemp", spy)
    asyncio.run(
        file_read.read_file_text(
            "/content/x", colab_service=_FakeColab(ok=False),
            session_name="s", auth_method="oauth2",
        )
    )
    assert created, "a temp file should have been made"
    for name in created:
        assert not Path(name).exists(), "the staged temp file must be cleaned up"


def test_the_temp_file_is_unlinked_when_the_download_raises(tmp_path, monkeypatch):
    created = []
    real = file_read.tempfile.mkstemp

    def spy(**kw):

        fd, name = real(dir=str(tmp_path), **kw)
        created.append(name)
        return fd, name

    monkeypatch.setattr(file_read.tempfile, "mkstemp", spy)
    asyncio.run(
        file_read.read_file_text(
            "/content/x", colab_service=_FakeColab(raises=ValueError("x")),
            session_name="s", auth_method="oauth2",
        )
    )
    for name in created:
        assert not Path(name).exists(), "a failure must not leak the temp file"


# ── the cap ─────────────────────────────────────────────────────────────────


def test_clip_truncates_and_says_how_much_was_lost():
    out = file_read.clip("x" * 100, max_chars=10)
    assert out.startswith("x" * 10)
    assert "90 more characters" in out


def test_clip_passes_short_text_through_unchanged():
    assert file_read.clip("hello", max_chars=10) == "hello"


def test_clip_of_empty_is_empty():
    assert file_read.clip("") == ""

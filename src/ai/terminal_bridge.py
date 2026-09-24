"""The Assistant's handle on the terminal that is on screen.

`TerminalPanel` owns the PTY and its WebSocket, so it builds one of
these per mount. Two things matter here:

* the user watches the command run in their own terminal — the bridge
  types into the same PTY they are looking at, it does not shell out
  behind their back;
* the Assistant still needs the result, so each command is followed by
  a unique sentinel that prints its exit code. The bridge waits for that
  sentinel instead of guessing when the command finished, which is what
  a naive sleep-then-read would get wrong on a long `pip install`.
"""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from collections.abc import Callable

# ANSI colour/cursor sequences: the terminal is for humans, the model wants
# the text. Stripped on every read so a traceback is not full of escape codes.
_ANSI = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_BACKSPACE = re.compile(r".\x08")

# How much of the scrollback the model sees in one read.
READ_CHARS = 6000
DEFAULT_TIMEOUT = 120.0
POLL_SECONDS = 0.1


def clean(text: str) -> str:
    """Terminal bytes as plain text."""
    return _BACKSPACE.sub("", _ANSI.sub("", text or "")).replace("\r\n", "\n").strip()


class TerminalBridge:
    """Read the active terminal and run commands in it.

    Args:
        session_name: the Colab session behind this terminal.
        active_entry: () -> the active TerminalEntry, or None.
        alive: () -> bool, false once the panel is gone.
    """

    def __init__(
        self,
        session_name: str,
        active_entry: Callable[[], object],
        alive: Callable[[], bool] | None = None,
    ):
        self.session_name = session_name
        self._active_entry = active_entry
        self._alive = alive or (lambda: True)

    def is_alive(self) -> bool:
        return self._alive() and self._entry() is not None

    def _entry(self):
        try:
            return self._active_entry()
        except Exception:
            return None

    def output(self, chars: int = READ_CHARS) -> str:
        entry = self._entry()
        if entry is None:
            return "No terminal is open right now."
        raw = b"".join(list(getattr(entry, "scrollback", []) or [])[-400:])
        text = clean(raw.decode("utf-8", errors="replace"))
        if not text:
            return "The terminal is empty — nothing has run yet."
        if len(text) > chars:
            text = "… (earlier output trimmed)\n" + text[-chars:]
        return text

    async def run(self, command: str, timeout: float = DEFAULT_TIMEOUT) -> str:
        """Type a command into the terminal and wait for it to finish.

        Returns the command's own output plus its exit code. On timeout
        the partial output comes back with a warning instead of a guess —
        a long build is still running, and saying so is more useful than
        reporting a wrong answer.
        """
        entry = self._entry()
        if entry is None or not getattr(entry, "ready", False):
            return "The terminal is not connected."

        marker = f"__COLLAB_AI_{uuid.uuid4().hex[:10]}__"
        entry.capture = []
        try:
            await entry.client.send_input(
                f"{command}\nprintf '\\n{marker}%s\\n' \"$?\"\n".encode()
            )
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                await asyncio.sleep(POLL_SECONDS)
                blob = b"".join(entry.capture or []).decode("utf-8", errors="replace")
                if marker not in blob:
                    continue
                head, _, tail = blob.partition(marker)
                code = tail.strip().splitlines()[0].strip() if tail.strip() else "?"
                body = clean(head)
                # Drop the echoed command line so the model sees results,
                # not its own request typed back at it.
                lines = body.splitlines()
                if lines and command.strip()[:40] in lines[0]:
                    lines = lines[1:]
                body = "\n".join(lines).strip()
                status = "succeeded" if code == "0" else f"failed (exit {code})"
                return f"`{command}` {status}.\n\n{body or '(no output)'}"
            partial = clean(
                b"".join(entry.capture or []).decode("utf-8", errors="replace")
            )
            return (
                f"`{command}` did not finish within {int(timeout)}s and may still "
                f"be running.\n\n{partial or '(no output yet)'}"
            )
        finally:
            entry.capture = None


__all__ = ["TerminalBridge", "clean"]

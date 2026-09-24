"""Phase 4 — the Assistant working in the terminal that is on screen.

The interesting part is not the catalog, it is the command protocol: the
bridge types a command, then a unique sentinel that prints the exit
code, and waits for that sentinel rather than guessing when the command
finished. A sleep-then-read would report the wrong thing on a long
`pip install`, and a missing sentinel would mean it is still running.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ai.session import AiSession
from ai.system_prompt import build_system_prompt
from ai.terminal_bridge import TerminalBridge, clean
from ai.terminal_sheet import build_question as terminal_question
from ai.tools import (
    AUTO,
    CONFIRM,
    NOTEBOOK_SCHEMAS,
    TERMINAL_SCHEMAS,
    TERMINAL_TIERS,
    TOOL_SCHEMAS,
    ToolBox,
    label_for,
    schemas_for,
)


class FakeClient:
    """Records what was typed and replays a scripted reply."""

    def __init__(self, reply: str = "", ready: bool = True):
        self.sent: list[bytes] = []
        self.reply = reply
        self.entry = None

    async def send_input(self, data):
        self.sent.append(data if isinstance(data, bytes) else str(data).encode())


class FakeEntry:
    def __init__(self, client=None, scrollback=None):
        self.client = client
        self.ready = client is not None
        self.scrollback = list(scrollback or [])
        self.capture = None
        if client is not None:
            # The real client writes into the entry's buffers, so the fakes
            # need the same back-reference to simulate a reply.
            client.entry = self


class FakeTerminal:
    def __init__(self, entry=None):
        self.entry = entry
        self.alive = True

    def bridge(self) -> TerminalBridge:
        return TerminalBridge("work", lambda: self.entry, alive=lambda: self.alive)


def _echo(text: str, code: str = "0") -> str:
    """What a real PTY would send back, sentinel included."""
    client = FakeClient()

    async def send(data):
        client.sent.append(data)
        marker = data.decode().split("printf '")[1].split("%s")[0][2:]
        client.entry.capture = client.entry.capture or []
        client.entry.capture.append(
            f"$ {data.decode().splitlines()[0]}\r\n{text}\r\n\r\n{marker}{code}\r\n$ ".encode()
        )

    client.send_input = send
    return client


# ── Catalog ────────────────────────────────────────────────────────────


def test_terminal_tools_appear_only_with_a_terminal():
    bare = {s["function"]["name"] for s in schemas_for(False)}
    with_terminal = {s["function"]["name"] for s in schemas_for(False, True)}
    assert bare == {s["function"]["name"] for s in TOOL_SCHEMAS}
    assert "run_command" not in bare
    assert {"read_terminal", "run_command"} <= with_terminal
    assert len(with_terminal) == len(bare) + len(TERMINAL_SCHEMAS)


def test_notebook_and_terminal_tools_stack():
    both = {s["function"]["name"] for s in schemas_for(True, True)}
    assert "set_cell_source" in both and "run_command" in both
    assert len(both) == len(TOOL_SCHEMAS) + len(NOTEBOOK_SCHEMAS) + len(
        TERMINAL_SCHEMAS
    )


def test_reading_is_free_and_running_asks():
    assert TERMINAL_TIERS["read_terminal"] == AUTO
    assert TERMINAL_TIERS["run_command"] == CONFIRM
    for schema in TERMINAL_SCHEMAS:
        fn = schema["function"]
        assert fn["description"]
        assert set(fn["parameters"]["required"]) <= set(fn["parameters"]["properties"])


def test_run_command_label_shows_the_command():
    assert label_for("run_command", {"command": "pip install pandas"}) == (
        "Running: pip install pandas"
    )
    assert label_for("read_terminal", {}) == "Reading the terminal"


# ── Reading ────────────────────────────────────────────────────────────


def test_clean_strips_ansi_and_carriage_returns():
    raw = "\x1b[31mred\x1b[0m\r\nplain\r\n"
    assert clean(raw) == "red\nplain"


def test_output_returns_real_scrollback():
    entry = FakeEntry(scrollback=[b"before ", b"\x1b[32mok\x1b[0m\r\n"])
    bridge = FakeTerminal(entry).bridge()
    assert bridge.output() == "before ok"


def test_output_trims_from_the_front_when_long():
    entry = FakeEntry(scrollback=[("x" * 50_000).encode()])
    text = FakeTerminal(entry).bridge().output(chars=100)
    assert text.startswith("… (earlier output trimmed)")
    assert len(text) < 200


def test_an_empty_terminal_says_so():
    assert "empty" in FakeTerminal(FakeEntry()).bridge().output().lower()
    assert "No terminal" in FakeTerminal(None).bridge().output()


def test_a_dead_panel_disables_the_tools():
    fake = FakeTerminal(FakeEntry())
    bridge = fake.bridge()
    assert bridge.is_alive() is True
    fake.alive = False
    assert bridge.is_alive() is False
    box = ToolBox(None, terminal=bridge)
    assert box.has_terminal is False
    assert "No terminal" in asyncio.run(box.run("read_terminal", {})).text
    assert "No terminal" in asyncio.run(box.run("run_command", {"command": "ls"})).text


def test_a_disconnected_terminal_refuses_to_type():
    box = ToolBox(None, terminal=FakeTerminal(FakeEntry()).bridge())
    result = asyncio.run(box.run("run_command", {"command": "rm -rf /"}))
    assert "not connected" in result.text


# ── Running ────────────────────────────────────────────────────────────


def test_a_successful_command_returns_output_and_status():
    entry = FakeEntry(client=_echo("all good"))
    bridge = FakeTerminal(entry).bridge()
    result = asyncio.run(bridge.run("ls -la"))
    assert "succeeded" in result
    assert "all good" in result
    assert "ls -la" in result
    assert "`ls -la`" not in result.splitlines()[1]  # echo line was trimmed


def test_a_failing_command_reports_the_exit_code():
    entry = FakeEntry(client=_echo("No such file or directory", code="2"))
    result = asyncio.run(FakeTerminal(entry).bridge().run("cat missing.txt"))
    assert "failed (exit 2)" in result
    assert "No such file" in result


def test_the_command_is_typed_into_the_users_terminal():
    entry = FakeEntry(client=FakeClient())
    # This client never replies, so the short timeout is the point: we only
    # care about what got typed, not about the reply.
    asyncio.run(FakeTerminal(entry).bridge().run("pip install pandas", timeout=0.3))
    typed = b"".join(entry.client.sent).decode()
    assert typed.startswith("pip install pandas\n")
    # One command, then a sentinel that reports the exit code.
    assert typed.count("printf") == 1
    assert "__COLLAB_AI_" in typed


def test_capture_is_always_released():
    entry = FakeEntry(client=_echo("done"))
    asyncio.run(FakeTerminal(entry).bridge().run("true"))
    assert entry.capture is None, "a stuck capture would grow forever"

    slow = FakeEntry(client=FakeClient())
    result = asyncio.run(FakeTerminal(slow).bridge().run("sleep 100", timeout=0.3))
    assert slow.capture is None
    assert "may still" in result


def test_a_hanging_command_reports_partial_output_not_a_guess():
    client = FakeClient()

    async def trickle(data):
        client.sent.append(data)
        client.entry.capture = client.entry.capture or []
        client.entry.capture.append(b"downloading...\r\n")

    client.send_input = trickle
    entry = FakeEntry(client=client)
    result = asyncio.run(FakeTerminal(entry).bridge().run("wget big", timeout=0.3))
    assert "may still be running" in result
    assert "downloading" in result


def test_each_command_gets_a_fresh_sentinel():
    entry = FakeEntry(client=_echo("x"))
    bridge = FakeTerminal(entry).bridge()
    asyncio.run(bridge.run("first"))
    asyncio.run(bridge.run("second"))
    typed = b"".join(entry.client.sent).decode()
    markers = set(typed.split("__COLLAB_AI_")[1:])
    assert len(markers) == 2, "a reused marker would match stale output"


def test_empty_commands_are_refused_before_typing():
    entry = FakeEntry(client=FakeClient())
    box = ToolBox(None, terminal=FakeTerminal(entry).bridge())
    assert "No command" in asyncio.run(box.run("run_command", {"command": "  "})).text
    assert entry.client.sent == []


# ── Session wiring ─────────────────────────────────────────────────────


def test_session_sends_terminal_tools_only_while_attached():
    session = AiSession()
    session.router = None
    session._toolbox = ToolBox(None)
    assert session._tool_schemas() is not None
    assert "run_command" not in {s["function"]["name"] for s in session._tool_schemas()}

    session.attach_terminal(FakeTerminal(FakeEntry()).bridge())
    assert "run_command" in {s["function"]["name"] for s in session._tool_schemas()}
    prompt = session._context_messages()[0]["content"]
    assert "run_command" in prompt

    session.detach_terminal()
    assert "run_command" not in {s["function"]["name"] for s in session._tool_schemas()}
    assert "run_command" not in session._context_messages()[0]["content"]


def test_prompt_forbids_chained_commands():
    with_terminal = build_system_prompt(tools_available=True, terminal_available=True)
    assert "read_terminal" in with_terminal
    assert "one command at a time" in with_terminal
    assert "read_terminal" not in build_system_prompt(tools_available=True)


# ── The quick-ask sheet ────────────────────────────────────────────────


def test_terminal_questions_do_not_stale_the_output():
    # The model reads the live terminal; pasting a snapshot would be wrong.
    assert "Read the terminal" in terminal_question("explain")
    assert terminal_question("run") == "Run this in the terminal: "
    assert terminal_question("ask") == "About this terminal: "

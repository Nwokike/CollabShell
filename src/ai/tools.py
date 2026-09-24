"""The Assistant's tool catalog — what it can do inside Collab Shell.

Colab-only by design: the Assistant drives *this* app and its Colab
sessions, nothing else. Shape follows DDGS: the app owns execution, the
model only proposes. Every tool is declared with an OpenAI function
schema plus a safety tier:

- ``auto``     read-only, runs without asking (list sessions, list files)
- ``confirm``  proposes and waits for the user (create/stop a session, run
               code, install packages, mount Drive, authenticate GCP)

State-changing tools never execute on a model decision alone: the panel
shows the exact action and the user taps Allow. Every model call in the
loop — including each step after a tool result — costs one turn of
credits, so a multi-step request is charged per call.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("ai.tools")

AUTO = "auto"
CONFIRM = "confirm"


def _fn(
    name: str,
    description: str,
    properties: dict | None = None,
    required: list[str] | None = None,
) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
            },
        },
    }


# The catalog the model sees. Kept deliberately small: every extra tool is
# another way to burn a paid turn.
TOOL_SCHEMAS: list[dict] = [
    _fn(
        "list_sessions",
        "List the user's active Colab sessions (name, hardware, status).",
    ),
    _fn(
        "list_files",
        "List files on a session's VM at a path (default /content).",
        {
            "session": {"type": "string", "description": "Session name."},
            "path": {"type": "string", "description": "Absolute VM path."},
        },
        ["session"],
    ),
    _fn(
        "create_session",
        "Start a new Colab runtime. Uses the user's compute quota.",
        {
            "name": {"type": "string", "description": "Short session name."},
            "gpu": {"type": "string", "description": "T4, L4, G4, A100, or H100."},
            "tpu": {"type": "string", "description": "v5e1 or v6e1."},
            "high_mem": {"type": "boolean", "description": "Request a High-RAM shape."},
        },
    ),
    _fn(
        "stop_session",
        "Stop a session and release its compute. All work on it ends.",
        {"session": {"type": "string", "description": "Session name."}},
        ["session"],
    ),
    _fn(
        "run_code",
        "Run Python code on a session's kernel and return its output.",
        {
            "session": {"type": "string"},
            "code": {"type": "string", "description": "Python source to run."},
        },
        ["session", "code"],
    ),
    _fn(
        "install_packages",
        "Install pip packages on a session's VM.",
        {
            "session": {"type": "string"},
            "packages": {
                "type": "array",
                "items": {"type": "string"},
                "description": 'Package names, e.g. ["numpy", "pandas"].',
            },
        },
        ["session", "packages"],
    ),
    _fn(
        "mount_drive",
        "Mount the user's Google Drive into a session (needs their sign-in).",
        {
            "session": {"type": "string"},
            "path": {
                "type": "string",
                "description": "Mount point, default /content/drive.",
            },
        },
        ["session"],
    ),
    _fn(
        "auth_gcp",
        "Authenticate the user's Google Cloud account inside a session.",
        {"session": {"type": "string"}},
        ["session"],
    ),
]

TIERS: dict[str, str] = {
    "list_sessions": AUTO,
    "list_files": AUTO,
    "create_session": CONFIRM,
    "stop_session": CONFIRM,
    "run_code": CONFIRM,
    "install_packages": CONFIRM,
    "mount_drive": CONFIRM,
    "auth_gcp": CONFIRM,
}


def label_for(name: str, args: dict) -> str:
    """One user-legible line for the step timeline."""
    match name:
        case "list_sessions":
            return "Checking your sessions"
        case "list_files":
            return f"Listing {args.get('path') or '/content'}"
        case "create_session":
            hw = args.get("gpu") or args.get("tpu") or "CPU"
            mem = ", High-RAM" if args.get("high_mem") else ""
            return f"Creating a {hw}{mem} session"
        case "stop_session":
            return f"Stopping {args.get('session', '')}"
        case "run_code":
            return f"Running code on {args.get('session', '')}"
        case "install_packages":
            return f"Installing {', '.join(args.get('packages') or [])}"
        case "mount_drive":
            return f"Mounting Drive on {args.get('session', '')}"
        case "auth_gcp":
            return f"Authenticating GCP on {args.get('session', '')}"
    return name


class ToolResult:
    __slots__ = ("text",)

    def __init__(self, text: str):
        self.text = text


class ToolBox:
    """Executes catalog tools against the live Colab service."""

    def __init__(self, colab_service):
        self._colab = colab_service

    async def run(self, name: str, args: dict) -> ToolResult:
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return ToolResult(f"Unknown tool: {name}")
        try:
            return await asyncio.wait_for(handler(args), timeout=240)
        except TimeoutError:
            return ToolResult(f"{name} timed out after 4 minutes.")
        except Exception as e:
            logger.exception("Tool %s failed", name)
            return ToolResult(f"{name} failed: {e}")

    # ── auto: read-only ─────────────────────────────────────────────────

    async def _tool_list_sessions(self, args: dict) -> ToolResult:
        sessions = await self._colab.list_sessions() or []
        if not sessions:
            return ToolResult("No active sessions.")
        lines = [
            f"{s.get('name')} — {s.get('accelerator_label', s.get('accelerator'))} "
            f"({s.get('status', 'unknown')})"
            for s in sessions
        ]
        return ToolResult("Active sessions:\n" + "\n".join(lines))

    async def _tool_list_files(self, args: dict) -> ToolResult:
        path = args.get("path") or "/content"
        entries = await self._colab.ls(
            path=path, session_name=args["session"], auth_method="oauth2"
        )
        if not entries:
            return ToolResult(f"{path} is empty.")
        lines = [f"{e.get('name')}{'/' if e.get('is_dir') else ''}" for e in entries]
        return ToolResult(f"{path}:\n" + "\n".join(lines))

    # ── confirm: state-changing ──────────────────────────────────────────

    async def _tool_create_session(self, args: dict) -> ToolResult:
        session = await self._colab.new_session(
            name=args.get("name") or None,
            gpu=args.get("gpu") or None,
            tpu=args.get("tpu") or None,
            auth_method="oauth2",
            high_mem=bool(args.get("high_mem")),
        )
        return ToolResult(
            f"Session {session['name']} is ready "
            f"({session.get('accelerator')}, {session.get('machine_shape', 'STANDARD')})."
        )

    async def _tool_stop_session(self, args: dict) -> ToolResult:
        stopped = await self._colab.stop_session(args["session"], auth_method="oauth2")
        return ToolResult(
            f"Stopped {args['session']}."
            if stopped
            else f"Could not stop {args['session']}."
        )

    async def _tool_run_code(self, args: dict) -> ToolResult:
        outputs = await self._colab.exec_code(
            args["code"],
            args["session"],
            timeout=120,
            auth_method="oauth2",
        )
        text = "\n".join(
            o.get("text", "") for o in (outputs or []) if isinstance(o, dict)
        ).strip()
        return ToolResult(text or "Ran with no output.")

    async def _tool_install_packages(self, args: dict) -> ToolResult:
        ok = await self._colab.install_packages(
            args["packages"], args["session"], auth_method="oauth2"
        )
        return ToolResult(
            "Packages installed." if ok else "Installation reported a failure."
        )

    async def _tool_mount_drive(self, args: dict) -> ToolResult:
        ok = await self._colab.mount_drive(
            args["session"],
            path=args.get("path") or "/content/drive",
            auth_method="oauth2",
        )
        return ToolResult("Drive mounted." if ok else "Drive mount did not complete.")

    async def _tool_auth_gcp(self, args: dict) -> ToolResult:
        ok = await self._colab.auth_gcp_on_vm(args["session"], auth_method="oauth2")
        return ToolResult("GCP authenticated." if ok else "GCP auth did not complete.")

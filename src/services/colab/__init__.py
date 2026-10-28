import logging
import re
import threading
from collections.abc import Callable

logger = logging.getLogger("colab_service")


def _extract_term_name(ws_url: str) -> str | None:
    """Extract the PTY terminal name embedded in a Colab terminal WS URL."""
    m = re.search(r"/terminals/websocket/([^/?#]+)", ws_url)
    return m.group(1) if m else None


class ColabService:
    """Async wrapper around the colab_cli Python SDK."""

    def __init__(self):
        self._cli_available = False
        self._cli_state = None
        self._cancel_event = threading.Event()
        self.default_stdin_hook: Callable | None = None

    @property
    def is_available(self) -> bool:
        return self._cli_available

    async def init(self) -> bool:
        from services.colab.auth import init_impl

        return await init_impl(self)

    async def _ensure_online(self):
        from services.colab.auth import ensure_online_impl

        return await ensure_online_impl(self)

    async def get_auth_url(self) -> str:
        from services.colab.auth import get_auth_url_impl

        return await get_auth_url_impl(self)

    async def authenticate_oauth2(self, code: str) -> dict:
        from services.colab.auth import authenticate_oauth2_impl

        return await authenticate_oauth2_impl(self, code)

    async def check_auth(self) -> dict:
        from services.colab.auth import check_auth_impl

        return await check_auth_impl(self)

    async def clear_token(self) -> bool:
        from services.colab.auth import clear_token_impl

        return await clear_token_impl(self)

    async def new_session(
        self,
        name: str | None = None,
        gpu: str | None = None,
        tpu: str | None = None,
        auth_method: str = "oauth2",
        high_mem: bool = False,
    ) -> dict:
        from services.colab.session_ops import new_session_impl

        return await new_session_impl(self, name, gpu, tpu, auth_method, high_mem)

    async def list_sessions(self, auth_method: str = "oauth2") -> list:
        from services.colab.session_ops import list_sessions_impl

        return await list_sessions_impl(self, auth_method)

    async def refresh_session_token(
        self, session_name: str, auth_method: str = "oauth2"
    ) -> bool:
        from services.colab.session_ops import refresh_session_token_impl

        return await refresh_session_token_impl(self, session_name, auth_method)

    async def stop_session(
        self,
        session_name: str,
        auth_method: str = "oauth2",
        reason: str = "user_requested",
    ) -> bool:
        from services.colab.session_ops import stop_session_impl

        return await stop_session_impl(self, session_name, auth_method, reason)

    async def restart_kernel(
        self, session_name: str, auth_method: str = "oauth2"
    ) -> bool:
        from services.colab.session_ops import restart_kernel_impl

        return await restart_kernel_impl(self, session_name, auth_method)

    async def get_session_url(
        self, session_name: str, auth_method: str = "oauth2"
    ) -> str:
        from services.colab.session_ops import get_session_url_impl

        return await get_session_url_impl(self, session_name, auth_method)

    async def exec_code(
        self,
        code: str,
        session_name: str,
        timeout: float = 30.0,
        auth_method: str = "oauth2",
        on_output: Callable | None = None,
        intercept_oauth: bool = True,
        stdin_hook: Callable | None = None,
        env: dict | None = None,
    ) -> dict:
        from services.colab.execution import exec_code_impl

        return await exec_code_impl(
            self,
            code,
            session_name,
            timeout,
            auth_method,
            on_output,
            intercept_oauth,
            stdin_hook,
            env,
        )

    def create_terminal_ws_url(
        self, raw_url: str, token: str, term_name: str | None = None
    ) -> str:
        from services.colab.terminal_client import create_terminal_ws_url as _create

        return _create(raw_url, token, term_name)

    def get_terminal_client(
        self,
        raw_url: str,
        token: str,
        on_stdout: Callable[[str], None],
        on_status: Callable[[str, bool], None] | None = None,
        term_name: str | None = None,
        session_name: str | None = None,
    ):
        """Build a terminal client (creating a fresh PTY when no `term_name`).

        The raw URL/token are cached on the client so it can later re-attach to
        the same PTY after a dropped socket instead of minting a new shell.
        `session_name` additionally lets re-attach pick up a re-minted
        runtime-proxy token after the cached one expires.
        """
        from services.colab.terminal_client import (
            ColabTerminalClient,
            create_terminal_ws_url,
        )

        ws_url = create_terminal_ws_url(raw_url, token, term_name)
        parsed_term_name = term_name or _extract_term_name(ws_url)
        return ColabTerminalClient(
            ws_url,
            on_stdout,
            on_status,
            base_url=raw_url,
            token=token,
            term_name=parsed_term_name,
            session_name=session_name,
        )

    async def get_usage(
        self, auth_method: str = "oauth2", cached_fallback: dict | None = None
    ) -> dict | None:
        from services.colab.usage_ops import get_usage_impl

        return await get_usage_impl(self, auth_method, cached_fallback)

    async def ls(
        self,
        path: str = "content",
        session_name: str | None = None,
        auth_method: str = "oauth2",
    ) -> list:
        from services.colab.files_ops import ls_impl

        return await ls_impl(self, session_name, path, auth_method)

    async def upload(
        self,
        local_path: str,
        remote_path: str,
        session_name: str | None = None,
        auth_method: str = "oauth2",
    ) -> bool:
        from services.colab.files_ops import upload_impl

        return await upload_impl(
            self, session_name, local_path, remote_path, auth_method
        )

    async def download(
        self,
        remote_path: str,
        local_path: str,
        session_name: str | None = None,
        auth_method: str = "oauth2",
    ) -> bool:
        from services.colab.files_ops import download_impl

        return await download_impl(
            self, session_name, remote_path, local_path, auth_method
        )

    async def download_folder(
        self,
        remote_dir_path: str,
        local_zip_path: str,
        session_name: str | None = None,
        auth_method: str = "oauth2",
        on_status: Callable[[str], None] | None = None,
    ) -> bool:
        from services.colab.files_ops import download_folder_impl

        return await download_folder_impl(
            self, session_name, remote_dir_path, local_zip_path, auth_method, on_status
        )

    async def rm(
        self, path: str, session_name: str | None = None, auth_method: str = "oauth2"
    ) -> bool:
        from services.colab.files_ops import rm_impl

        return await rm_impl(self, session_name, path, auth_method)

    async def mount_drive(
        self,
        session_name: str,
        path: str = "/content/drive",
        auth_method: str = "oauth2",
        on_output: Callable | None = None,
        stdin_hook: Callable | None = None,
    ) -> bool:
        from services.colab.vm_ops import mount_drive_impl

        return await mount_drive_impl(
            self, session_name, path, auth_method, on_output, stdin_hook
        )

    async def install_packages(
        self,
        packages: list,
        session_name: str,
        auth_method: str = "oauth2",
        on_output: Callable | None = None,
    ) -> bool:
        from services.colab.vm_ops import install_packages_impl

        return await install_packages_impl(
            self, session_name, packages, auth_method, on_output
        )

    async def auth_gcp_on_vm(
        self,
        session_name: str,
        auth_method: str = "oauth2",
        on_output: Callable | None = None,
        stdin_hook: Callable | None = None,
    ) -> bool:
        from services.colab.vm_ops import auth_gcp_on_vm_impl

        return await auth_gcp_on_vm_impl(
            self, session_name, auth_method, on_output, stdin_hook
        )

    async def get_log(
        self,
        session_name: str,
        lines: int | None = None,
        event_type: str | None = None,
    ) -> list:
        from services.colab.logs import get_log_impl

        return await get_log_impl(self, session_name, lines, event_type)

    async def list_log_sessions(self) -> list:
        from services.colab.logs import list_log_sessions_impl

        return await list_log_sessions_impl(self)

    async def export_log(self, session_name: str, output_path: str) -> bool:
        from services.colab.logs import export_log_impl

        return await export_log_impl(self, session_name, output_path)

    def cancel(self):
        self._cancel_event.set()

    def _resolve_session(self, st) -> str:
        sessions = st.store.list()
        names = list(sessions.keys())
        if len(names) == 1:
            return names[0]
        elif len(names) == 0:
            raise ValueError("No active sessions. Create one first.")
        else:
            raise ValueError(
                f"Multiple sessions active. Specify one: {', '.join(names)}"
            )

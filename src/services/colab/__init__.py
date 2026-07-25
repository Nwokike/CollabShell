import asyncio
import logging
import threading
import time
from collections.abc import Callable

logger = logging.getLogger("colab_service")


class ColabService:
    """Async wrapper around the colab_cli Python SDK."""

    def __init__(self):
        self._cli_available = False
        self._cli_state = None
        self._cancel_event = threading.Event()
        self._keep_alive_tasks: dict[str, asyncio.Task] = {}
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
        keep_alive: bool = True,
    ) -> dict:
        from services.colab.session_ops import new_session_impl

        return await new_session_impl(self, name, gpu, tpu, auth_method, keep_alive)

    async def list_sessions(self, auth_method: str = "oauth2") -> list:
        from services.colab.session_ops import list_sessions_impl

        return await list_sessions_impl(self, auth_method)

    async def stop_session(
        self, session_name: str, auth_method: str = "oauth2"
    ) -> bool:
        from services.colab.session_ops import stop_session_impl

        return await stop_session_impl(self, session_name, auth_method)

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
        intercept_oauth: bool = False,
        stdin_hook: Callable | None = None,
    ) -> list:
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
        )

    def create_terminal_ws_url(self, raw_url: str, token: str) -> str:
        from services.colab.terminal_client import create_terminal_ws_url as _create

        return _create(raw_url, token)

    def get_terminal_client(
        self,
        ws_url: str,
        on_stdout: Callable[[str], None],
        on_status: Callable[[str, bool], None] | None = None,
    ):
        from services.colab.terminal_client import ColabTerminalClient

        return ColabTerminalClient(ws_url, on_stdout, on_status)

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

    def _start_in_process_keep_alive(
        self, session_name: str, endpoint: str, auth_method: str
    ):
        existing = self._keep_alive_tasks.get(session_name)
        if existing is not None and not existing.done():
            existing.cancel()

        task = asyncio.create_task(
            self._keep_alive_loop(session_name, endpoint, auth_method)
        )
        self._keep_alive_tasks[session_name] = task

    async def _keep_alive_loop(
        self, session_name: str, endpoint: str, auth_method: str
    ):
        from colab_cli.auth import AuthProvider
        from colab_cli.common import State

        provider = AuthProvider.ADC if auth_method == "adc" else AuthProvider.OAUTH2
        start = time.time()
        max_dur = 24 * 3600
        consecutive_4xx = 0

        while time.time() - start < max_dur:
            try:
                st = State()
                st.auth_provider = provider
                await asyncio.to_thread(st.client.keep_alive_assignment, endpoint)
                consecutive_4xx = 0
            except Exception as e:
                code = getattr(e, "response", None) and e.response.status_code
                if code is not None and 400 <= code < 500:
                    consecutive_4xx += 1
                    if consecutive_4xx >= 2:
                        break
            await asyncio.sleep(60)

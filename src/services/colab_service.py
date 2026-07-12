"""Wraps the colab_cli Python SDK with async methods for the Flet UI.

Direct import approach (like Sherlock imports sherlock_project) — no subprocess.
All blocking SDK calls are wrapped in asyncio.to_thread() for non-blocking UI.
"""

import asyncio
import json
import logging
import os
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class ColabService:
    """Async wrapper around the colab_cli Python SDK."""

    def __init__(self):
        self._cli_available = False
        self._cli_state = None
        self._cancel_event = threading.Event()
        # In-process keep-alive tasks for platforms that don't support subprocess
        # (Android).  Keyed by session name, cancelled when the session stops.
        self._keep_alive_tasks: dict[str, asyncio.Task] = {}

    # ── Availability ──────────────────────────────────────────────────────────

    @property
    def is_available(self) -> bool:
        return self._cli_available

    async def init(self) -> bool:
        """Initialize the colab_cli State singleton and check availability."""
        try:

            def _init():
                from colab_cli.common import State
                from colab_cli.auto_update import get_app_version

                self._cli_state = State()
                version = get_app_version()
                self._cli_available = True
                return version

            await asyncio.to_thread(_init)
            return True
        except Exception as e:
            logger.error("Failed to init colab_cli: %s", e)
            self._cli_available = False
            return False

    async def get_version(self) -> str:
        """Return the installed CLI version."""

        def _get():
            from colab_cli.auto_update import get_app_version

            return get_app_version()

        try:
            return await asyncio.to_thread(_get)
        except Exception:
            return "unknown"

    # ── Auth ──────────────────────────────────────────────────────────────────

    async def _ensure_online(self):
        """Raise ConnectionError if device is offline."""
        import socket
        import asyncio

        def _check():
            try:
                socket.setdefaulttimeout(2.0)
                socket.gethostbyname("oauth2.googleapis.com")
                return True
            except Exception:
                return False

        is_online = await asyncio.to_thread(_check)
        if not is_online:
            from core.constants import ERR_NETWORK

            raise ConnectionError(ERR_NETWORK)

    async def get_auth_url(self) -> str:
        """Generate the OAuth2 authorization URL for the user to visit."""

        def _get_url():
            from colab_cli.auth import (
                PUBLIC_SCOPES,
                REMOTE_REDIRECT_URI,
                TOKEN_CONFIG_PATH,
            )
            from importlib import resources
            from google_auth_oauthlib.flow import InstalledAppFlow

            # Load the bundled OAuth config
            config_resource = resources.files("colab_cli").joinpath("oauth_config.json")
            client_config = json.loads(config_resource.read_text())

            flow = InstalledAppFlow.from_client_config(client_config, PUBLIC_SCOPES)
            flow.redirect_uri = REMOTE_REDIRECT_URI
            auth_url, _ = flow.authorization_url(prompt="consent", token_usage="remote")

            # Persist code_verifier to file for retrieval during verification phase
            try:
                verifier_path = os.path.join(
                    os.path.dirname(TOKEN_CONFIG_PATH), "code_verifier.txt"
                )
                os.makedirs(os.path.dirname(verifier_path), exist_ok=True)
                with open(verifier_path, "w") as f:
                    f.write(flow.code_verifier)
            except Exception as e:
                logger.error("Failed to save OAuth2 code verifier: %s", e)

            return auth_url

        return await asyncio.to_thread(_get_url)

    async def authenticate_oauth2(self, code: str) -> dict:
        """Complete the OAuth2 flow with the authorization code.

        Returns {"success": bool, "email": str, "error": str}.
        """

        def _auth(code):
            from colab_cli.auth import (
                PUBLIC_SCOPES,
                REMOTE_REDIRECT_URI,
                TOKEN_CONFIG_PATH,
            )
            from importlib import resources
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request

            config_resource = resources.files("colab_cli").joinpath("oauth_config.json")
            client_config = json.loads(config_resource.read_text())

            flow = InstalledAppFlow.from_client_config(client_config, PUBLIC_SCOPES)
            flow.redirect_uri = REMOTE_REDIRECT_URI

            # Restore the code_verifier generated during authorization URL creation
            verifier_path = os.path.join(
                os.path.dirname(TOKEN_CONFIG_PATH), "code_verifier.txt"
            )
            fetch_kwargs = {"code": code}
            if os.path.exists(verifier_path):
                try:
                    with open(verifier_path, "r") as f:
                        verifier = f.read().strip()
                    if verifier:
                        flow.code_verifier = verifier
                        # Pass explicitly to fetch_token and session
                        fetch_kwargs["code_verifier"] = verifier
                        if hasattr(flow, "oauth2session"):
                            flow.oauth2session.code_verifier = verifier
                except Exception as e:
                    logger.error("Failed to load OAuth2 code verifier: %s", e)

            flow.fetch_token(**fetch_kwargs)
            creds = flow.credentials

            # Clean up the code_verifier file since authorization is complete
            if os.path.exists(verifier_path):
                try:
                    os.remove(verifier_path)
                except Exception:
                    pass

            # Save the token
            os.makedirs(os.path.dirname(TOKEN_CONFIG_PATH), exist_ok=True)
            with open(TOKEN_CONFIG_PATH, "w") as f:
                f.write(creds.to_json())

            # Get the user's email
            creds.refresh(Request())
            import urllib.request
            import urllib.parse

            qs = urllib.parse.urlencode({"access_token": creds.token})
            url = f"https://oauth2.googleapis.com/tokeninfo?{qs}"
            with urllib.request.urlopen(url, timeout=10) as resp:
                info = json.loads(resp.read().decode("utf-8"))

            return {
                "success": True,
                "email": info.get("email", ""),
                "error": "",
            }

        try:
            return await asyncio.to_thread(_auth, code)
        except Exception as e:
            return {"success": False, "email": "", "error": str(e)}

    async def check_auth(self) -> dict:
        """Check if current credentials are valid.

        Returns {"authenticated": bool, "email": str, "expires_in": str, "auth_method": str}.
        """

        def _check():
            from colab_cli.auth import TOKEN_CONFIG_PATH, get_credentials, AuthProvider
            import urllib.request
            import urllib.parse

            # Check if token file exists
            if not os.path.exists(TOKEN_CONFIG_PATH):
                return {
                    "authenticated": False,
                    "email": "",
                    "expires_in": "",
                    "auth_method": "oauth2",
                }

            try:
                sess = get_credentials(provider=AuthProvider.OAUTH2)
                creds = sess.credentials
                from google.auth.transport.requests import Request as _Req

                creds.refresh(_Req())

                token = creds.token
                if not token:
                    return {
                        "authenticated": False,
                        "email": "",
                        "expires_in": "",
                        "auth_method": "oauth2",
                    }

                qs = urllib.parse.urlencode({"access_token": token})
                url = f"https://oauth2.googleapis.com/tokeninfo?{qs}"
                with urllib.request.urlopen(url, timeout=10) as resp:
                    info = json.loads(resp.read().decode("utf-8"))

                email = info.get("email", "")
                expires_in = info.get("expires_in", "")
                try:
                    expires_min = int(expires_in) // 60
                    expires_str = f"{expires_min}m"
                except (TypeError, ValueError):
                    expires_str = str(expires_in)

                return {
                    "authenticated": True,
                    "email": email,
                    "expires_in": expires_str,
                    "auth_method": "oauth2",
                }
            except Exception as e:
                logger.warning("Auth check failed: %s", e)
                return {
                    "authenticated": False,
                    "email": "",
                    "expires_in": "",
                    "auth_method": "oauth2",
                }

        return await asyncio.to_thread(_check)

    async def clear_token(self) -> bool:
        """Delete the cached OAuth2 token."""

        def _clear():
            from colab_cli.auth import TOKEN_CONFIG_PATH

            if os.path.exists(TOKEN_CONFIG_PATH):
                os.remove(TOKEN_CONFIG_PATH)
                return True
            return False

        return await asyncio.to_thread(_clear)

    # ── Sessions ──────────────────────────────────────────────────────────────

    async def new_session(
        self,
        name: str = None,
        gpu: str = None,
        tpu: str = None,
        auth_method: str = "oauth2",
        keep_alive: bool = True,
    ) -> dict:
        """Create a new Colab session.

        Returns a dict with session info or raises an exception.
        """

        def _new():
            import uuid
            from colab_cli.auth import AuthProvider
            from colab_cli.common import State
            from colab_cli.client import Accelerator, Variant, ColabRequestError
            from colab_cli.state import SessionState
            from colab_cli.commands.session import spawn_keep_alive
            from colab_cli.utils import get_status_code

            provider = AuthProvider.ADC if auth_method == "adc" else AuthProvider.OAUTH2
            st = State()
            st.auth_provider = provider

            session_name = name or uuid.uuid4().hex[:6]
            variant = Variant.DEFAULT
            accelerator = Accelerator.NONE

            if tpu:
                variant = Variant.TPU
                accelerator = (
                    Accelerator.V5E1 if tpu.lower() == "v5e1" else Accelerator.V6E1
                )
            elif gpu:
                variant = Variant.GPU
                mapping = {
                    "a100": Accelerator.A100,
                    "h100": Accelerator.H100,
                    "l4": Accelerator.L4,
                    "t4": Accelerator.T4,
                    "g4": Accelerator.G4,
                }
                accelerator = mapping.get(gpu.lower(), Accelerator.T4)

            try:
                res = st.client.assign(
                    uuid.uuid4(), variant=variant, accelerator=accelerator
                )
            except ColabRequestError as e:
                if get_status_code(e) == 400 and accelerator != Accelerator.NONE:
                    raise ValueError(
                        f"Accelerator '{accelerator.value}' rejected. "
                        "You may not have quota. Try T4 (free) or CPU."
                    )
                raise

            from colab_cli.client import PostAssignmentResponse

            if isinstance(res, PostAssignmentResponse):
                token = res.runtime_proxy_info.token
                url = res.runtime_proxy_info.url
                endpoint = res.endpoint
            else:
                token = (
                    res.runtime_proxy_info.token
                    if hasattr(res, "runtime_proxy_info")
                    else getattr(res, "runtime_proxy_token", "")
                )
                url = (
                    res.runtime_proxy_info.url
                    if hasattr(res, "runtime_proxy_info")
                    else ""
                )
                endpoint = res.endpoint

            s = SessionState(
                name=session_name,
                token=token,
                url=url,
                endpoint=endpoint,
                variant=variant.value,
                accelerator=accelerator.value,
            )

            # Pre-flight keep-alive
            if keep_alive:
                try:
                    st.client.keep_alive_assignment(endpoint)
                except ColabRequestError:
                    pass  # Non-blocking: daemon will retry

                st.store.add(s)
                try:
                    s.keep_alive_pid = spawn_keep_alive(
                        endpoint,
                        session_name,
                        auth_provider=st.auth_provider,
                        config_path=st.config_path,
                    )
                except (PermissionError, OSError) as ex:
                    logger.warning(
                        "Could not spawn keep-alive background process (likely Android): %s",
                        ex,
                    )
                    s.keep_alive_pid = None
                st.store.add(s)
            else:
                st.store.add(s)
                s.keep_alive_pid = None
            st.history.log_event(
                session_name,
                "session_created",
                {
                    "endpoint": endpoint,
                    "variant": variant.value,
                    "accelerator": accelerator.value,
                },
            )

            return {
                "name": session_name,
                "endpoint": endpoint,
                "variant": variant.value,
                "accelerator": accelerator.value,
                "status": "READY",
                "keep_alive_subprocess": getattr(s, "keep_alive_pid", None) is not None,
            }

        result = await asyncio.to_thread(_new)

        # If keep-alive was requested but subprocess spawning failed (Android →
        # PermissionError/OSError caught above), start an in-process keep-alive
        # loop that calls keep_alive_assignment every 60s from the event loop.
        if keep_alive and not result.get("keep_alive_subprocess", False):
            self._start_in_process_keep_alive(
                result["name"], result["endpoint"], auth_method
            )

        return result

    async def list_sessions(self, auth_method: str = "oauth2") -> list:
        """List all active sessions. Returns list of session dicts."""
        await self._ensure_online()

        def _list():
            from colab_cli.auth import AuthProvider
            from colab_cli.common import State

            provider = AuthProvider.ADC if auth_method == "adc" else AuthProvider.OAUTH2
            st = State()
            st.auth_provider = provider

            local_sessions, assignments = st.sync_sessions()
            results = []
            name_by_ep = {s.endpoint: s.name for s in local_sessions.values()}

            for a in assignments:
                name = name_by_ep.get(a.endpoint, "Unknown")
                accel_label = (
                    "CPU" if a.accelerator.value == "NONE" else a.accelerator.value
                )
                status = "IDLE"
                running = None
                last_exec = None

                if name != "?" and name in local_sessions:
                    s = local_sessions[name]
                    if s.running:
                        status = f"BUSY ({s.running})"
                        running = s.running
                    if s.last_execution:
                        last_exec = {
                            "file": s.last_execution[0],
                            "cell": s.last_execution[1],
                            "time": s.last_execution[2],
                        }

                results.append(
                    {
                        "name": name,
                        "endpoint": a.endpoint,
                        "accelerator": a.accelerator.value,
                        "variant": a.variant.name,
                        "accelerator_label": accel_label,
                        "status": status,
                        "running": running,
                        "last_execution": last_exec,
                    }
                )

            return results

        try:
            return await asyncio.to_thread(_list)
        except Exception as e:
            logger.error("list_sessions failed: %s", e)
            return []

    async def stop_session(
        self, session_name: str, auth_method: str = "oauth2"
    ) -> bool:
        """Stop a session by name."""

        # Cancel any in-process keep-alive loop first
        task = self._keep_alive_tasks.pop(session_name, None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("keep-alive task for %s raised unexpected exception", session_name)

        def _stop():
            from colab_cli.auth import AuthProvider
            from colab_cli.common import State, kill_process
            from colab_cli.runtime import ColabRuntime

            provider = AuthProvider.ADC if auth_method == "adc" else AuthProvider.OAUTH2
            st = State()
            st.auth_provider = provider

            s = st.store.get(session_name)
            if not s:
                return False

            if getattr(s, "keep_alive_pid", None):
                kill_process(s.keep_alive_pid)

            try:
                runtime = ColabRuntime(s.url, s.token, kernel_id=s.kernel_id)
                runtime.stop(shutdown_kernel=True)
            except Exception:
                pass

            st.client.unassign(s.endpoint)
            st.store.remove(session_name)
            st.history.log_event(
                session_name, "session_terminated", {"reason": "user_requested"}
            )
            return True

        return await asyncio.to_thread(_stop)

    async def restart_kernel(
        self, session_name: str, auth_method: str = "oauth2"
    ) -> bool:
        """Restart a session's kernel."""
        await self._ensure_online()

        def _restart():
            from colab_cli.auth import AuthProvider
            from colab_cli.common import State
            from colab_cli.runtime import ColabRuntime

            provider = AuthProvider.ADC if auth_method == "adc" else AuthProvider.OAUTH2
            st = State()
            st.auth_provider = provider

            s = st.store.get(session_name)
            if not s:
                return False

            def on_started(kid):
                s.kernel_id = kid
                st.store.add(s)

            def on_sess(sid):
                s.session_id = sid
                st.store.add(s)

            runtime = ColabRuntime(
                s.url,
                s.token,
                kernel_id=s.kernel_id,
                session_id=s.session_id,
                on_kernel_started=on_started,
                on_session_started=on_sess,
            )
            try:
                runtime.restart()
            finally:
                runtime.stop()
            return True

        return await asyncio.to_thread(_restart)

    # ── Execution ─────────────────────────────────────────────────────────────

    async def exec_code(
        self,
        code: str,
        session_name: str,
        timeout: float = 30.0,
        auth_method: str = "oauth2",
        on_output: Optional[Callable] = None,
        intercept_oauth: bool = False,
        stdin_hook: Optional[Callable] = None,
    ) -> list:
        """Execute Python code in a session. Returns list of outputs."""
        self._cancel_event.clear()

        def _exec():
            import datetime
            from colab_cli.auth import AuthProvider
            from colab_cli.common import State
            from colab_cli.runtime import ColabRuntime

            if self._cancel_event.is_set():
                self._cancel_event.clear()
                raise RuntimeError("Execution cancelled by user")

            provider = AuthProvider.ADC if auth_method == "adc" else AuthProvider.OAUTH2
            st = State()
            st.auth_provider = provider
            s = st.store.get(session_name)
            if not s:
                raise ValueError(f"Session '{session_name}' not found")

            def on_started(kid):
                s.kernel_id = kid
                st.store.add(s)

            def on_sess(sid):
                s.session_id = sid
                st.store.add(s)

            runtime = ColabRuntime(
                s.url,
                s.token,
                kernel_id=s.kernel_id,
                session_id=s.session_id,
                on_kernel_started=on_started,
                on_session_started=on_sess,
            )

            # Set working directory
            try:
                runtime.execute_code(
                    "import os; os.makedirs('/content', exist_ok=True); os.chdir('/content')"
                )
            except Exception as e:
                from colab_cli.utils import is_terminal_error

                if is_terminal_error(e):
                    st.prune_session(session_name)
                    raise ValueError("Session lost (404/401). It may have timed out.")
                raise

            s.running = "exec(code)"
            s.last_execution = (
                "code",
                None,
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
            st.store.add(s)

            def output_hook(out):
                if self._cancel_event.is_set():
                    self._cancel_event.clear()
                    try:
                        runtime.kernel_client.interrupt()
                    except Exception:
                        pass
                    raise RuntimeError("Execution cancelled by user")
                if on_output:
                    text = ""
                    if out.get("output_type") == "stream":
                        text = out.get("text", "")
                    elif "data" in out:
                        data = out["data"]
                        text = data.get("text/plain", "")
                    elif out.get("output_type") == "error":
                        tb = out.get("traceback", [])
                        if tb:
                            # Preserve ANSI codes — the parser renders colored tracebacks
                            text = "\n".join(tb)
                        else:
                            text = (
                                f"{out.get('ename', 'Error')}: {out.get('evalue', '')}"
                            )
                    if text:
                        on_output(text)

            if intercept_oauth:
                import json
                from colab_cli.auth import get_credentials
                from colab_cli.utils import get_status_code

                def drivefs_hook(deserialize_msg, wsclient):
                    content = deserialize_msg.get("content", {})
                    if content.get("request", {}).get("authType") == "dfs_ephemeral":
                        msg_id = deserialize_msg.get("metadata", {}).get("colab_msg_id")
                        if on_output:
                            on_output("Intercepted Drive Auth Request. Authorizing...")

                        url = f"{st.client.colab_domain}/tun/m/credentials-propagation/{s.endpoint}"
                        params = {
                            "authuser": "0",
                            "authtype": "dfs_ephemeral",
                            "version": "2",
                            "dryrun": "true",
                            "propagate": "true",
                            "record": "false",
                        }
                        creds = get_credentials(
                            st.client_oauth_config, provider=st.auth_provider
                        )
                        resp = creds.request("GET", url, params=params)
                        token = (
                            json.loads(resp.text.split("\n", 1)[-1]).get("token")
                            if get_status_code(resp) == 200
                            else None
                        )
                        headers = {"x-goog-colab-token": token}
                        resp = creds.request(
                            "POST",
                            url,
                            params=params,
                            headers=headers,
                            files={"file_id": (None, "empty.ipynb")},
                        )
                        data = json.loads(resp.text.split("\n", 1)[-1])

                        if not data.get("success"):
                            uri = data.get("unauthorized_redirect_uri")
                            if on_output:
                                on_output(
                                    f"\nERROR: Google Authorization needed.\nPlease visit: {uri}\nGrant access, then try again."
                                )
                            raise ValueError(f"Authorization needed: {uri}")

                        params["dryrun"] = "false"
                        resp = creds.request(
                            "POST",
                            url,
                            params=params,
                            headers=headers,
                            files={"file_id": (None, "empty.ipynb")},
                        )
                        if get_status_code(resp) == 200:
                            if on_output:
                                on_output("Credentials propagated successfully.")
                            reply = wsclient.session.msg(
                                "input_reply",
                                {
                                    "value": {
                                        "type": "colab_reply",
                                        "colab_msg_id": msg_id,
                                    }
                                },
                            )
                            if "header" in deserialize_msg:
                                reply["parent_header"] = deserialize_msg["header"]
                            wsclient.stdin_channel.send(reply)
                        else:
                            if on_output:
                                on_output(
                                    f"Error propagating: {get_status_code(resp)} {resp.text}"
                                )
                        return True
                    return False

                runtime.colab_request_hook = drivefs_hook

            try:
                outputs = runtime.execute_code(
                    code,
                    output_hook=output_hook if on_output else None,
                    timeout=timeout,
                    allow_stdin=intercept_oauth or (stdin_hook is not None),
                    stdin_hook=stdin_hook,
                )
                st.history.log_event(
                    session_name,
                    "execution",
                    {
                        "code": code,
                        "outputs": outputs,
                    },
                )
                return outputs
            finally:
                s.running = None
                st.store.add(s)
                runtime.stop()

        return await asyncio.to_thread(_exec)

    # ── Files ─────────────────────────────────────────────────────────────────

    async def ls(
        self,
        path: str = "content",
        session_name: str = None,
        auth_method: str = "oauth2",
    ) -> list:
        """List files at a remote path. Returns list of file dicts."""
        await self._ensure_online()

        def _ls():
            from colab_cli.auth import AuthProvider
            from colab_cli.common import State
            from colab_cli.contents import ContentsClient

            provider = AuthProvider.ADC if auth_method == "adc" else AuthProvider.OAUTH2
            st = State()
            st.auth_provider = provider
            name = session_name or self._resolve_session(st)
            s = st.store.get(name)
            if not s:
                raise ValueError(f"Session '{name}' not found")

            client = ContentsClient(s)
            data = client.list_dir(path)
            st.history.log_event(name, "file_operation", {"op": "ls", "path": path})

            if data.get("type") == "directory":
                items = data.get("content", [])
                return sorted(
                    [
                        {
                            "name": i.get("name"),
                            "type": i.get("type"),
                            "size": i.get("size", 0),
                        }
                        for i in items
                    ],
                    key=lambda x: (x["type"] != "directory", x["name"]),
                )
            return [
                {
                    "name": data.get("name"),
                    "type": data.get("type"),
                    "size": data.get("size", 0),
                }
            ]

        return await asyncio.to_thread(_ls)

    async def upload(
        self,
        local_path: str,
        remote_path: str,
        session_name: str = None,
        auth_method: str = "oauth2",
    ) -> bool:
        """Upload a local file to the remote session."""

        def _upload():
            from colab_cli.auth import AuthProvider
            from colab_cli.common import State
            from colab_cli.contents import ContentsClient

            provider = AuthProvider.ADC if auth_method == "adc" else AuthProvider.OAUTH2
            st = State()
            st.auth_provider = provider
            name = session_name or self._resolve_session(st)
            s = st.store.get(name)
            if not s:
                raise ValueError(f"Session '{name}' not found")

            client = ContentsClient(s)
            client.upload(local_path, remote_path)
            st.history.log_event(
                name,
                "file_operation",
                {
                    "op": "upload",
                    "local": local_path,
                    "remote": remote_path,
                },
            )
            return True

        return await asyncio.to_thread(_upload)

    async def download(
        self,
        remote_path: str,
        local_path: str,
        session_name: str = None,
        auth_method: str = "oauth2",
    ) -> bool:
        """Download a remote file to a local path."""
        await self._ensure_online()

        def _download():
            from colab_cli.auth import AuthProvider
            from colab_cli.common import State
            from colab_cli.contents import ContentsClient

            provider = AuthProvider.ADC if auth_method == "adc" else AuthProvider.OAUTH2
            st = State()
            st.auth_provider = provider
            name = session_name or self._resolve_session(st)
            s = st.store.get(name)
            if not s:
                raise ValueError(f"Session '{name}' not found")

            client = ContentsClient(s)
            client.download(remote_path, local_path)
            st.history.log_event(
                name,
                "file_operation",
                {
                    "op": "download",
                    "remote": remote_path,
                    "local": local_path,
                },
            )
            return True

        return await asyncio.to_thread(_download)

    async def rm(
        self, path: str, session_name: str = None, auth_method: str = "oauth2"
    ) -> bool:
        """Delete a remote file."""

        def _rm():
            from colab_cli.auth import AuthProvider
            from colab_cli.common import State
            from colab_cli.contents import ContentsClient

            provider = AuthProvider.ADC if auth_method == "adc" else AuthProvider.OAUTH2
            st = State()
            st.auth_provider = provider
            name = session_name or self._resolve_session(st)
            s = st.store.get(name)
            if not s:
                raise ValueError(f"Session '{name}' not found")

            client = ContentsClient(s)
            client.rm(path)
            st.history.log_event(name, "file_operation", {"op": "rm", "path": path})
            return True

        return await asyncio.to_thread(_rm)

    # ── Automation ────────────────────────────────────────────────────────────

    async def mount_drive(
        self,
        session_name: str,
        path: str = "/content/drive",
        auth_method: str = "oauth2",
        on_output: Optional[Callable] = None,
    ) -> bool:
        """Mount Google Drive at the given path."""
        code = f"from google.colab import drive\ndrive.mount('{path}')"
        try:
            await self.exec_code(
                code,
                session_name,
                timeout=600,
                auth_method=auth_method,
                on_output=on_output,
                intercept_oauth=True,
            )
            return True
        except Exception as e:
            logger.error("mount_drive failed: %s", e)
            return False

    async def install_packages(
        self,
        packages: list,
        session_name: str,
        auth_method: str = "oauth2",
        on_output: Optional[Callable] = None,
    ) -> bool:
        """Install Python packages on the VM."""
        " ".join(packages)
        code = f"""
import subprocess, sys
try:
    subprocess.check_call(['uv', 'pip', 'install', '--system'] + {repr(packages)})
    print('Installation Complete (via uv)!')
except:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install'] + {repr(packages)})
    print('Installation Complete (via pip)!')
"""
        try:
            await self.exec_code(
                code,
                session_name,
                timeout=300,
                auth_method=auth_method,
                on_output=on_output,
            )
            return True
        except Exception as e:
            logger.error("install_packages failed: %s", e)
            return False

    async def auth_gcp_on_vm(
        self,
        session_name: str,
        auth_method: str = "oauth2",
        on_output: Optional[Callable] = None,
    ) -> bool:
        """Authenticate GCP on the VM."""
        await self._ensure_online()
        code = "import os\nos.environ['USE_AUTH_EPHEM'] = '0'\nfrom google.colab import auth\nauth.authenticate_user()"
        try:
            await self.exec_code(
                code,
                session_name,
                timeout=600,
                auth_method=auth_method,
                on_output=on_output,
                intercept_oauth=True,
            )
            return True
        except Exception as e:
            logger.error("auth_gcp_on_vm failed: %s", e)
            return False

    # ── Utility ───────────────────────────────────────────────────────────────

    async def get_session_url(
        self, session_name: str, auth_method: str = "oauth2"
    ) -> str:
        """Get the browser URL for a session."""

        def _url():
            from urllib.parse import quote
            from colab_cli.auth import AuthProvider
            from colab_cli.common import State

            provider = AuthProvider.ADC if auth_method == "adc" else AuthProvider.OAUTH2
            st = State()
            st.auth_provider = provider
            s = st.store.get(session_name)
            if not s:
                raise ValueError(f"Session '{session_name}' not found")

            host = "https://colab.research.google.com"
            backend_path = f"/tun/m/{s.endpoint}"
            dbu_value = quote(backend_path, safe="")
            fragment_value = f"{host}{backend_path}"
            return f"{host}/notebooks/empty.ipynb?dbu={dbu_value}#datalabBackendUrl={fragment_value}"

        return await asyncio.to_thread(_url)

    async def get_log(
        self,
        session_name: str,
        lines: int = None,
        event_type: str = None,
    ) -> list:
        """Get session history logs."""

        def _log():
            from colab_cli.history import HistoryLogger

            h = HistoryLogger()
            events = h.get_history(session_name)
            if event_type:
                events = [e for e in events if e.get("event_type") == event_type]
            if lines:
                events = events[-lines:]
            return events

        return await asyncio.to_thread(_log)

    async def list_log_sessions(self) -> list:
        """List session names that have history logs."""

        def _list():
            from colab_cli.history import HistoryLogger

            h = HistoryLogger()
            return h.list_sessions()

        return await asyncio.to_thread(_list)

    async def export_log(self, session_name: str, output_path: str) -> bool:
        """Export session history to a file."""

        def _export():
            from colab_cli.history import HistoryLogger
            from colab_cli.converter import export_history

            h = HistoryLogger()
            events = h.get_history(session_name)
            if not events:
                return False
            export_history(events, session_name, output_path)
            return True

        return await asyncio.to_thread(_export)

    async def get_cli_version(self) -> str:
        """Return the installed google-colab-cli version."""
        try:
            from colab_cli.auto_update import get_app_version

            return await asyncio.to_thread(get_app_version)
        except Exception:
            return "unknown"

    # ── Cancel ────────────────────────────────────────────────────────────────

    def cancel(self):
        """Signal cancellation to any running operation."""
        self._cancel_event.set()

    def _resolve_session(self, st) -> str:
        """Resolve to the single active session name."""
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

    # ── In-process keep-alive (Android alternative to subprocess) ──────────

    def _start_in_process_keep_alive(
        self, session_name: str, endpoint: str, auth_method: str
    ):
        """Start an asyncio task that pings the keep-alive endpoint every 60s.

        Replaces ``spawn_keep_alive`` which fails on Android (subprocess not
        available).  The task runs for at most 24 hours and exits early on
        consecutive 4xx errors (session gone).
        """
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
        """Periodic keep-alive ping (60 s interval, max 24 h)."""
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
                code = (
                    getattr(e, "response", None) and e.response.status_code
                )
                if code is not None and 400 <= code < 500:
                    consecutive_4xx += 1
                    if consecutive_4xx >= 2:
                        break
                # Network blips are non-fatal — just retry next cycle
            await asyncio.sleep(60)

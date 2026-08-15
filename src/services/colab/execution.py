import asyncio
import datetime
import logging
import threading
import time
from collections.abc import Callable

logger = logging.getLogger("colab_execution")

_oauth_verifying_lock = threading.Lock()
_verified_oauth_endpoints = set()


async def exec_code_impl(
    service,
    code: str,
    session_name: str,
    timeout: float = 60.0,
    auth_method: str = "oauth2",
    on_output: Callable | None = None,
    intercept_oauth: bool = True,
    stdin_hook: Callable | None = None,
) -> dict:
    """Execute Python code in a session."""
    await service._ensure_online()
    service._cancel_event.clear()

    def _exec():
        from colab_cli.auth import AuthProvider
        from colab_cli.common import State
        from colab_cli.runtime import ColabRuntime

        if service._cancel_event.is_set():
            service._cancel_event.clear()
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
            datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )
        st.store.add(s)

        def output_hook(out):
            if service._cancel_event.is_set():
                service._cancel_event.clear()
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
                        text = "\n".join(tb)
                    else:
                        text = f"{out.get('ename', 'Error')}: {out.get('evalue', '')}"
                if text:
                    on_output(text)

        if intercept_oauth:
            import json

            from colab_cli.auth import get_credentials
            from colab_cli.utils import get_status_code

            def drivefs_hook(deserialize_msg, wsclient):
                content = deserialize_msg.get("content", {})
                if content.get("request", {}).get("authType") == "dfs_ephemeral":
                    with _oauth_verifying_lock:
                        if s.endpoint in _verified_oauth_endpoints:
                            return True
                        msg_id = deserialize_msg.get("metadata", {}).get("colab_msg_id")
                        if on_output:
                            on_output("Intercepted Drive Auth Request. Checking...")

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
                            if active_stdin_hook:
                                if on_output:
                                    on_output(
                                        "\nAuthorization required. Please authorize in browser using dialog link."
                                    )

                                def _on_oauth_done(success, message=None):
                                    pass

                                prompt_text = (
                                    f"Google Drive Authorization Required\n\n"
                                    f"Please click 'Open Link in Browser' below and grant access to your Google Drive.\n\n"
                                    f"After granting access, return here and click Submit.\n\n{uri}"
                                )
                                try:
                                    active_stdin_hook(
                                        prompt_text, on_complete=_on_oauth_done
                                    )
                                except TypeError:
                                    active_stdin_hook(prompt_text)

                                for _retry in range(10):
                                    resp_get = creds.request("GET", url, params=params)
                                    if get_status_code(resp_get) == 200:
                                        fresh_token = json.loads(
                                            resp_get.text.split("\n", 1)[-1]
                                        ).get("token")
                                        if fresh_token:
                                            headers["x-goog-colab-token"] = fresh_token
                                    resp = creds.request(
                                        "POST",
                                        url,
                                        params=params,
                                        headers=headers,
                                        files={"file_id": (None, "empty.ipynb")},
                                    )
                                    data = json.loads(resp.text.split("\n", 1)[-1])
                                    if data.get("success"):
                                        break
                                    time.sleep(2.0)

                            if not data.get("success"):
                                uri = data.get("unauthorized_redirect_uri")
                                if on_output:
                                    on_output(
                                        f"\nERROR: Google Authorization needed.\nPlease visit: {uri}\nGrant access, then try again."
                                    )
                                raise ValueError(f"Authorization needed: {uri}")

                        _verified_oauth_endpoints.add(s.endpoint)
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

        active_stdin_hook = stdin_hook or service.default_stdin_hook
        wrapped_user_stdin_hook = None
        if active_stdin_hook is not None:

            def _app_stdin_hook(prompt, *args, **kwargs):
                try:
                    res = active_stdin_hook(prompt, *args, **kwargs)
                except TypeError:
                    res = active_stdin_hook(prompt)
                try:
                    kc = runtime.kernel_client
                    wsclient = (
                        getattr(kc._manager, "client", None)
                        if kc and hasattr(kc, "_manager")
                        else None
                    )
                    if wsclient and hasattr(wsclient, "stdin_channel"):
                        content = {"value": res}
                        reply_msg = wsclient.session.msg("input_reply", content)
                        if isinstance(prompt, dict) and "header" in prompt:
                            reply_msg["parent_header"] = prompt["header"]
                        wsclient.stdin_channel.send(reply_msg)
                        logger.info(
                            "[colab_service] Successfully sent input_reply over WebSocket from our app code."
                        )
                except Exception:
                    logger.exception(
                        "[colab_service] Failed to send input_reply over WebSocket: %s"
                    )
                return res

            wrapped_user_stdin_hook = _app_stdin_hook

        try:
            outputs = runtime.execute_code(
                code,
                output_hook=output_hook if on_output else None,
                timeout=timeout,
                allow_stdin=intercept_oauth or (active_stdin_hook is not None),
                stdin_hook=wrapped_user_stdin_hook,
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
        except Exception as e:
            err_str = str(e)
            if (
                hasattr(e, "response")
                and getattr(e.response, "status_code", None) == 404
                or "404" in err_str
                or "Not Found" in err_str
            ):
                logger.warning(
                    f"[colab_service] Kernel for session '{session_name}' returned 404 (Expired/Closed). Removing from local storage."
                )
                st.store.remove(session_name)
                raise RuntimeError(
                    "Session has expired or closed on Colab server (404 Not Found) and was removed locally."
                ) from e
            raise
        finally:
            if intercept_oauth and runtime:
                runtime.colab_request_hook = None
            s.running = None
            if st.store.get(session_name):
                st.store.add(s)
            runtime.stop()

    return await asyncio.to_thread(_exec)

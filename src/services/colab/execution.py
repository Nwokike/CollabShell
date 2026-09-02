import asyncio
import datetime
import logging
import time
from collections.abc import Callable

logger = logging.getLogger("colab_execution")


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

        from services.colab.session_ops import (
            _refresh_runtime_token_sync as _heal_runtime_token,
        )

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

        def _new_runtime():
            return ColabRuntime(
                s.url,
                s.token,
                kernel_id=s.kernel_id,
                session_id=s.session_id,
                on_kernel_started=on_started,
                on_session_started=on_sess,
            )

        runtime = _new_runtime()
        preflight_code = (
            "import os; os.makedirs('/content', exist_ok=True); os.chdir('/content')"
        )

        for attempt in range(2):
            try:
                runtime.execute_code(preflight_code)
                break
            except Exception as e:
                from colab_cli.utils import is_terminal_error

                if not is_terminal_error(e):
                    raise
                # 404/401: the cached runtime-proxy token may simply have
                # expired while the assignment stayed alive. Heal it once
                # before pruning a session that may still be server-side.
                if attempt == 0 and _heal_runtime_token(st, session_name):
                    fresh = st.store.get(session_name)
                    if fresh:
                        s = fresh
                        runtime = _new_runtime()
                        continue
                st.prune_session(session_name)
                raise ValueError(
                    "Session lost (404/401). It may have timed out."
                ) from e

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
                    logger.exception("Suppressed exception")
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
                if content.get("request", {}).get("authType") != "dfs_ephemeral":
                    return False

                msg_id = deserialize_msg.get("metadata", {}).get("colab_msg_id")
                if on_output:
                    on_output(
                        "Drive mount needs Google credentials — checking authorization..."
                    )

                url = f"{st.client.colab_domain}/tun/m/credentials-propagation/{s.endpoint}"
                base_params = {
                    "authuser": "0",
                    "authtype": "dfs_ephemeral",
                    "version": "2",
                    "propagate": "true",
                    "record": "false",
                }
                creds = get_credentials(
                    st.client_oauth_config, provider=st.auth_provider
                )

                def _post(dryrun: str):
                    # Refresh the propagation token, then POST. Returns
                    # (status_code, parsed_json_body).
                    params = dict(base_params, dryrun=dryrun)
                    resp = creds.request("GET", url, params=params)
                    token = None
                    if get_status_code(resp) == 200:
                        try:
                            token = json.loads(resp.text.split("\n", 1)[-1]).get(
                                "token"
                            )
                        except Exception:
                            token = None
                    headers = {"x-goog-colab-token": token}
                    resp = creds.request(
                        "POST",
                        url,
                        params=params,
                        headers=headers,
                        files={"file_id": (None, "empty.ipynb")},
                    )
                    try:
                        data = json.loads(resp.text.split("\n", 1)[-1])
                    except Exception:
                        data = {}
                    return get_status_code(resp), data

                def _send_reply():
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

                # 1) Dry-run check: are credentials already authorized for this VM?
                _status, data = _post("true")
                if not data.get("success"):
                    uri = data.get("unauthorized_redirect_uri")
                    if active_stdin_hook and uri:
                        if on_output:
                            on_output(
                                "Google Drive authorization required — opening sign-in dialog."
                            )
                        prompt_text = (
                            "Google Drive Authorization Required\n\n"
                            "Click 'Open Link in Browser' below and grant access to your Google Drive.\n\n"
                            "After granting access, return here and tap 'Confirm & Continue'.\n\n"
                            + uri
                        )
                        try:
                            active_stdin_hook(prompt_text)
                        except TypeError:
                            active_stdin_hook(prompt_text)
                    elif on_output:
                        on_output(f"ERROR: Drive authorization required. Visit: {uri}")

                # 2) Propagate credentials to the VM (dryrun=false). Retry briefly
                #    to absorb Google's backend sync delay right after the user
                #    grants access. This is the step the old code skipped — it
                #    only re-ran the dry-run check, so the mount hung.
                for attempt in range(6):
                    status, data = _post("false")
                    if status == 200:
                        if on_output:
                            on_output(
                                "Credentials propagated — resuming Drive mount..."
                            )
                        _send_reply()
                        return True
                    if attempt < 5:
                        time.sleep(2.0)

                if on_output:
                    on_output(
                        "Could not propagate Drive credentials. Check the authorization and retry."
                    )
                # Reply anyway so the kernel resumes and reports the real mount
                # error instead of hanging until the execution timeout.
                _send_reply()
                return True

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

        def _execute_main():
            return runtime.execute_code(
                code,
                output_hook=output_hook if on_output else None,
                timeout=timeout,
                allow_stdin=intercept_oauth or (active_stdin_hook is not None),
                stdin_hook=wrapped_user_stdin_hook,
            )

        try:
            for attempt in range(2):
                try:
                    outputs = _execute_main()
                except Exception as e:
                    err_str = str(e)
                    is_404 = (
                        hasattr(e, "response")
                        and getattr(e.response, "status_code", None) == 404
                        or "404" in err_str
                        or "Not Found" in err_str
                    )
                    if not is_404:
                        raise
                    # A stale runtime-proxy token 404s exactly like a dead
                    # kernel. Heal once before removing a live session.
                    if attempt == 0 and _heal_runtime_token(st, session_name):
                        fresh = st.store.get(session_name)
                        if fresh:
                            s = fresh
                            runtime = _new_runtime()
                            if intercept_oauth:
                                runtime.colab_request_hook = drivefs_hook
                            continue
                    logger.warning(
                        f"[colab_service] Kernel for session '{session_name}' returned 404 (Expired/Closed). Removing from local storage."
                    )
                    st.store.remove(session_name)
                    raise RuntimeError(
                        "Session has expired or closed on Colab server (404 Not Found) and was removed locally."
                    ) from e
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
            if intercept_oauth and runtime:
                runtime.colab_request_hook = None
            s.running = None
            if st.store.get(session_name):
                st.store.add(s)
            runtime.stop()

    return await asyncio.to_thread(_exec)

import asyncio
import logging

logger = logging.getLogger("colab_session_ops")


async def new_session_impl(
    service,
    name: str | None = None,
    gpu: str | None = None,
    tpu: str | None = None,
    auth_method: str = "oauth2",
    keep_alive: bool = True,
) -> dict:
    """Create a new Colab session."""

    def _new():
        import uuid

        from colab_cli.auth import AuthProvider
        from colab_cli.client import Accelerator, ColabRequestError, Variant
        from colab_cli.common import State
        from colab_cli.state import SessionState
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
                res.runtime_proxy_info.url if hasattr(res, "runtime_proxy_info") else ""
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

        if keep_alive:
            try:
                st.client.keep_alive_assignment(endpoint)
            except ColabRequestError:
                pass

            st.store.add(s)
            s.keep_alive_pid = None
        else:
            st.store.add(s)
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
        }

    result = await asyncio.to_thread(_new)

    if keep_alive:
        service._start_in_process_keep_alive(
            result["name"], result["endpoint"], auth_method
        )

    return result


async def list_sessions_impl(service, auth_method: str = "oauth2") -> list:
    """List all active sessions."""
    await service._ensure_online()

    def _list():
        from colab_cli.auth import AuthProvider
        from colab_cli.common import State

        provider = AuthProvider.ADC if auth_method == "adc" else AuthProvider.OAUTH2
        st = State()
        st.auth_provider = provider

        local_sessions, assignments = st.sync_sessions()
        results = []
        name_by_ep = {s.endpoint: s.name for s in local_sessions.values()}

        recovered_count = 0
        for a in assignments:
            name = name_by_ep.get(a.endpoint)

            if not name:
                recovered_count += 1
                name = f"recovered-{recovered_count}"

                from colab_cli.state import SessionState

                recovered_session = SessionState(
                    name=name,
                    token=a.runtime_proxy_info.token,
                    url=a.runtime_proxy_info.url,
                    endpoint=a.endpoint,
                    variant=a.variant.name,
                    accelerator=a.accelerator.value,
                )
                st.store.add(recovered_session)
                local_sessions[name] = recovered_session

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
    except Exception:
        logger.exception("list_sessions failed")
        return []


async def stop_session_impl(
    service, session_name: str, auth_method: str = "oauth2"
) -> bool:
    """Stop a session by name."""
    task = service._keep_alive_tasks.pop(session_name, None)
    if task is not None and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception(
                "keep-alive task for %s raised unexpected exception", session_name
            )

    def _stop():
        from colab_cli.auth import AuthProvider
        from colab_cli.common import State
        from colab_cli.runtime import ColabRuntime

        provider = AuthProvider.ADC if auth_method == "adc" else AuthProvider.OAUTH2
        st = State()
        st.auth_provider = provider

        s = st.store.get(session_name)
        if not s:
            return False

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


async def restart_kernel_impl(
    service, session_name: str, auth_method: str = "oauth2"
) -> bool:
    """Restart a session's kernel."""
    await service._ensure_online()

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
            on_output=None,
        )
        try:
            runtime.restart()
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
            runtime.stop()
        return True

    return await asyncio.to_thread(_restart)


async def get_session_url_impl(
    service, session_name: str, auth_method: str = "oauth2"
) -> str:
    """Get the web URL of an active session."""

    def _url():
        from colab_cli.auth import AuthProvider
        from colab_cli.common import State

        provider = AuthProvider.ADC if auth_method == "adc" else AuthProvider.OAUTH2
        st = State()
        st.auth_provider = provider

        s = st.store.get(session_name)
        if not s:
            raise ValueError(f"Session '{session_name}' not found locally.")

        return f"{s.url}?authuser=0"

    return await asyncio.to_thread(_url)

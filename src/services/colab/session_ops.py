import asyncio
import logging

logger = logging.getLogger("colab_session_ops")


async def new_session_impl(
    service,
    name: str | None = None,
    gpu: str | None = None,
    tpu: str | None = None,
    auth_method: str = "oauth2",
    high_mem: bool = False,
) -> dict:
    """Create a new Colab session."""
    await service._ensure_online()

    def _new():
        import uuid

        from colab_cli.auth import AuthProvider
        from colab_cli.client import (
            Accelerator,
            ColabRequestError,
            Shape,
            TooManyAssignmentsError,
            Variant,
            resolve_assign_shape,
        )
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

        shape = resolve_assign_shape(accelerator, high_mem=high_mem)

        try:
            res = st.client.assign(
                uuid.uuid4(), variant=variant, accelerator=accelerator, shape=shape
            )
        except TooManyAssignmentsError:
            raise RuntimeError(
                "[colab] Allocation refused (precondition failed). This can mean "
                "too many active sessions, or a temporary usage or capacity "
                "limit for the requested runtime. Run `colab stop` to free up a "
                "session, wait and retry, or try a different accelerator."
            )
        except ColabRequestError as e:
            status_code = get_status_code(e)
            if status_code == 400 and accelerator != Accelerator.NONE:
                raise ValueError(
                    f"Backend rejected accelerator '{accelerator.value}'. "
                    "You may not have quota or entitlement for this accelerator "
                    "on your account. Try T4 (free) or CPU."
                )
            if status_code and status_code >= 500 and high_mem:
                # Live-observed: CPU + shape=hm returns 503 Service Unavailable
                # on free accounts. The shape is the problem, not the server.
                raise ValueError(
                    "High-RAM is not available on your free account — retry as "
                    "Standard RAM. High-RAM needs Colab Pro/Pro+."
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
            token_expires_at=(
                res.runtime_proxy_info.expires_at()
                if hasattr(res, "runtime_proxy_info")
                else None
            ),
            variant=variant.value,
            accelerator=accelerator.value,
            machine_shape=(
                Shape.HIGH_RAM.name if shape == Shape.HIGH_RAM else Shape.STANDARD.name
            ),
        )

        st.store.add(s)
        st.history.log_event(
            session_name,
            "session_created",
            {
                "endpoint": endpoint,
                "variant": variant.value,
                "accelerator": accelerator.value,
                "machine_shape": s.machine_shape,
            },
        )

        return {
            "name": session_name,
            "endpoint": endpoint,
            "variant": variant.value,
            "accelerator": accelerator.value,
            "machine_shape": s.machine_shape,
            "status": "READY",
        }

    result = await asyncio.to_thread(_new)

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
        # NOTE: upstream 0.7.4 `sync_sessions` already refreshes tokens +
        # `token_expires_at` for surviving sessions via `_apply_proxy_info`,
        # so no custom re-mint loop is needed here (it would only duplicate
        # the refresh without the expiry math).

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
                    token_expires_at=a.runtime_proxy_info.expires_at(),
                    variant=a.variant.name,
                    accelerator=a.accelerator.value,
                    machine_shape=a.machine_shape.name,
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
                    "machine_shape": a.machine_shape.name,
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


def load_session_fresh(st, session_name: str):
    """GUI-safe wrapper over upstream `State.get_session`.

    Always passes `ignore_missing_session=True` because bare `get_session`
    raises `typer.Exit(1)` (plus a `typer.echo` to stdout) on missing
    sessions — an unhandled control-flow exception inside Flet async code.
    Returns the refreshed `SessionState`, or `None` when missing/pruned so
    callers can map to their existing `ValueError`/status-string contracts.
    """
    return st.get_session(session_name, ignore_missing_session=True)


def _refresh_runtime_token_sync(st, session_name: str) -> bool:
    """Synchronously re-mint one session's runtime-proxy token from the server.

    Returns True when the local record was updated with a fresh token (the
    caller should retry its failed operation); False when the session is
    unknown locally, has no live assignment anymore, the token is unchanged,
    or the refresh itself failed (the caller keeps its existing error path).
    """
    try:
        s = load_session_fresh(st, session_name)
        if not s:
            return False

        assignments = st.client.list_assignments()
        match = next((a for a in assignments if a.endpoint == s.endpoint), None)
        if match is None:
            return False

        fresh = match.runtime_proxy_info
        if s.token == fresh.token and s.url == fresh.url:
            return False

        s.token = fresh.token
        s.url = fresh.url
        st.store.add(s)
        logger.info("[heal] refreshed runtime proxy token for session %s", session_name)
        return True
    except Exception:
        logger.debug(
            "runtime proxy token refresh failed for %s", session_name, exc_info=True
        )
        return False


async def refresh_session_token_impl(
    service, session_name: str, auth_method: str = "oauth2"
) -> bool:
    """Re-mint the runtime-proxy token for one session from the server."""
    await service._ensure_online()

    def _refresh():
        from colab_cli.auth import AuthProvider
        from colab_cli.common import State

        provider = AuthProvider.ADC if auth_method == "adc" else AuthProvider.OAUTH2
        st = State()
        st.auth_provider = provider
        return _refresh_runtime_token_sync(st, session_name)

    return await asyncio.to_thread(_refresh)


async def stop_session_impl(
    service, session_name: str, auth_method: str = "oauth2"
) -> bool:
    """Stop a session by name."""
    await service._ensure_online()

    def _stop():
        from colab_cli.auth import AuthProvider
        from colab_cli.common import State
        from colab_cli.runtime import ColabRuntime

        provider = AuthProvider.ADC if auth_method == "adc" else AuthProvider.OAUTH2
        st = State()
        st.auth_provider = provider

        s = load_session_fresh(st, session_name)
        if not s:
            return False

        try:
            # Fresh-read the token first: a long-lived session may have
            # outlived its runtime-proxy token (upstream run.py teardown pattern).
            runtime = ColabRuntime(s.url, s.token, kernel_id=s.kernel_id)
            runtime.stop(shutdown_kernel=True)
        except Exception:
            logger.exception("Suppressed exception")
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

        s = load_session_fresh(st, session_name)
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
        except Exception as e:
            err_str = str(e)
            is_404 = (
                (
                    hasattr(e, "response")
                    and getattr(e.response, "status_code", None) == 404
                )
                or "404" in err_str
                or "Not Found" in err_str
            )
            if is_404:
                # A stale runtime-proxy token 404s identically to a dead
                # kernel. Re-mint the token and retry once before pruning a
                # session that may still be alive server-side.
                if _refresh_runtime_token_sync(st, session_name):
                    s = load_session_fresh(st, session_name)
                    retry = ColabRuntime(
                        s.url,
                        s.token,
                        kernel_id=s.kernel_id,
                        session_id=s.session_id,
                        on_kernel_started=on_started,
                        on_session_started=on_sess,
                    )
                    try:
                        retry.restart()
                        return True
                    except Exception:
                        logger.exception(
                            "Kernel restart retry with fresh token failed for %s",
                            session_name,
                        )
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

        s = load_session_fresh(st, session_name)
        if not s:
            raise ValueError(f"Session '{session_name}' not found locally.")

        return f"{s.url}?authuser=0"

    return await asyncio.to_thread(_url)

import asyncio
import logging
from collections.abc import Callable

logger = logging.getLogger("colab_files_ops")


async def ls_impl(
    service,
    session_name: str,
    path: str = "/content",
    auth_method: str = "oauth2",
) -> list[dict]:
    """List files at a remote path. Returns list of file dicts."""
    await service._ensure_online()

    def _ls():
        import posixpath

        from colab_cli.auth import AuthProvider
        from colab_cli.common import State
        from colab_cli.contents import ContentsClient

        norm_path = posixpath.normpath(path) if path else ""
        if norm_path == "." or norm_path == "/":
            norm_path = ""

        provider = AuthProvider.ADC if auth_method == "adc" else AuthProvider.OAUTH2
        st = State()
        st.auth_provider = provider
        name = session_name or service._resolve_session(st)
        s = st.store.get(name)
        if not s:
            raise ValueError(f"Session '{name}' not found")

        client = ContentsClient(s)
        data = client.list_dir(norm_path)
        st.history.log_event(name, "file_operation", {"op": "ls", "path": norm_path})

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


async def upload_impl(
    service,
    session_name: str,
    local_path: str,
    remote_path: str,
    auth_method: str = "oauth2",
) -> bool:
    """Upload a local file to the remote session."""
    await service._ensure_online()

    def _upload():
        import posixpath

        from colab_cli.auth import AuthProvider
        from colab_cli.common import State
        from colab_cli.contents import ContentsClient

        norm_remote = posixpath.normpath(remote_path)

        provider = AuthProvider.ADC if auth_method == "adc" else AuthProvider.OAUTH2
        st = State()
        st.auth_provider = provider
        name = session_name or service._resolve_session(st)
        s = st.store.get(name)
        if not s:
            raise ValueError(f"Session '{name}' not found")

        client = ContentsClient(s)
        client.upload(local_path, norm_remote)
        st.history.log_event(
            name,
            "file_operation",
            {
                "op": "upload",
                "local": local_path,
                "remote": norm_remote,
            },
        )
        return True

    return await asyncio.to_thread(_upload)


async def download_impl(
    service,
    session_name: str,
    remote_path: str,
    local_path: str,
    auth_method: str = "oauth2",
) -> bool:
    """Download a remote file to a local path."""
    await service._ensure_online()

    def _download():
        import posixpath

        from colab_cli.auth import AuthProvider
        from colab_cli.common import State
        from colab_cli.contents import ContentsClient

        norm_remote = posixpath.normpath(remote_path)

        provider = AuthProvider.ADC if auth_method == "adc" else AuthProvider.OAUTH2
        st = State()
        st.auth_provider = provider
        name = session_name or service._resolve_session(st)
        s = st.store.get(name)
        if not s:
            raise ValueError(f"Session '{name}' not found")

        client = ContentsClient(s)
        client.download(norm_remote, local_path)
        st.history.log_event(
            name,
            "file_operation",
            {
                "op": "download",
                "remote": norm_remote,
                "local": local_path,
            },
        )
        return True

    return await asyncio.to_thread(_download)


async def download_folder_impl(
    service,
    session_name: str,
    remote_path: str,
    local_path: str,
    auth_method: str = "oauth2",
    on_progress: Callable | None = None,
) -> bool:
    """Download a remote directory as a zip file to a local path."""
    import posixpath

    norm_dir = posixpath.normpath(remote_path)
    if norm_dir.startswith("/content/") or norm_dir == "/content":
        vm_target_dir = norm_dir
    else:
        clean_rel = norm_dir.lstrip("/")
        vm_target_dir = (
            posixpath.join("/content", clean_rel) if clean_rel else "/content"
        )

    base_name = posixpath.basename(vm_target_dir)
    if not base_name:
        base_name = "folder"

    parent_dir = posixpath.dirname(vm_target_dir)
    vm_zip_base = posixpath.join(parent_dir, f"{base_name}_temp")
    vm_zip_path = f"{vm_zip_base}.zip"

    code = f"""
import subprocess, shutil, os
try:
    if shutil.which('zip'):
        subprocess.run(['zip', '-q', '-r', '{vm_zip_base}.zip', '.'], cwd='{vm_target_dir}', check=True, capture_output=True, text=True)
    else:
        shutil.make_archive('{vm_zip_base}', 'zip', '{vm_target_dir}')
except Exception as e:
    shutil.make_archive('{vm_zip_base}', 'zip', '{vm_target_dir}')
"""
    api_path = vm_zip_path

    logger.info(
        f"[colab_service] Zipping remote folder '{vm_target_dir}' on Colab VM into '{vm_zip_path}'..."
    )
    if on_progress:
        on_progress(f"Zipping {base_name} on VM...")

    try:
        outputs = await service.exec_code(
            code=code,
            session_name=session_name,
            auth_method=auth_method,
            timeout=120.0,
        )
        if outputs:
            for out in outputs:
                if out.get("output_type") == "error":
                    ename = out.get("ename", "Error")
                    evalue = out.get("evalue", "")
                    logger.error(
                        f"[colab_service] VM zipping failed: {ename}: {evalue}"
                    )
                    raise RuntimeError(
                        f"Failed to zip folder on VM ({ename}): {evalue}"
                    )

        logger.info(
            f"[colab_service] Zipping completed. Downloading '{api_path}' to '{local_path}' over HTTP..."
        )
        if on_progress:
            on_progress(f"Downloading {api_path} over HTTP...")

        await service.download(
            remote_path=api_path,
            local_path=local_path,
            session_name=session_name,
            auth_method=auth_method,
        )
        logger.info(
            f"[colab_service] Download completed successfully to '{local_path}'. Cleaning up temporary file '{api_path}' on VM..."
        )
        if on_progress:
            on_progress("Cleaning up temporary zip on VM...")
        return True
    finally:
        try:
            await service.rm(
                path=api_path,
                session_name=session_name,
                auth_method=auth_method,
            )
            logger.info(f"[colab_service] Temporary file '{api_path}' removed from VM.")
        except Exception as ex:
            logger.warning(
                f"[colab_service] Failed to remove temporary file '{api_path}': {ex}"
            )


async def rm_impl(
    service, session_name: str, path: str, auth_method: str = "oauth2"
) -> bool:
    """Delete a remote file."""

    def _rm():
        import posixpath

        from colab_cli.auth import AuthProvider
        from colab_cli.common import State
        from colab_cli.contents import ContentsClient

        norm_path = posixpath.normpath(path)

        provider = AuthProvider.ADC if auth_method == "adc" else AuthProvider.OAUTH2
        st = State()
        st.auth_provider = provider
        name = session_name or service._resolve_session(st)
        s = st.store.get(name)
        if not s:
            raise ValueError(f"Session '{name}' not found")

        client = ContentsClient(s)
        client.rm(norm_path)
        st.history.log_event(name, "file_operation", {"op": "rm", "path": norm_path})
        return True

    return await asyncio.to_thread(_rm)

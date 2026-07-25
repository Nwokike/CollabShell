import logging
from collections.abc import Callable

logger = logging.getLogger("colab_vm_ops")


async def mount_drive_impl(
    service,
    session_name: str,
    path: str = "/content/drive",
    auth_method: str = "oauth2",
    on_output: Callable | None = None,
    stdin_hook: Callable | None = None,
) -> bool:
    """Mount Google Drive at the given path."""
    code = f"from google.colab import drive\ndrive.mount('{path}')"
    try:
        await service.exec_code(
            code,
            session_name,
            timeout=600,
            auth_method=auth_method,
            on_output=on_output,
            intercept_oauth=True,
            stdin_hook=stdin_hook,
        )
        return True
    except Exception as e:
        logger.error("mount_drive failed: %s", e)
        return False


async def install_packages_impl(
    service,
    session_name: str,
    packages: list,
    auth_method: str = "oauth2",
    on_output: Callable | None = None,
) -> bool:
    """Install Python packages on the VM."""
    code = f"""
import subprocess, sys
try:
    subprocess.check_call(['uv', 'pip', 'install', '--system'] + {packages!r})
    print('Installation Complete (via uv)!')
except:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install'] + {packages!r})
    print('Installation Complete (via pip)!')
"""
    try:
        await service.exec_code(
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


async def auth_gcp_on_vm_impl(
    service,
    session_name: str,
    auth_method: str = "oauth2",
    on_output: Callable | None = None,
    stdin_hook: Callable | None = None,
) -> bool:
    """Authenticate GCP on the VM."""
    await service._ensure_online()
    code = "import os\nos.environ['USE_AUTH_EPHEM'] = '0'\nfrom google.colab import auth\nauth.authenticate_user()"
    try:
        await service.exec_code(
            code,
            session_name,
            timeout=600,
            auth_method=auth_method,
            on_output=on_output,
            intercept_oauth=True,
            stdin_hook=stdin_hook,
        )
        return True
    except Exception as e:
        logger.error("auth_gcp_on_vm failed: %s", e)
        return False

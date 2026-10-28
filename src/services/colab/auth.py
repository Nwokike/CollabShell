import asyncio
import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger("colab_auth")


async def init_impl(service) -> bool:
    """Initialize the colab_cli State singleton and check availability."""
    try:

        def _init():
            from colab_cli.common import State

            service._cli_state = State()
            service._cli_available = True
            return True

        return await asyncio.to_thread(_init)
    except Exception as e:
        logger.error("Failed to init colab_cli: %s", e)
        service._cli_available = False
        return False


async def ensure_online_impl(service):
    """Raise ConnectionError when Google services cannot be reached."""

    def _check():
        try:
            with urllib.request.urlopen("https://oauth2.googleapis.com/", timeout=3):
                return True
        except urllib.error.HTTPError:
            # An HTTP response (including a 404 for this root path) proves
            # DNS, TLS, and the remote service are reachable.
            return True
        except (OSError, TimeoutError, urllib.error.URLError):
            return False

    is_online = await asyncio.to_thread(_check)
    if not is_online:
        from core.constants import ERR_NETWORK

        raise ConnectionError(ERR_NETWORK)


def _auth_status_for_error(exc: BaseException) -> str:
    """Classify only explicit credential rejection as signed out."""
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None) or getattr(exc, "code", None)
    if status_code in (400, 401):
        return "unauthenticated"
    if status_code is not None:
        return "unavailable"
    message = str(exc).lower()
    if any(marker in message for marker in ("invalid_grant", "invalid credentials")):
        return "unauthenticated"
    return "unavailable"


def _auth_error_message(exc: BaseException) -> str:
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    status_code = status_code or getattr(exc, "code", None)
    if status_code is not None:
        return f"Google sign-in verification returned HTTP {status_code}. Try again."
    return (
        "Could not verify sign-in with Google "
        f"({type(exc).__name__}). Check your connection and retry."
    )


async def get_auth_url_impl(service) -> str:
    """Generate the OAuth2 authorization URL for the user to visit."""

    def _get_url():
        from importlib import resources

        from colab_cli.auth import (
            PUBLIC_SCOPES,
            REMOTE_REDIRECT_URI,
            TOKEN_CONFIG_PATH,
        )
        from google_auth_oauthlib.flow import InstalledAppFlow

        config_resource = resources.files("colab_cli").joinpath("oauth_config.json")
        client_config = json.loads(config_resource.read_text())

        flow = InstalledAppFlow.from_client_config(client_config, PUBLIC_SCOPES)
        flow.redirect_uri = REMOTE_REDIRECT_URI
        auth_url, _ = flow.authorization_url(prompt="consent", token_usage="remote")

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


async def authenticate_oauth2_impl(service, code: str) -> dict:
    """Complete the OAuth2 flow with the authorization code."""

    def _auth(code):
        from importlib import resources

        from colab_cli.auth import (
            PUBLIC_SCOPES,
            REMOTE_REDIRECT_URI,
            TOKEN_CONFIG_PATH,
        )
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow

        config_resource = resources.files("colab_cli").joinpath("oauth_config.json")
        client_config = json.loads(config_resource.read_text())

        flow = InstalledAppFlow.from_client_config(client_config, PUBLIC_SCOPES)
        flow.redirect_uri = REMOTE_REDIRECT_URI

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
                    fetch_kwargs["code_verifier"] = verifier
                    if hasattr(flow, "oauth2session"):
                        flow.oauth2session.code_verifier = verifier
            except Exception as e:
                logger.error("Failed to load OAuth2 code verifier: %s", e)

        flow.fetch_token(**fetch_kwargs)
        creds = flow.credentials

        if os.path.exists(verifier_path):
            try:
                os.remove(verifier_path)
            except Exception:
                logger.exception("Suppressed exception")
        os.makedirs(os.path.dirname(TOKEN_CONFIG_PATH), exist_ok=True)
        with open(TOKEN_CONFIG_PATH, "w") as f:
            f.write(creds.to_json())

        creds.refresh(Request())
        import urllib.parse
        import urllib.request

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


async def check_auth_impl(service) -> dict:
    """Check if current credentials are valid without ever triggering interactive CLI terminal prompt."""

    def _check():
        import urllib.parse
        import urllib.request

        from colab_cli.auth import PUBLIC_SCOPES, TOKEN_CONFIG_PATH
        from google.auth.transport.requests import Request as _Req
        from google.oauth2.credentials import Credentials

        def result(authenticated, status, email="", expires_in="", error=""):
            return {
                "authenticated": authenticated,
                "email": email,
                "expires_in": expires_in,
                "auth_method": "oauth2",
                "status": status,
                "error": error,
            }

        if not os.path.exists(TOKEN_CONFIG_PATH):
            return result(False, "unauthenticated")

        try:
            creds = Credentials.from_authorized_user_file(
                TOKEN_CONFIG_PATH, PUBLIC_SCOPES
            )
            if not creds:
                return result(False, "unauthenticated")

            if creds.expired:
                if not creds.refresh_token:
                    return result(False, "unauthenticated")
                try:
                    creds.refresh(_Req())
                    # Persist refreshed token
                    with open(TOKEN_CONFIG_PATH, "w") as f:
                        f.write(creds.to_json())
                except Exception as ref_err:
                    status = _auth_status_for_error(ref_err)
                    logger.warning(
                        "Token refresh verification failed (%s, %s)",
                        status,
                        type(ref_err).__name__,
                    )
                    return result(
                        status == "authenticated",
                        status,
                        error=(
                            ""
                            if status == "unauthenticated"
                            else _auth_error_message(ref_err)
                        ),
                    )

            token = creds.token
            if not token:
                return result(False, "unauthenticated")

            qs = urllib.parse.urlencode({"access_token": token})
            url = f"https://oauth2.googleapis.com/tokeninfo?{qs}"
            with urllib.request.urlopen(url, timeout=10) as resp:
                info = json.loads(resp.read().decode("utf-8"))

            email = info.get("email", "")
            expires_in = info.get("expires_in", "")
            try:
                expires_min = int(expires_in) // 60
                expires_str = f"{expires_min}m"
            except TypeError, ValueError:
                expires_str = str(expires_in)

            return result(True, "authenticated", email, expires_str)
        except Exception as e:
            status = _auth_status_for_error(e)
            logger.warning("Auth check failed (%s, %s)", status, type(e).__name__)
            return result(
                status == "authenticated",
                status,
                error=("" if status == "unauthenticated" else _auth_error_message(e)),
            )

    return await asyncio.to_thread(_check)


async def clear_token_impl(service) -> bool:
    """Delete the cached OAuth2 token."""

    def _clear():
        from colab_cli.auth import TOKEN_CONFIG_PATH

        if os.path.exists(TOKEN_CONFIG_PATH):
            os.remove(TOKEN_CONFIG_PATH)
            return True
        return False

    return await asyncio.to_thread(_clear)

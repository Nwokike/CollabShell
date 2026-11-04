import asyncio
import sys
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

_SRC = Path(__file__).resolve().parents[3] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from services.colab import auth


def test_auth_error_classifies_only_explicit_rejection_as_unauthenticated():
    rejected = urllib.error.HTTPError(
        "https://oauth2.googleapis.com/tokeninfo", 401, "Unauthorized", {}, None
    )
    unavailable = urllib.error.HTTPError(
        "https://oauth2.googleapis.com/tokeninfo", 503, "Unavailable", {}, None
    )

    assert auth._auth_status_for_error(rejected) == "unauthenticated"
    assert auth._auth_status_for_error(unavailable) == "unavailable"
    forbidden = urllib.error.HTTPError(
        "https://oauth2.googleapis.com/tokeninfo", 403, "Forbidden", {}, None
    )
    assert auth._auth_status_for_error(forbidden) == "unavailable"
    assert auth._auth_status_for_error(TimeoutError()) == "unavailable"
    assert auth._auth_status_for_error(RuntimeError("invalid_grant")) == (
        "unauthenticated"
    )


def test_reachability_probe_treats_an_http_response_as_online(monkeypatch):
    def _http_response(*args, **kwargs):
        raise urllib.error.HTTPError(args[0], 404, "Not Found", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", _http_response)
    assert asyncio.run(auth.ensure_online_impl(SimpleNamespace())) is None


def test_reachability_probe_does_not_treat_timeout_as_online(monkeypatch):
    def _timeout(*args, **kwargs):
        raise TimeoutError("handshake timed out")

    monkeypatch.setattr(urllib.request, "urlopen", _timeout)
    with pytest.raises(ConnectionError):
        asyncio.run(auth.ensure_online_impl(SimpleNamespace()))

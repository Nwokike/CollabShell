"""Tests for the rewritten UpdateService (ktv-player design) and the
bundled changelog guard."""

import asyncio
import sys
from unittest.mock import patch

import httpx

sys.path.insert(0, "src")

from core.changelog import notes_for
from core.constants import APP_BUILD_NUMBER, APP_VERSION
from services.update_service import UpdateService


def _service(payload, status=200):
    def _handler(request):
        return httpx.Response(status, json=payload)

    transport = httpx.MockTransport(_handler)
    svc = UpdateService("https://example.test/version.json")

    # Inject the mock transport into the client the service creates.
    original_client = httpx.AsyncClient

    def _client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    svc._patch = patch.object(httpx, "AsyncClient", side_effect=_client)
    return svc


def test_newer_build_detected():
    svc = _service(
        {
            "build_number": APP_BUILD_NUMBER + 1,
            "version": "9.9.9",
            "release_notes": "- fixed things",
            "type": "update",
        }
    )
    with svc._patch:
        result = asyncio.run(svc.check_for_update())
    assert result is not None
    assert result["build_number"] == APP_BUILD_NUMBER + 1
    assert result["version"] == "9.9.9"
    assert result["release_notes"] == "- fixed things"
    assert result["mandatory"] is False
    assert result["github_url"]  # ktv-style default fallback applies


def test_same_build_returns_none():
    svc = _service({"build_number": APP_BUILD_NUMBER, "version": APP_VERSION})
    with svc._patch:
        result = asyncio.run(svc.check_for_update())
    assert result is None


def test_non_int_build_returns_none():
    svc = _service({"build_number": "99", "version": "9.9.9"})
    with svc._patch:
        result = asyncio.run(svc.check_for_update())
    assert result is None


def test_non_200_returns_none():
    svc = _service({}, status=500)
    with svc._patch:
        result = asyncio.run(svc.check_for_update())
    assert result is None


def test_invalid_json_returns_none():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, text="not json")
    )
    svc = UpdateService("https://example.test/version.json")
    original_client = httpx.AsyncClient

    def _client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    with patch.object(httpx, "AsyncClient", side_effect=_client):
        result = asyncio.run(svc.check_for_update())
    assert result is None


def test_announcement_type_preserved():
    svc = _service(
        {
            "build_number": APP_BUILD_NUMBER + 1,
            "version": "9.9.9",
            "type": "announcement",
            "title": "News",
        }
    )
    with svc._patch:
        result = asyncio.run(svc.check_for_update())
    assert result["type"] == "announcement"
    assert result["title"] == "News"


def test_changelog_has_entry_for_current_version():
    """Guard: bumping APP_VERSION without adding a CHANGELOG entry fails."""
    assert notes_for(APP_VERSION), f"CHANGELOG is missing an entry for {APP_VERSION}"

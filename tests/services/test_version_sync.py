"""Version-sync guard — every place the app version/build lives must agree.

This exists because a partial bump once shipped: build 11 went into
pyproject.toml, version.json, and the build workflow while
core.constants (the runtime truth the update check compares against)
stayed at 10, so every installed app saw a phantom "update available"
for the version it already ran.

Note on version.json: it is the LIVE update feed, so it is deliberately
held back until a build is published. The invariant for it is
one-sided: the feed must never get AHEAD of the shipped build
(feed build <= APP_BUILD_NUMBER), otherwise installed apps see an
update that does not exist yet.
"""

import json
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, "src")

from core.constants import APP_BUILD_NUMBER, APP_VERSION

ROOT = Path(__file__).resolve().parent.parent.parent


def test_version_in_sync_everywhere():
    """APP_VERSION / APP_BUILD_NUMBER must match pyproject + uv.lock.

    version.json (the live feed) is staged separately — see
    test_feed_never_ahead_of_app below.
    """
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert str(pyproject["project"]["version"]) == APP_VERSION, (
        f"pyproject version {pyproject['project']['version']!r} != "
        f"APP_VERSION {APP_VERSION!r}"
    )
    assert int(pyproject["tool"]["flet"]["build_number"]) == APP_BUILD_NUMBER, (
        f"pyproject build_number {pyproject['tool']['flet']['build_number']!r} != "
        f"APP_BUILD_NUMBER {APP_BUILD_NUMBER!r}"
    )

    lock_text = (ROOT / "uv.lock").read_text()
    assert f'name = "collabshell"\nversion = "{APP_VERSION}"' in lock_text, (
        f"uv.lock collabshell entry is stale — run `uv sync` "
        f"(APP_VERSION {APP_VERSION!r})"
    )


def test_feed_never_ahead_of_app():
    """version.json must never advertise a build newer than the shipped app.

    The feed goes live the moment it is pushed, so a feed build ahead of
    APP_BUILD_NUMBER means installed apps see an update that does not
    exist yet. Lagging behind is fine (feed is staged after publishing).
    """
    feed = json.loads((ROOT / "version.json").read_text())
    assert int(feed["build_number"]) <= APP_BUILD_NUMBER, (
        f"version.json build {feed['build_number']!r} is AHEAD of the shipped "
        f"APP_BUILD_NUMBER {APP_BUILD_NUMBER!r} — hold the feed back until "
        "the new build is published"
    )


def test_workflow_defaults_in_sync():
    """The build workflow's default version/build must match too."""
    workflow = (ROOT / ".github" / "workflows" / "build-all.yml").read_text()
    assert f'default: "{APP_VERSION}"' in workflow, (
        f"build-all.yml missing build_version default {APP_VERSION!r}"
    )
    assert f'default: "{APP_BUILD_NUMBER}"' in workflow, (
        f"build-all.yml missing build_number default {APP_BUILD_NUMBER!r}"
    )
    assert f"inputs.build_version || '{APP_VERSION}'" in workflow
    assert f"inputs.build_number || '{APP_BUILD_NUMBER}'" in workflow

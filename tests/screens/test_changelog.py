"""The version dialog must show THIS version's changelog.

The owner clicked the version in Settings and saw a changelog two versions
old, under a header reading "✓ Latest version · v2.2.0". Two defects caused
it, both verified:

1. `notes_for` fell back to `next(reversed(CHANGELOG.values()), "")` — which
   yields the LAST-INSERTED value, i.e. the OLDEST entry (2.1.0) — and
   `CHANGELOG` had no "2.2.0" key while `constants.APP_VERSION` was "2.2.0".
2. The 2.2.0-era features (High-RAM, the usage card, per-session env vars,
   multiple notebooks) were appended to the "2.1.2" entry, so even the right
   fallback would have shown the wrong release.

A green test (`tests/test_phase5_regression.py:54-56`) pinned the wrong
fallback as a contract, which is why the suite never noticed.
"""

from __future__ import annotations

import pathlib
import sys

_SRC = pathlib.Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from core import constants
from core.changelog import CHANGELOG, notes_for


def test_there_is_an_entry_for_the_running_version():
    assert constants.APP_VERSION in CHANGELOG, (
        f"APP_VERSION {constants.APP_VERSION!r} has no changelog entry; the "
        "version dialog falls back to another release's notes"
    )


def test_notes_for_the_running_version_is_that_version():
    assert notes_for(constants.APP_VERSION) == CHANGELOG[constants.APP_VERSION]


def test_the_fallback_is_the_newest_entry_not_the_oldest():
    """An unknown version shows the NEWEST notes, by version order."""
    newest = max(CHANGELOG, key=lambda v: tuple(int(x) for x in v.split(".")))
    assert notes_for("9.9.9") == CHANGELOG[newest], (
        f"expected the newest entry ({newest}); the oldest is what "
        "`reversed(dict.values())` actually yields"
    )


def test_the_2_1_2_entry_is_only_2_1_2():
    """The 2.2.0 features were misfiled here; they must not still be."""
    entry = CHANGELOG.get("2.1.2", "")
    for bullet_start in (
        "High-RAM shape",
        "Compute usage card",
        "Per-session environment variables",
        "Multiple notebooks per session",
    ):
        assert bullet_start not in entry, (
            f"{bullet_start!r} is a 2.2.0 feature filed under 2.1.2"
        )


def test_the_2_2_0_entry_covers_this_release():
    """The 2.2.0 entry names the features that actually shipped in 2.2.0."""
    entry = CHANGELOG.get("2.2.0", "")
    for fragment in (
        "High-RAM",
        "usage card",
        "environment variables",
        "notebooks",
        "Assistant",
    ):
        assert fragment.lower() in entry.lower(), (
            f"the 2.2.0 entry does not mention {fragment!r}"
        )

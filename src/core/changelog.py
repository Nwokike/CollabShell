"""Bundled changelog shown by the version dialog when the app is up to
date — works fully offline. One line per release; keep the entry for the
current APP_VERSION in sync when bumping (guarded by tests)."""

CHANGELOG: dict[str, str] = {
    "2.1.2": (
        "- Fixed the false 'update available' prompt — the last build\n"
        "  missed a version bump in one spot, so 2.1.1 kept showing as new\n"
        "- General bug fixes and stability improvements\n"
        "- Expanded automated test coverage, including a guard that keeps\n"
        "  version numbers in sync across every release"
    ),
    "2.1.1": (
        "- Sessions no longer die after hours idle — the runtime proxy token\n"
        "  now refreshes automatically on resume, session sync, and 404\n"
        "- Terminal tabs reconnect with a fresh token instead of erroring\n"
        "- Files browser self-heals after long sessions\n"
        "- Kernel execution no longer drops a live session on a stale token\n"
        "- Update notifications: version chip and changelog dialog\n"
        "- Check for Updates button in the version dialog"
    ),
    "2.1.0": (
        "- GitHub version.json update service + always-tappable changelog\n"
        "- Auto-refocus the terminal so shortcuts survive toolbar clicks\n"
        "- Flet libs for Windows installation"
    ),
}


def notes_for(version: str) -> str:
    """Changelog entry for a version, falling back to the latest entry."""
    return CHANGELOG.get(version) or next(reversed(CHANGELOG.values()), "")

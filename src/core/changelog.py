"""Bundled changelog shown by the version dialog when the app is up to
date — works fully offline. One line per release; keep the entry for the
current APP_VERSION in sync when bumping (guarded by tests)."""

CHANGELOG: dict[str, str] = {
    "2.1.2": (
        "- Fixed phantom update prompt — build number is now in sync\n"
        "  across the app, store config, and update feed\n"
        "- No more 'update available' for the version you already run\n"
        "- High-RAM shape for new sessions (Colab Pro/Pro+)\n"
        "- Compute usage card + home balance chip (Settings → Account;\n"
        "  auto-loads on open, tap Refresh to re-fetch — values, a fetched\n"
        "  timestamp, and truthful errors every time)\n"
        "- Per-session environment variables (defaults + override;\n"
        "  values are never logged)\n"
        "- Multiple notebooks per session, each with isolated saves/exports\n"
        "- Sessions survive stale tokens via automatic refresh\n"
        "- Friendly errors for GPU allocation limits\n"
        "- Session header rails scroll visibly on narrow screens\n"
        "- Direct SSH access deferred to a later release"
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

"""Bundled changelog shown by the version dialog when the app is up to
date — works fully offline. One line per release; keep the entry for the
current APP_VERSION in sync when bumping (guarded by tests)."""

CHANGELOG: dict[str, str] = {
    "2.2.0": (
        "- Assistant: the app runs its own local model router — it attaches\n"
        "  to one already running or embeds its own, so the assistant works\n"
        "  with no setup\n"
        "- The thinking stream is visible while the assistant reasons, and a\n"
        "  Thinking-depth control sets how hard it thinks\n"
        "- Ask AI about a cell, a file, or terminal output; the assistant can\n"
        "  create sessions and read them live\n"
        "- High-RAM shape for new sessions (Colab Pro/Pro+)\n"
        "- Compute-unit usage card (Settings → Account) with a shared cache\n"
        "  and truthful errors\n"
        "- Per-session environment variables (defaults + override; values are\n"
        "  never logged)\n"
        "- Multiple notebooks per session, each with isolated saves/exports,\n"
        "  plus Python script tabs — plain .py files you edit, run, and save\n"
        "  back to the session\n"
        "- Command palette (Ctrl+K) and Ctrl+I to ask about the active cell\n"
        "- Premium: restore purchases, the recovery ID shown with copy, and\n"
        "  honest pricing from the licence service"
    ),
    "2.1.2": (
        "- Fixed phantom update prompt — build number is now in sync\n"
        "  across the app, store config, and update feed\n"
        "- No more 'update available' for the version you already run\n"
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


def _version_key(version: str) -> tuple[int, ...]:
    """A version's sort key; unparsable segments sort as zero."""
    try:
        return tuple(int(x) for x in version.split("."))
    except ValueError:
        return (0,)


def notes_for(version: str) -> str:
    """Changelog entry for a version, falling back to the NEWEST entry.

    The fallback is by version ORDER, not insertion order — an earlier
    version of this helper used `reversed(dict.values())`, which yields the
    *last-inserted* value. With entries ordered newest-first that was the
    OLDEST release, so an app whose version had no entry showed a changelog
    two versions old under a "You're up to date" header.
    """
    if version in CHANGELOG:
        return CHANGELOG[version]
    if not CHANGELOG:
        return ""
    newest = max(CHANGELOG, key=_version_key)
    return CHANGELOG[newest]

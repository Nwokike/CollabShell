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
        "  create sessions and read them live — even when the session screen\n"
        "  is not open\n"
        "- Assistant can create notebook tabs and switch between them, and\n"
        "  writes starter notebooks without you opening one first\n"
        "- Terminal AI: follow-up questions in the same dialog, and the whole\n"
        "  thread continues in the chat with one tap\n"
        "- Cell AI: Explain and Suggest Next in a two-option menu, and Fix\n"
        "  Error appears on the output row only when a run actually failed\n"
        "- Cancel button while the assistant is working — in cells, in the\n"
        "  terminal dialog, and Stop in chat\n"
        "- The assistant is no longer cut off mid-task: far more tool rounds\n"
        "  per reply and a much longer working window\n"
        "- Credits persist across restarts and reset to the daily cap at\n"
        "  00:00 UTC; premium days refill to 500, free to 50\n"
        "- Premium reads at launch: your 500-credit day and ad-free state\n"
        "  are correct from the first second after an update\n"
        "- Sessions stay alive while the app is open — a quiet keep-alive\n"
        "  resets Colab's idle timer well inside its prune window\n"
        "- Interstitial ads at the natural breaks: opening, creating, or\n"
        "  closing a session (never more than one per interval)\n"
        "- Banner ads across the app, each placed once and reused — no more\n"
        "  flashing or missing banners; sticky banner in the terminal and in\n"
        "  Python script tabs\n"
        "- Settings rows move their controls under the label on small\n"
        "  screens, starting with the assistant model picker\n"
        "- Restore-licence verdicts are honest: a wrong recovery ID says so\n"
        "  instead of claiming the service is unreachable\n"
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
        "  honest pricing from the licence service\n"
        "- Stability: splash no longer flashes the home screen mid-boot, the\n"
        "  bottom navigation stays put on every screen, the FAB switches\n"
        "  cleanly between the assistant and session options, a boot crash\n"
        "  right after launch is fixed, and flet 1.1.0 stable throughout"
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


def _version_key(version: str) -> tuple[int, ...] | None:
    """A version's sort key; None when the version is unparseable."""
    try:
        return tuple(int(x) for x in str(version).split("."))
    except ValueError:
        return None


def notes_for(version: str) -> str:
    """Changelog entry for a version, falling back to the NEWEST entry.

    The fallback is by version ORDER, not insertion order — an earlier
    version of this helper used `reversed(dict.values())`, which yields the
    *last-inserted* value. With entries ordered newest-first that was the
    OLDEST release, so an app whose version had no entry showed a changelog
    two versions old under a "You're up to date" header. Unparseable keys
    are excluded from the fallback entirely, so a malformed entry can never
    be picked as "newest".
    """
    if version in CHANGELOG:
        return CHANGELOG[version]
    keys = [v for v in CHANGELOG if _version_key(v) is not None]
    if not keys:
        return ""
    newest = max(keys, key=_version_key)
    return CHANGELOG[newest]

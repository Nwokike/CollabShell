"""Bundled changelog shown by the version dialog when the app is up to
date — works fully offline. One line per release; keep the entry for the
current APP_VERSION in sync when bumping (guarded by tests)."""

CHANGELOG: dict[str, str] = {
    "2.3.0": (
        "- AI assistant: ask anything from the header icon, the session FAB,\n"
        "  or Ctrl+Shift+K — it streams replies from Kiri Router with a\n"
        "  collapsible thinking block, and keeps going in the notebook or\n"
        "  terminal when you minimize the panel\n"
        "- 50 free AI credits a day, one per model call; failed calls are\n"
        "  refunded\n"
        "- Model picker shows only the models Kiri is serving right now,\n"
        "  with each one's rate limit before you pick it\n"
        "- Ads: interstitials reload after every show, and a failed ad no\n"
        "  longer blocks downloads or log exports\n"
        "- High-RAM default stays off; the tip now says free Colab\n"
        "  accounts cannot use it\n"
        "- Android 2.3.0: ARM64 only — Colab's dependency tree cannot\n"
        "  resolve 32-bit wheels any more"
    ),
    "2.2.0": (
        "- Upgraded to Flet 1.0: snappier copy/open buttons (client-side\n"
        "  actions), a biometric check before clearing your Google\n"
        "  credentials, and more reliable platform storage\n"
        "- High-RAM machine shape for new sessions (CPU/T4/G4/A100/H100),\n"
        "  shown as a badge on session cards\n"
        "- Environment variables (KEY=VALUE) injected before every code run\n"
        "  — Settings → Execution\n"
        "- Tap Compute Usage in Settings → About for compute-unit balance,\n"
        "  burn rate, and active runtimes (google-colab-cli 0.7.2)\n"
        "- Notebook cells render Markdown & HTML outputs (pandas DataFrames,\n"
        "  rich reprs) instead of dropping them\n"
        "- Drive mount credentials propagate reliably again; friendly\n"
        "  messages for quota/capacity errors instead of tracebacks\n"
        "- Fixed two crash-on-import bugs, a terminal-open UI freeze, and\n"
        "  session cleanup when closing the app\n"
        "- Settings save instantly (native storage) with existing\n"
        "  preferences imported automatically"
    ),
    "2.1.2": (
        "- Fixed the false 'update available' prompt from 2.1.1 — one\n"
        "  version spot was missed in the last bump, so the app kept\n"
        "  flagging 2.1.1 as new even though you already had it\n"
        "- General bug fixes and stability improvements\n"
        "- Expanded automated test coverage, including a guard that keeps\n"
        "  the version numbers in sync across every release"
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

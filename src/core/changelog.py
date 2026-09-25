"""Bundled changelog shown by the version dialog when the app is up to
date — works fully offline. One line per release; keep the entry for the
current APP_VERSION in sync when bumping (guarded by tests)."""

CHANGELOG: dict[str, str] = {
    "3.0.0": (
        "- The Assistant, powered by Kiri Router: ask from the header, the\n"
        "  session FAB, Ctrl+Shift+K, or the chat icon on any notebook cell\n"
        "  or terminal. It can act on your Colab account — list sessions and\n"
        "  files, run code, install packages, start or stop a session, mount\n"
        "  Drive — and anything that changes something asks first, showing\n"
        "  the exact code it wants to run\n"
        "- The Assistant works in your notebook and your terminal: it reads\n"
        "  and rewrites cells, inserts new ones, runs them, and types\n"
        "  commands into the terminal you already have open, so you watch it\n"
        "  work\n"
        "- Many chats with per-chat delete (20 kept), a collapsible thinking\n"
        "  block, a scrollable model picker, and a step/credit receipt\n"
        "- 50 free Assistant credits a day, 2 per model call, +2 for watching\n"
        "  a short ad (one at a time, 30s between). Failed calls are\n"
        "  refunded; a turn is never aborted for being a credit short\n"
        "- Fixed: the Assistant no longer crashes on open — it is mounted\n"
        "  through Flet's declarative dialog API now\n"
        "- Fixed: Drive mount and Google Cloud auth work on Android again\n"
        "- Fixed: the model list no longer offers models that cannot answer\n"
        "  (3 of 48 were dead ends), says 'Kiri unreachable' when it truly\n"
        "  cannot be reached, and never sits on 'Starting...' forever\n"
        "- Fixed: a cell using 'from __future__ import' no longer breaks when\n"
        "  execution environment variables are set\n"
        "- Fixed: an empty model reply is retried once, then reported — and\n"
        "  never charged for\n"
        "- Fixed: upgrading no longer loses your Google login, saved\n"
        "  sessions, or history (the storage layout migrates automatically)\n"
        "- The launcher icon is adaptive again — the white square is gone\n"
        "- An Android emulator (x86_64) build is available alongside the\n"
        "  ARM64 APK\n"
        "- Premium: Google Play Billing on the Play build, Kiri License\n"
        "  Worker on direct/desktop builds. The Play Store build is free-only\n"
        "  for now and shows no purchase UI at all\n"
        "- Premium removes ads, raises credits to 200/day, and shows honest\n"
        "  renewal status ('Payment overdue', 'Premium expired', 'Premium\n"
        "  refunded') refreshed every time the app resumes\n"
        "- Upgraded to Flet 1.0: native settings storage, copy/open buttons\n"
        "  that work inside dialogs, biometric protection for credentials,\n"
        "  High-RAM machine shapes, env-var injection, and compute-usage\n"
        "  reporting\n"
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

"""Phase 5 regression tests: toggle reframe, history detail, changelog, intercept parity."""

import sys

sys.path.insert(0, "src")


def test_dead_keep_alive_key_unreferenced():
    # rglob scan (works without git): the write-only Active toggle chain is
    # gone — no src/ file may reference the deleted state field.
    from pathlib import Path

    hits = [
        f"{p}:{i + 1}"
        for p in sorted(Path("src").rglob("*.py"))
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines())
        if "keep_alive_enabled" in line
    ]
    assert hits == [], f"dead key references remain: {hits}"


def test_auto_stop_copy_present_in_behavior_section():
    import inspect

    from screens.settings import behavior_section

    src = inspect.getsource(behavior_section.build_behavior_section)
    assert "Auto-stop sessions on exit" in src
    assert "Keep-Alive" not in src
    assert "TIP_KEEP_ALIVE" not in src


def test_history_detail_renders_shape_env_reason():
    import pathlib

    src = pathlib.Path("src/screens/history/__init__.py").read_text(encoding="utf-8")
    assert "machine_shape" in src
    assert "env_keys" in src
    assert "session_terminated" in src


def test_changelog_covers_phases_and_fallback_intact():
    """The 2.2.0 entry owns the 2.2.0 features; the fallback is the newest.

    This test once pinned the WRONG fallback as a contract — it asserted
    `notes_for("9.9.9") == CHANGELOG["2.1.0"]` and called that "the latest
    entry", because `reversed(dict.values())` yields the last-inserted value
    and the dict happened to be ordered oldest-last. The owner then clicked
    the version in Settings and saw 2.1.0's notes under a v2.2.0 header. The
    real contract lives in tests/screens/test_changelog.py; this keeps the
    content assertions.
    """
    from core.changelog import CHANGELOG, notes_for

    entry = notes_for("2.2.0")
    for needle in (
        "High-RAM",
        "environment variables",
        "router",
        "Assistant",
    ):
        assert needle.lower() in entry.lower(), f"missing: {needle}"
    # Fallback contract: unknown version falls back to the NEWEST entry, by
    # version order — see notes_for's docstring for why order matters.
    newest = max(CHANGELOG, key=lambda v: tuple(int(x) for x in v.split(".")))
    assert notes_for("9.9.9") == CHANGELOG[newest]
    assert entry == CHANGELOG["2.2.0"]


def test_intercept_oauth_defaults_agree_on_true():
    import inspect

    from services.colab import ColabService, execution

    assert (
        inspect.signature(ColabService.exec_code).parameters["intercept_oauth"].default
        is True
    )
    assert (
        inspect.signature(execution.exec_code_impl)
        .parameters["intercept_oauth"]
        .default
        is True
    )


def test_wipe_list_has_no_dangling_constants():
    import inspect

    from core import constants
    from screens.settings import data_section

    src = inspect.getsource(data_section)
    # Every STORAGE_* referenced in the wipe list must still be defined.
    import re

    for name in re.findall(r"constants\.(STORAGE_[A-Z_]+)", src):
        assert hasattr(constants, name), f"dangling wipe key: {name}"
    assert "STORAGE_KEEP_ALIVE," not in src.replace(
        "STORAGE_KEEP_ALIVE_ON_DISCONNECT", ""
    )

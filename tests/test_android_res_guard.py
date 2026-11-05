"""Guard: the Android notification icon drawables must exist at every density.

Mirrors proot-distro-flet's guard (c279158): flet build copies res_dir into
the generated Android project, and a missing small icon breaks the
foreground-service notification on device.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DENSITIES = ("mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi")


def test_notification_icon_exists_at_every_density():
    for density in DENSITIES:
        path = ROOT / "android_res" / f"drawable-{density}" / "ic_stat_collabshell.png"
        assert path.exists() and path.stat().st_size > 0, f"missing {path}"


def test_pyproject_points_at_res_dir_and_declares_fgs():
    import tomllib

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    android = pyproject["tool"]["flet"]["android"]
    assert android.get("res_dir") == "android_res"
    perms = android["permission"]
    for perm in (
        "android.permission.WAKE_LOCK",
        "android.permission.FOREGROUND_SERVICE",
        "android.permission.FOREGROUND_SERVICE_SPECIAL_USE",
        "android.permission.POST_NOTIFICATIONS",
    ):
        assert perms.get(perm) is True, f"missing permission {perm}"
    svc = android["service"]["com.dexterous.flutterlocalnotifications.ForegroundService"]
    assert svc.get("foregroundServiceType") == "specialUse"
    assert android.get("legacy_packaging") is True


def test_flet_notifications_pinned_to_stable():
    import tomllib

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    deps = pyproject["project"]["dependencies"]
    assert any(d.startswith("flet-notifications==1.1.0") for d in deps)
    assert any(d == "flet==1.1.0" for d in deps)


def test_session_notify_service_mounts_without_the_package():
    """On desktop (no flet_notifications native side needed) mount must be a
    safe no-op, and FGS calls must no-op off-Android."""
    import asyncio
    import sys
    import types

    sys.path.insert(0, "src")
    from services.session_notify import SessionNotificationService

    page = types.SimpleNamespace(services=[], web=False)
    state = types.SimpleNamespace(active_session_name="s1")
    svc = SessionNotificationService(page, state)
    svc.mount()  # flet_notifications IS installed in the venv; must not raise
    assert svc.notifications is not None
    assert svc.notifications in page.services
    # Off-Android: FGS start/stop are no-ops.
    page.platform = None
    asyncio.run(svc.start_for_session("s1"))
    assert svc._fgs_running is False
    asyncio.run(svc.stop())

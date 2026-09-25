"""Repackage flet mobile-index wheels to their base PEP 440 versions.

The Android build's pip targets android_24 + cp314 and finds native wheels
only on flet's mobile index (pypi.flet.dev), where every rebuild is
published as a *post*-release: 2.46.4-1 normalizes to 2.46.4.post1. A
requirement naming the base version exactly (pydantic pins
pydantic-core==2.46.4) or our own pins (pyarrow==24.0.0) can therefore
never resolve, and the packaging step dies with ResolutionImpossible.

This downloads those wheels and republishes them locally under the base
version so pip finds them through PIP_FIND_LINKS. Nothing here changes
package contents — only the version metadata.

It also relabels one PyPI wheel for a second reason. google-colab-cli
0.7.2 requires `jupyter-kernel-client==0.8`, but 0.8 is missing the
websocket symbols its Drive-OAuth interception needs (JupyterSubprotocol,
wsclient._subprotocol, deserialize_msg_from_ws_default) — 0.9–0.15 have
them, and 0.15.0 is what our desktop runs via the uv override. The
Android packager ignores that override (it only reads project.dependencies),
so Android silently got 0.8.0 and Drive mount died there. Republishing
0.15.0 as 0.8.1 satisfies `==0.8` (which means 0.8.*) with the right code:
PyPI has no 0.8.1, so pip must take ours. Remove this entry the day
googlecolab/google-colab-cli ships a widened pin (our PR #138).
"""

from __future__ import annotations

import base64
import hashlib
import io
import pathlib
import sys
import urllib.request
import zipfile

INDEX = "https://pypi.flet.dev"
PYPI = "https://pypi.org/simple"
UA = {"User-Agent": "collabshell-ci/1.0 (+https://github.com/Nwokike/CollabShell)"}

# (wheel distribution prefix, base version, post-release as published)
SPECS = [
    ("pydantic_core", "2.46.4", "2.46.4-1"),
    ("pyarrow", "24.0.0", "24.0.0-2"),
    ("cryptography", "48.0.0", "48.0.0-10"),
]

# Relabeled from PyPI, not the mobile index: (dist, published, relabeled).
# jupyter-kernel-client is pure-Python (py3-none-any), so it needs no ABI
# wheel — only a version the Android resolver will accept.
PYPI_SPECS = [
    ("jupyter_kernel_client", "0.15.0", "0.8.1"),
]

# serious_python installs one site-packages tree per target ABI. x86_64 is
# included for the emulator build; armeabi-v7a is impossible (no pyarrow
# wheel for 32-bit exists on the mobile index).
TAGS = [
    "cp314-cp314-android_24_arm64_v8a",
    "cp314-cp314-android_24_x86_64",
]
ANY_WHEEL_TAG = "py3-none-any"


def find_wheel_url(
    dist: str, version: str, tag: str, index: str = INDEX
) -> str | None:
    filename = f"{dist}-{version}-{tag}.whl"
    req = urllib.request.Request(f"{index}/{dist}/", headers=UA)
    with urllib.request.urlopen(req, timeout=60) as resp:
        page = resp.read().decode("utf-8", "replace")
    for chunk in page.split('href="')[1:]:
        url = chunk.split('"')[0].split("#")[0]
        if url.rsplit("/", 1)[-1] == filename:
            return url
    return None


def repackage(wheel_bytes: bytes, dist: str, base: str) -> bytes:
    src = zipfile.ZipFile(io.BytesIO(wheel_bytes))
    new_info = f"{dist}-{base}.dist-info"
    renamed: dict[str, str] = {}
    bodies: dict[str, bytes] = {}
    record_name = f"{new_info}/RECORD"

    for info in src.infolist():
        name = info.filename
        if ".dist-info/" in name:
            _, _, tail = name.partition(".dist-info/")
            name = f"{new_info}/{tail}"
        if name.endswith(".dist-info/METADATA"):
            lines = []
            for line in src.read(info).decode("utf-8").splitlines(keepends=True):
                lines.append(
                    f"Version: {base}\n" if line.startswith("Version:") else line
                )
            body = "".join(lines).encode("utf-8")
        else:
            body = src.read(info)
        renamed[name] = name
        bodies[name] = body

    bodies.pop(record_name, None)

    record_lines = []
    for name, body in bodies.items():
        digest = (
            base64.urlsafe_b64encode(hashlib.sha256(body).digest())
            .rstrip(b"=")
            .decode()
        )
        record_lines.append(f"{name},sha256={digest},{len(body)}\n")
    record_lines.append(f"{record_name},,\n")
    bodies[record_name] = "".join(record_lines).encode("utf-8")

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for name, body in bodies.items():
            dst.writestr(name, body)
    return out.getvalue()


def main() -> int:
    out_dir = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "wheels")
    out_dir.mkdir(parents=True, exist_ok=True)
    def _one(dist: str, published: str, base: str, tag: str, index: str) -> None:
        url = find_wheel_url(dist, published, tag, index)
        if not url:
            print(f"WARN {dist} {published} {tag}: not found on {index}")
            return
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = resp.read()
        fixed = repackage(data, dist, base)
        name = f"{dist}-{base}-{tag}.whl"
        (out_dir / name).write_bytes(fixed)
        print(f"OK {name}")

    for dist, base, post in SPECS:
        for tag in TAGS:
            try:
                _one(dist, post, base, tag, INDEX)
            except Exception as exc:  # keep going; the build log shows misses
                print(f"WARN {dist} {post} {tag}: {type(exc).__name__}: {exc}")

    for dist, published, base in PYPI_SPECS:
        try:
            _one(dist, published, base, ANY_WHEEL_TAG, PYPI)
        except Exception as exc:
            print(f"WARN {dist} {published}: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
UA = {"User-Agent": "collabshell-ci/1.0 (+https://github.com/Nwokike/CollabShell)"}

# (wheel distribution prefix, base version, post-release as published)
SPECS = [
    ("pydantic_core", "2.46.4", "2.46.4-1"),
    ("pyarrow", "24.0.0", "24.0.0-2"),
    ("cryptography", "48.0.0", "48.0.0-10"),
]

# serious_python installs one site-packages tree per target ABI (arm64 only:
# the mobile index has no armeabi-v7a pyarrow wheel, so 32-bit cannot
# resolve google-colab-cli's tree).
TAGS = ["cp314-cp314-android_24_arm64_v8a"]


def find_wheel_url(dist: str, version: str, tag: str) -> str | None:
    filename = f"{dist}-{version}-{tag}.whl"
    req = urllib.request.Request(f"{INDEX}/{dist}/", headers=UA)
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
                lines.append(f"Version: {base}\n" if line.startswith("Version:") else line)
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
    for dist, base, post in SPECS:
        for tag in TAGS:
            try:
                url = find_wheel_url(dist, post, tag)
                if not url:
                    print(f"WARN {dist} {post} {tag}: not on mobile index")
                    continue
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=300) as resp:
                    data = resp.read()
                fixed = repackage(data, dist, base)
                name = f"{dist}-{base}-{tag}.whl"
                (out_dir / name).write_bytes(fixed)
                print(f"OK {name}")
            except Exception as exc:  # keep going; the build log shows misses
                print(f"WARN {dist} {post} {tag}: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

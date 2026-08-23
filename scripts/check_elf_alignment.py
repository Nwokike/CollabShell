#!/usr/bin/env python3
"""Verify Google Play's 16 KB memory page-size requirement on an Android artifact.

Usage:
    python scripts/check_elf_alignment.py <path.aab | path.apk> [more artifacts...]

Extracts every ``*.so`` from the artifact (AAB/APK are zip containers) and
checks the ``p_align`` of each ``PT_LOAD`` program header. Google Play rejects
uploads where any 64-bit library (arm64-v8a, x86_64) has a PT_LOAD segment
aligned below 16384 (16 KB). 32-bit ABIs are reported as warnings only.

Exits non-zero if any 64-bit library is misaligned, so it can gate CI.
"""

from __future__ import annotations

import struct
import sys
import tempfile
import zipfile
from pathlib import Path

PT_LOAD = 1
PAGE_16K = 16384
ABI_64_BIT = {"arm64-v8a", "x86_64"}


def load_segment_alignments(path: Path) -> list[int] | None:
    """Return p_align values of all PT_LOAD segments, or None if not ELF."""
    with path.open("rb") as f:
        ident = f.read(16)
        if ident[:4] != b"\x7fELF":
            return None
        is64 = ident[4] == 2
        if is64:
            f.seek(0x20)
            (e_phoff,) = struct.unpack("<Q", f.read(8))
            f.seek(0x36)
            e_phentsize, e_phnum = struct.unpack("<HH", f.read(4))
        else:
            f.seek(0x1C)
            (e_phoff,) = struct.unpack("<I", f.read(4))
            f.seek(0x2A)
            e_phentsize, e_phnum = struct.unpack("<HH", f.read(4))
        aligns: list[int] = []
        for i in range(e_phnum):
            f.seek(e_phoff + i * e_phentsize)
            ph = f.read(e_phentsize)
            if is64:
                (p_type,) = struct.unpack("<I", ph[:4])
                (p_align,) = struct.unpack("<Q", ph[48:56])
            else:
                (p_type,) = struct.unpack("<I", ph[:4])
                (p_align,) = struct.unpack("<I", ph[28:32])
            if p_type == PT_LOAD:
                aligns.append(p_align)
        return aligns


def check_artifact(artifact: Path) -> bool:
    """Check one .aab/.apk; return True when it passes the 16 KB requirement."""
    print(f"\n=== {artifact.name} ===")
    ok = True
    count = 0
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(artifact) as zf:
            so_names = [n for n in zf.namelist() if n.endswith(".so")]
            zf.extractall(tmp, members=so_names)
        for name in sorted(so_names):
            lib = Path(tmp) / name
            aligns = load_segment_alignments(lib)
            if aligns is None:
                print(f"?    {name} (not an ELF)")
                continue
            count += 1
            worst = min(aligns)
            abi = next((a for a in ABI_64_BIT if f"/{a}/" in name), None)
            if abi and worst < PAGE_16K:
                print(
                    f"FAIL {name}  p_aligns={sorted(set(aligns))} (64-bit ABI below 16 KB)"
                )
                ok = False
            elif not abi and worst < PAGE_16K:
                print(
                    f"warn {name}  p_aligns={sorted(set(aligns))} (32-bit ABI, exempt)"
                )
            else:
                print(f"ok   {name}  p_aligns={sorted(set(aligns))}")
    print(
        f"\n{count} native libraries checked in {artifact.name}: {'PASS' if ok else 'FAIL'}"
    )
    return ok


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    results = [check_artifact(Path(p)) for p in argv[1:]]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

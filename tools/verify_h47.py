"""Verifier for H47: native fixed19 full 2-digit (`00..80`) Mini-Lisp REPL."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.native_lisp_num80 import build_lisp_num80, reference as num80_ref

BUILD = ROOT / "build"


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _run(vm: Path, image: Path, stdin: bytes) -> bytes:
    proc = subprocess.run([str(vm), str(image)], input=stdin, capture_output=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"{vm.name} failed ({proc.returncode}) on {image.name}")
    return proc.stdout


def main() -> int:
    vms = [BUILD / "bolge19", BUILD / "fast20"]
    for vm in vms:
        if not vm.exists():
            raise SystemExit(f"missing VM binary: {vm}")

    h47 = build_lisp_num80(rounds=3)
    p47 = BUILD / "test_h47_lisp_num80.mb"
    p47.write_bytes(h47.image)
    in47 = b"(+ 12 34)(- 50 17)(* 07 09)(= 42 42)(< 19 20)"
    exp47 = num80_ref(in47)
    for vm in vms:
        assert _run(vm, p47, in47) == exp47 == b"4633630101"

    report = {
        "H47_lisp_num80": {
            "lowering": h47.lowering,
            "cells": len(h47.image),
            "max_byte": max(h47.image),
            "sha256": _sha256(h47.image),
            "stdout": exp47.decode("ascii"),
        }
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

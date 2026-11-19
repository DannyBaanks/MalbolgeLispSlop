"""Verifier for H50: native fixed19 integrated Mini-Lisp VM v2."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.native_lisp_v2 import build_lisp_v2, reference as v2_ref

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

    h50 = build_lisp_v2(rounds=3)
    p50 = BUILD / "test_h50_lisp_v2.mb"
    p50.write_bytes(h50.image)
    in50 = b"(s x 3)(w 2 7)(+ 1 1)(r ! _)(* ! x)(D + .)(C ! 2)(S 3 _)"
    exp50 = v2_ref(in50)
    for vm in vms:
        assert _run(vm, p50, in50) == exp50 == b"3727E.06"

    report = {
        "H50_lisp_v2": {
            "lowering": h50.lowering,
            "cells": len(h50.image),
            "max_byte": max(h50.image),
            "sha256": _sha256(h50.image),
            "stdout": exp50.decode("ascii"),
        }
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

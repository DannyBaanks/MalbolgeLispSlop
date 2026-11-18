"""Verifier for H40: native fixed19 integrated Mini-Lisp REPL."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.native_lisp_v1 import build_lisp_v1, reference as v1_ref

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

    h40 = build_lisp_v1(rounds=3)
    p40 = BUILD / "test_h40_lisp_v1.mb"
    p40.write_bytes(h40.image)
    in40 = b"(s x 3)(s y 4)(* 2 x)(= ! 6)(< y x)(s z !)(+ x z)"
    exp40 = v1_ref(in40)
    for vm in vms:
        assert _run(vm, p40, in40) == exp40 == b"3461003"

    report = {
        "H40_lisp_v1": {
            "lowering": h40.lowering,
            "cells": len(h40.image),
            "max_byte": max(h40.image),
            "sha256": _sha256(h40.image),
            "stdout": exp40.decode("ascii"),
        }
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

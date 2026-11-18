"""Verifier for H33: native fixed19 conditional `(if (= a b) x y)` and `(if (< a b) x y)` REPL."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.native_lisp_if import build_lisp_if, reference as if_ref

BUILD = ROOT / "build"


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _run(vm: Path, image: Path, stdin: bytes) -> bytes:
    proc = subprocess.run([str(vm), str(image)], input=stdin, capture_output=True, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"{vm.name} failed ({proc.returncode}) on {image.name}")
    return proc.stdout


def main() -> int:
    vms = [BUILD / "bolge19", BUILD / "fast20"]
    for vm in vms:
        if not vm.exists():
            raise SystemExit(f"missing VM binary: {vm}")

    h33 = build_lisp_if(rounds=3)
    p33 = BUILD / "test_h33_lisp_if.mb"
    p33.write_bytes(h33.image)
    in33 = b"(if (= 3 3) 7 2)(if (= 3 4) 7 2)(if (< 2 5) 9 1)(if (< 5 2) 9 1)(if (< 4 4) 9 1)\x00"
    exp33 = if_ref(in33)
    for vm in vms:
        assert _run(vm, p33, in33) == exp33 == b"72911"

    report = {
        "H33_lisp_if": {
            "lowering": h33.lowering,
            "cells": len(h33.image),
            "max_byte": max(h33.image),
            "sha256": _sha256(h33.image),
            "stdout": exp33.decode("ascii"),
        }
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

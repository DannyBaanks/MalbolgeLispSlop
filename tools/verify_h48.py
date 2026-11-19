"""Verifier for H48: native fixed19 streaming nested S-expression evaluator v2."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.native_lisp_stream_v2 import build_lisp_stream_v2, reference as stream_ref

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

    h48 = build_lisp_stream_v2(rounds=3)
    p48 = BUILD / "test_h48_lisp_stream_v2.mb"
    p48.write_bytes(h48.image)
    in48 = b"(+ (* 2 3) (- 9 (+ 1 2)))"
    exp48 = stream_ref(in48)
    for vm in vms:
        assert _run(vm, p48, in48) == exp48 == b"<"

    report = {
        "H48_lisp_stream_v2": {
            "lowering": h48.lowering,
            "cells": len(h48.image),
            "max_byte": max(h48.image),
            "sha256": _sha256(h48.image),
            "stdout": exp48.decode("ascii"),
        }
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Verifier for H38: native fixed19 streaming S-expression evaluator with stack."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.native_lisp_stack import build_lisp_stack, reference as stack_ref

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

    h38 = build_lisp_stack(rounds=3)
    p38 = BUILD / "test_h38_lisp_stack.mb"
    p38.write_bytes(h38.image)
    in38 = b"(+ (+ 1 (+ 2 3)) (- 9 6))"
    exp38 = stack_ref(in38)
    for vm in vms:
        assert _run(vm, p38, in38) == exp38 == b"9"

    report = {
        "H38_lisp_stack": {
            "lowering": h38.lowering,
            "cells": len(h38.image),
            "max_byte": max(h38.image),
            "sha256": _sha256(h38.image),
            "stdout": exp38.decode("ascii"),
        }
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

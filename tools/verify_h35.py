"""Verifier for H35: native fixed19 `(+ a b)`, `(- a b)`, and `(* a b)` REPL."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.native_lisp_mul import build_lisp_mul, reference as mul_ref

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

    h35 = build_lisp_mul(rounds=5)
    p35 = BUILD / "test_h35_lisp_mul.mb"
    p35.write_bytes(h35.image)
    in35 = b"(* 0 9)(* 6 7)(+ 9 9)(- 5 5)(* 3 8)\x00"
    exp35 = mul_ref(in35)
    for vm in vms:
        assert _run(vm, p35, in35) == exp35 == b"0042180024"

    report = {
        "H35_lisp_mul": {
            "lowering": h35.lowering,
            "cells": len(h35.image),
            "max_byte": max(h35.image),
            "sha256": _sha256(h35.image),
            "stdout": exp35.decode("ascii"),
        }
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

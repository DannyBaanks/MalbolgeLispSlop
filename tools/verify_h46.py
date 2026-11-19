"""Verifier for H46: native fixed19 2-arg user-defined functions (`def`/`call`) Mini-Lisp REPL."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.native_lisp_fn2 import build_lisp_fn2, reference as fn2_ref

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

    h46 = build_lisp_fn2(rounds=3)
    p46 = BUILD / "test_h46_lisp_fn2.mb"
    p46.write_bytes(h46.image)
    in46 = b"(D + .)(C 3 4)(D * 2)(C ! 0)"
    exp46 = fn2_ref(in46)
    for vm in vms:
        assert _run(vm, p46, in46) == exp46 == b".724"

    report = {
        "H46_lisp_fn2": {
            "lowering": h46.lowering,
            "cells": len(h46.image),
            "max_byte": max(h46.image),
            "sha256": _sha256(h46.image),
            "stdout": exp46.decode("ascii"),
        }
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

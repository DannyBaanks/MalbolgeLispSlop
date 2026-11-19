"""Verifier for H44: native fixed19 internal-loop `fact(n)`, `fib(n)`, `sum(n)` Mini-Lisp REPL."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.native_lisp_rec import build_lisp_rec, reference as rec_ref

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

    h44 = build_lisp_rec(rounds=3)
    p44 = BUILD / "test_h44_lisp_rec.mb"
    p44.write_bytes(h44.image)
    in44 = b"(F 4 _)(B 6 _)(S 3 _)(+ 1 2)(F ! _)"
    exp44 = rec_ref(in44)
    for vm in vms:
        assert _run(vm, p44, in44) == exp44 == b"H8636"

    report = {
        "H44_lisp_rec": {
            "lowering": h44.lowering,
            "cells": len(h44.image),
            "max_byte": max(h44.image),
            "sha256": _sha256(h44.image),
            "stdout": exp44.decode("ascii"),
        }
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

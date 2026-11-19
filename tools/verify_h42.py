"""Verifier for H42: native fixed19 pointer-based `cons`/`car`/`cdr` heap Mini-Lisp REPL."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.native_lisp_cons import build_lisp_cons, reference as cons_ref

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

    h42 = build_lisp_cons(rounds=3)
    p42 = BUILD / "test_h42_lisp_cons.mb"
    p42.write_bytes(h42.image)
    in42 = b"(c 5 0)(c 7 !)(a ! _)(d 1 _)(a ! _)"
    exp42 = cons_ref(in42)
    for vm in vms:
        assert _run(vm, p42, in42) == exp42 == b"01705"

    report = {
        "H42_lisp_cons": {
            "lowering": h42.lowering,
            "cells": len(h42.image),
            "max_byte": max(h42.image),
            "sha256": _sha256(h42.image),
            "stdout": exp42.decode("ascii"),
        }
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

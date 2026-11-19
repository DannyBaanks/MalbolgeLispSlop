"""Verifier for H43: native fixed19 internal conditional loop (`(S n _)` sum 1..n) Mini-Lisp REPL."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.native_lisp_loop import build_lisp_loop, reference as loop_ref

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

    h43 = build_lisp_loop(rounds=3)
    p43 = BUILD / "test_h43_lisp_loop.mb"
    p43.write_bytes(h43.image)
    in43 = b"(+ 1 2)(S ! _)(- ! 1)(S 0 _)"
    exp43 = loop_ref(in43)
    for vm in vms:
        assert _run(vm, p43, in43) == exp43 == b"3650"

    report = {
        "H43_lisp_loop": {
            "lowering": h43.lowering,
            "cells": len(h43.image),
            "max_byte": max(h43.image),
            "sha256": _sha256(h43.image),
            "stdout": exp43.decode("ascii"),
        }
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

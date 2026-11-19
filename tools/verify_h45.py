"""Verifier for H45: native fixed19 Call/Data Stack (`push`/`pop`/`top`) Mini-Lisp REPL."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.native_lisp_stack_ops import build_lisp_stack_ops, reference as stack_ref

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

    h45 = build_lisp_stack_ops(rounds=3)
    p45 = BUILD / "test_h45_lisp_stack_ops.mb"
    p45.write_bytes(h45.image)
    in45 = b"(u 5 _)(u 7 _)(t _ _)(o _ _)(o _ _)"
    exp45 = stack_ref(in45)
    for vm in vms:
        assert _run(vm, p45, in45) == exp45 == b"57775"

    report = {
        "H45_lisp_stack_ops": {
            "lowering": h45.lowering,
            "cells": len(h45.image),
            "max_byte": max(h45.image),
            "sha256": _sha256(h45.image),
            "stdout": exp45.decode("ascii"),
        }
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

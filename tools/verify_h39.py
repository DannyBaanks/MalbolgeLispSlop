"""Verifier for H39: native fixed19 user-defined 1-arg functions (`fn` / `ap`) REPL."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.native_lisp_fn import build_lisp_fn, reference as fn_ref

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

    h39 = build_lisp_fn(rounds=3)
    p39 = BUILD / "test_h39_lisp_fn.mb"
    p39.write_bytes(h39.image)
    in39 = b"(fn * x 3)(ap f 2 0)(fn + x 1)(ap f ! 0)(fn - x 4)(ap f ! 0)\x00"
    exp39 = fn_ref(in39)
    for vm in vms:
        assert _run(vm, p39, in39) == exp39 == b"361743"

    report = {
        "H39_lisp_fn": {
            "lowering": h39.lowering,
            "cells": len(h39.image),
            "max_byte": max(h39.image),
            "sha256": _sha256(h39.image),
            "stdout": exp39.decode("ascii"),
        }
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

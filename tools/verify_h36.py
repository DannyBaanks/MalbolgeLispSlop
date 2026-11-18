"""Verifier for H36: native fixed19 named-variable Lisp REPL (`x`, `y`, `z`, `=`, `+`, `-`)."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.native_lisp_env import build_lisp_env, reference as env_ref

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

    h36 = build_lisp_env(rounds=3)
    p36 = BUILD / "test_h36_lisp_env.mb"
    p36.write_bytes(h36.image)
    in36 = b"(= x 5)(= y 3)(+ x y)(= z x)(- z 2)"
    exp36 = env_ref(in36)
    for vm in vms:
        assert _run(vm, p36, in36) == exp36 == b"53853"

    report = {
        "H36_lisp_env": {
            "lowering": h36.lowering,
            "cells": len(h36.image),
            "max_byte": max(h36.image),
            "sha256": _sha256(h36.image),
            "stdout": exp36.decode("ascii"),
        }
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Verifier for H49: native fixed19 code-as-data AST-heap `eval` Mini-Lisp REPL."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.native_lisp_eval import build_lisp_eval, reference as eval_ref

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

    h49 = build_lisp_eval(rounds=3)
    p49 = BUILD / "test_h49_lisp_eval.mb"
    p49.write_bytes(h49.image)
    in49 = b"(p 0 +)(l 0 3)(r 0 4)(e 0 _)(p 1 *)(l 1 7)(r 1 2)(e 1 _)"
    exp49 = eval_ref(in49)
    for vm in vms:
        assert _run(vm, p49, in49) == exp49 == b"+347*72>"

    report = {
        "H49_lisp_eval": {
            "lowering": h49.lowering,
            "cells": len(h49.image),
            "max_byte": max(h49.image),
            "sha256": _sha256(h49.image),
            "stdout": exp49.decode("ascii"),
        }
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

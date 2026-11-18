"""Verifier for H31..H32: native fixed19 stateful (`!`) and nested Lisp S-expression loops."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.native_lisp_nested import build_lisp_nested, reference as nested_ref
from slopsynth.native_lisp_state import build_lisp_state, reference as state_ref

BUILD = ROOT / "build"


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _run(vm: Path, image: Path, stdin: bytes) -> bytes:
    proc = subprocess.run([str(vm), str(image)], input=stdin, capture_output=True, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"{vm.name} failed ({proc.returncode}) on {image.name}")
    return proc.stdout


def main() -> int:
    vms = [BUILD / "bolge19", BUILD / "fast20"]
    for vm in vms:
        if not vm.exists():
            raise SystemExit(f"missing VM binary: {vm}")

    report = {}

    # H31: Stateful REPL loop with ANS ('!')
    h31 = build_lisp_state(rounds=3)
    p31 = BUILD / "test_h31_lisp_state.mb"
    p31.write_bytes(h31.image)
    in31 = b"(+ 2 3)(+ ! 4)(- ! 2)(+ 1 !)(- ! !)"
    exp31 = state_ref(in31)
    for vm in vms:
        assert _run(vm, p31, in31) == exp31 == b"59780"
    report["H31_lisp_state"] = {
        "lowering": h31.lowering,
        "cells": len(h31.image),
        "max_byte": max(h31.image),
        "sha256": _sha256(h31.image),
        "stdout": exp31.decode("ascii"),
    }

    # H32: Depth-2 nested S-expression evaluator loop
    h32 = build_lisp_nested(rounds=3)
    p32 = BUILD / "test_h32_lisp_nested.mb"
    p32.write_bytes(h32.image)
    in32 = b"(+ 2 (- 9 4))(- (+ 3 6) 4)(+ (+ 1 2) 5)(- 9 (- 5 2))\x00"
    exp32 = nested_ref(in32)
    for vm in vms:
        assert _run(vm, p32, in32) == exp32 == b"7586"
    report["H32_lisp_nested"] = {
        "lowering": h32.lowering,
        "cells": len(h32.image),
        "max_byte": max(h32.image),
        "sha256": _sha256(h32.image),
        "stdout": exp32.decode("ascii"),
    }

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

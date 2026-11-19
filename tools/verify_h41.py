"""Verifier for H41: native fixed19 dynamic indexed memory (`PEEK`/`POKE`) Mini-Lisp REPL."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.native_lisp_mem import build_lisp_mem, reference as mem_ref

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

    h41 = build_lisp_mem(rounds=3)
    p41 = BUILD / "test_h41_lisp_mem.mb"
    p41.write_bytes(h41.image)
    in41 = b"(w 0 5)(w 3 7)(+ 1 2)(r ! _)(+ 1 2)(w ! 9)(r 3 _)(- ! 2)(= ! 7)"
    exp41 = mem_ref(in41)
    for vm in vms:
        assert _run(vm, p41, in41) == exp41 == b"573739971"

    report = {
        "H41_lisp_mem": {
            "lowering": h41.lowering,
            "cells": len(h41.image),
            "max_byte": max(h41.image),
            "sha256": _sha256(h41.image),
            "stdout": exp41.decode("ascii"),
        }
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

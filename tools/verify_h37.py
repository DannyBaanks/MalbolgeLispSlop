"""Verifier for H37: native fixed19 `cons` (`c`), `car` (`a`), `cdr` (`d`) list REPL."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.native_lisp_lists import build_lisp_lists, reference as lists_ref

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

    h37 = build_lisp_lists(rounds=3)
    p37 = BUILD / "test_h37_lisp_lists.mb"
    p37.write_bytes(h37.image)
    in37 = b"(c 7 0)(c 5 0)(c 3 0)(a 0 0)(d 0 0)(a 0 0)(d 0 0)(a 0 0)(d 0 0)\x00"
    exp37 = lists_ref(in37)
    for vm in vms:
        assert _run(vm, p37, in37) == exp37 == b"753355770"

    report = {
        "H37_lisp_lists": {
            "lowering": h37.lowering,
            "cells": len(h37.image),
            "max_byte": max(h37.image),
            "sha256": _sha256(h37.image),
            "stdout": exp37.decode("ascii"),
        }
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

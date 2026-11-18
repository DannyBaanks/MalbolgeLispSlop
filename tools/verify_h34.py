"""Verifier for H34: native fixed19 multi-digit `(+ ab cd)` and `(- ab cd)` REPL."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.native_lisp_multidigit import build_lisp_multidigit, reference as md_ref

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

    h34 = build_lisp_multidigit(rounds=5)
    p34 = BUILD / "test_h34_lisp_multidigit.mb"
    p34.write_bytes(h34.image)
    in34 = b"(+ 12 34)(+ 99 99)(- 50 17)(- 09 09)(+ 00 00)(- 99 01)\x00"
    exp34 = md_ref(in34)
    for vm in vms:
        assert _run(vm, p34, in34) == exp34 == b"046198033000000098"

    report = {
        "H34_lisp_multidigit": {
            "lowering": h34.lowering,
            "cells": len(h34.image),
            "max_byte": max(h34.image),
            "sha256": _sha256(h34.image),
            "stdout": exp34.decode("ascii"),
        }
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

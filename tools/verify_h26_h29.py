"""Verifier for H26..H29: native fixed19 store, carry-add, Fibonacci, and Lisp REPL loops."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.native_carry_loop import build_carry_loop, reference as carry_ref
from slopsynth.native_fib_loop import build_fib_loop, reference as fib_ref
from slopsynth.native_lisp_add_sub import build_lisp_add_sub, reference as add_sub_ref
from slopsynth.native_lisp_repl import build_lisp_repl, reference as repl_ref
from slopsynth.native_store import build_store_loop, reference as store_ref
BUILD = ROOT / "build"


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _run(vm: Path, image: Path, stdin: bytes) -> bytes:
    proc = subprocess.run([str(vm), str(image)], input=stdin, capture_output=True, timeout=20)
    if proc.returncode != 0:
        raise RuntimeError(f"{vm.name} failed ({proc.returncode}) on {image.name}")
    return proc.stdout


def main() -> int:
    vms = [BUILD / "bolge19", BUILD / "fast20"]
    for vm in vms:
        if not vm.exists():
            raise SystemExit(f"missing VM binary: {vm}")

    report = {}

    # H26: Universal store shift-register loop
    h26 = build_store_loop()
    p26 = BUILD / "test_h26_store.mb"
    p26.write_bytes(h26.image)
    in26 = b"\x01A\x01B\x01C\x01D\x00"
    exp26 = store_ref(in26)
    for vm in vms:
        assert _run(vm, p26, in26) == exp26 == b"*ABC"
    report["H26_store_loop"] = {
        "lowering": h26.lowering,
        "cells": len(h26.image),
        "max_byte": max(h26.image),
        "sha256": _sha256(h26.image),
        "stdout": exp26.decode("ascii"),
    }

    # H27: Carry-addition accumulator loop
    h27 = build_carry_loop(rounds=3)
    p27 = BUILD / "test_h27_carry.mb"
    p27.write_bytes(h27.image)
    in27 = b"\x01\x05\x01\x07\x01\x0a\x01\x14\x00"
    exp27 = carry_ref(in27, rounds=3)
    for vm in vms:
        assert _run(vm, p27, in27) == exp27 == bytes([5, 12, 22, 42])
    report["H27_carry_loop"] = {
        "lowering": h27.lowering,
        "cells": len(h27.image),
        "max_byte": max(h27.image),
        "sha256": _sha256(h27.image),
        "stdout_bytes": list(exp27),
    }

    # H28: Iterative Fibonacci loop
    h28 = build_fib_loop(rounds=4)
    p28 = BUILD / "test_h28_fib.mb"
    p28.write_bytes(h28.image)
    in28 = b"\x01" * 13 + b"\x00"
    exp28 = fib_ref(in28, rounds=4)
    for vm in vms:
        assert _run(vm, p28, in28) == exp28 == bytes([1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233])
    report["H28_fib_loop"] = {
        "lowering": h28.lowering,
        "cells": len(h28.image),
        "max_byte": max(h28.image),
        "sha256": _sha256(h28.image),
        "stdout_bytes": list(exp28),
    }

    # H29: Lisp S-expression REPL loop
    h29 = build_lisp_repl(rounds=3)
    p29 = BUILD / "test_h29_lisp_repl.mb"
    p29.write_bytes(h29.image)
    in29 = b"(+ 2 3)(+ 4 5)(+ 1 7)(+ 0 9)"
    exp29 = repl_ref(in29)
    for vm in vms:
        assert _run(vm, p29, in29) == exp29 == b"5989"
    report["H29_lisp_repl"] = {
        "lowering": h29.lowering,
        "cells": len(h29.image),
        "max_byte": max(h29.image),
        "sha256": _sha256(h29.image),
        "stdout": exp29.decode("ascii"),
    }

    # H30: Multi-operator (+ a b) / (- a b) Lisp S-expression REPL loop
    h30 = build_lisp_add_sub(rounds=3)
    p30 = BUILD / "test_h30_lisp_add_sub.mb"
    p30.write_bytes(h30.image)
    in30 = b"(+ 2 3)(- 9 4)(+ 1 7)(- 8 8)"
    exp30 = add_sub_ref(in30)
    for vm in vms:
        assert _run(vm, p30, in30) == exp30 == b"5580"
    report["H30_lisp_add_sub"] = {
        "lowering": h30.lowering,
        "cells": len(h30.image),
        "max_byte": max(h30.image),
        "sha256": _sha256(h30.image),
        "stdout": exp30.decode("ascii"),
    }

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

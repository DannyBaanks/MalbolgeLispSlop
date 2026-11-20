"""Tests for H54: native fixed19 streaming depth-3 Mini-Lisp VM v6 (vars x/p/u + logic A/O/N)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_lisp_v6 import build_lisp_v6, reference as v6_ref

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
VMS = [vm for vm in (BUILD / "bolge19", BUILD / "fast20") if vm.exists()]


def _run_vm(vm: Path, image: Path, stdin: bytes) -> bytes:
    proc = subprocess.run([str(vm), str(image)], input=stdin, capture_output=True, timeout=60)
    assert proc.returncode == 0, f"{vm.name} failed ({proc.returncode}): {proc.stderr!r}"
    return proc.stdout


@pytest.mark.parametrize(
    "stdin,expected",
    [
        (b"", b""),
        (b"\x00", b""),
        (b"(s x 2)(s p 3)(s u 4)(+ x (+ p u))", b"2349"),
        (b"(A 1 2)(A 0 2)(O 0 0)(O 0 5)(N 0 _)(N 3 _)", b"100110"),
        (b"(s p 5)(N (= p 4) _)(? (A (> p 3) !) (+ p 2) 0)", b"517"),
        (b"(c p u)(s x 8)(a 0 _)(+ x (d 0 _))", b"0808"),
    ],
)
def test_h54_lisp_v6_vars_logic(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_v6(rounds=3)
    assert max(artifact.image) < 128
    assert v6_ref(stdin) == expected
    img_path = BUILD / "test_h54_lisp_v6.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected

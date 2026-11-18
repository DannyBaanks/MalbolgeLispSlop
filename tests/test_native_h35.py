"""Tests for H35: native fixed19 `(+ a b)`, `(- a b)`, and `(* a b)` REPL."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_lisp_mul import build_lisp_mul, reference as mul_ref

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
        (b"(+ 8 7)", b"15"),
        (b"(- 9 2)", b"07"),
        (b"(* 9 9)", b"81"),
        (b"(* 0 9)(* 6 7)(+ 9 9)(- 5 5)(* 3 8)\x00", b"0042180024"),
        (b"(* 7 8)(+ 0 0)(- 9 0)(* 1 9)", b"56000909"),
    ],
)
def test_h35_lisp_mul_loop(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_mul(rounds=5)
    assert max(artifact.image) < 128
    assert mul_ref(stdin) == expected
    img_path = BUILD / "test_h35_lisp_mul.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected

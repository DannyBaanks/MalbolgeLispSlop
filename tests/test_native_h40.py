"""Tests for H40: native fixed19 integrated Mini-Lisp REPL (`+`, `-`, `*`, `=`, `<`, `s`, `x/y/z`, `!`)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_lisp_v1 import build_lisp_v1, reference as v1_ref

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
        (b"(s x 3)(s y 4)(* 2 x)(= ! 6)(< y x)(s z !)(+ x z)", b"3461003"),
        (b"(s x 5)(s y 2)(- x y)(+ ! x)(= ! 8)(< x 9)(* x !)\x00", b"5238115"),
        (b"(+ x y)(= x y)(< x 1)(s x 7)(= x 7)(< 2 x)(* 1 x)", b"0117117"),
    ],
)
def test_h40_lisp_v1_loop(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_v1(rounds=3)
    assert max(artifact.image) < 128
    assert v1_ref(stdin) == expected
    img_path = BUILD / "test_h40_lisp_v1.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected

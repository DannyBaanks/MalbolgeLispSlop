"""Tests for H38: native fixed19 streaming S-expression evaluator with stack."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_lisp_stack import build_lisp_stack, reference as stack_ref

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
        (b"(+ 2 3)", b"5"),
        (b"(+ 1 (+ 2 3))", b"6"),
        (b"(+ (+ 2 3) 1)", b"6"),
        (b"(- (+ 3 6) (- 5 2))", b"6"),
        (b"(+ (+ 1 (+ 2 3)) (- 9 6))", b"9"),
        (b"(+ (- (+ 1 2) 1) (+ 3 4))\x00", b"9"),
    ],
)
def test_h38_lisp_stack_loop(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_stack(rounds=3)
    assert max(artifact.image) < 128
    assert stack_ref(stdin) == expected
    img_path = BUILD / "test_h38_lisp_stack.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected

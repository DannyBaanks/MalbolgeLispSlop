"""Tests for H31..H32: native fixed19 stateful Lisp REPL (`!`) and nested S-expression evaluator."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_lisp_nested import build_lisp_nested, reference as nested_ref
from slopsynth.native_lisp_state import build_lisp_state, reference as state_ref

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
VMS = [vm for vm in (BUILD / "bolge19", BUILD / "fast20") if vm.exists()]


def _run_vm(vm: Path, image: Path, stdin: bytes) -> bytes:
    proc = subprocess.run([str(vm), str(image)], input=stdin, capture_output=True, timeout=30)
    assert proc.returncode == 0, f"{vm.name} failed ({proc.returncode}): {proc.stderr!r}"
    return proc.stdout


@pytest.mark.parametrize(
    "stdin,expected",
    [
        (b"", b""),
        (b"\x00", b""),
        (b"(+ ! 5)(- 9 !)(+ ! !)(- ! 3)\x00", b"5485"),
        (b"(+ 2 3)(+ ! 4)(- ! 2)(+ 1 !)(- ! !)", b"59780"),
        (b"(- 8 3)(+ 2 !)(- ! 1)\x00", b"576"),
    ],
)
def test_h31_lisp_state_loop(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_state(rounds=3)
    assert max(artifact.image) < 128
    assert state_ref(stdin) == expected
    img_path = BUILD / "test_h31_lisp_state.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected


@pytest.mark.parametrize(
    "stdin,expected",
    [
        (b"", b""),
        (b"\x00", b""),
        (b"(+ 2 (- 9 4))", b"7"),
        (b"(- (+ 3 6) 4)", b"5"),
        (b"(+ 1 (+ 2 3))(- 9 (- 5 2))(+ (- 8 3) 4)(- (+ 4 4) 1)", b"6697"),
        (b"(+ 2 (- 9 4))(- (+ 3 6) 4)(+ (+ 1 2) 5)(- 9 (- 5 2))\x00", b"7586"),
        (b"(- (- 9 2) 3)(+ 1 (+ 2 3))", b"46"),
    ],
)
def test_h32_lisp_nested_loop(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_nested(rounds=3)
    assert max(artifact.image) < 128
    assert nested_ref(stdin) == expected
    img_path = BUILD / "test_h32_lisp_nested.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected

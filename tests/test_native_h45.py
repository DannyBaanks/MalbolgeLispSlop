"""Tests for H45: native fixed19 Call/Data Stack (`push`/`pop`/`top`) Mini-Lisp REPL."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_lisp_stack_ops import build_lisp_stack_ops, reference as stack_ref

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
        (b"(u 5 _)(u 7 _)(t _ _)(o _ _)(o _ _)", b"57775"),
        (b"(u 3 _)(u 4 _)(o _ _)(+ ! 2)(u ! _)(t _ _)(o _ _)(o _ _)", b"34466663"),
        (b"(u 9 _)(u 2 _)(- ! 1)(u ! _)(o _ _)(o _ _)(o _ _)\x00", b"9211129"),
    ],
)
def test_h45_lisp_stack_ops_loop(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_stack_ops(rounds=3)
    assert max(artifact.image) < 128
    assert stack_ref(stdin) == expected
    img_path = BUILD / "test_h45_lisp_stack_ops.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected

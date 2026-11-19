"""Tests for H47: native fixed19 full 2-digit (`00..80`) Mini-Lisp REPL."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_lisp_num80 import build_lisp_num80, reference as num80_ref

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
        (b"(+ 12 34)(- 50 17)(* 07 09)(= 42 42)(< 19 20)", b"4633630101"),
        (b"(+ 70 20)(- 10 25)(* 09 11)(= 12 13)(< 30 10)\x00", b"0966180000"),
        (b"(* 00 80)(+ 00 80)(- 80 00)(= 80 80)(< 00 80)", b"0080800101"),
    ],
)
def test_h47_lisp_num80_loop(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_num80(rounds=3)
    assert max(artifact.image) < 128
    assert num80_ref(stdin) == expected
    img_path = BUILD / "test_h47_lisp_num80.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected

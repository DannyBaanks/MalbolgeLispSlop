"""Tests for H33: native fixed19 conditional `(if (= a b) x y)` and `(if (< a b) x y)` REPL."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_lisp_if import build_lisp_if, reference as if_ref

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
        (b"(if (= 3 3) 7 2)", b"7"),
        (b"(if (= 3 4) 7 2)", b"2"),
        (b"(if (< 2 5) 9 1)", b"9"),
        (b"(if (< 5 2) 9 1)", b"1"),
        (b"(if (< 4 4) 9 1)", b"1"),
        (b"(if (= 0 0) 1 0)(if (= 9 9) 2 0)(if (< 0 9) 3 0)(if (< 9 0) 4 5)", b"1235"),
        (b"(if (= 3 3) 7 2)(if (= 3 4) 7 2)(if (< 2 5) 9 1)(if (< 5 2) 9 1)(if (< 4 4) 9 1)\x00", b"72911"),
    ],
)
def test_h33_lisp_if_loop(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_if(rounds=3)
    assert max(artifact.image) < 128
    assert if_ref(stdin) == expected
    img_path = BUILD / "test_h33_lisp_if.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected

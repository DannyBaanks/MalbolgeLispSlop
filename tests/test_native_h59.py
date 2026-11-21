"""Tests for H59: native fixed19 2-digit (00..80) div/mod/pow Mini-Lisp REPL (/, %, ^)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_lisp_divpow import build_lisp_divpow, reference as divpow_ref

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
        (b"(/ 75 10)(% 75 10)(/ 80 01)(/ 09 00)", b"07058000"),
        (b"(^ 02 06)(^ 03 03)(^ 05 02)(^ 07 00)", b"64272501"),
        (b"(/ 72 09)(^ !! 02)(% !! 10)", b"086404"),
        (b"(+ 30 25)(/ !! 07)(% !! 03)(? !! 42)", b"55070142"),
    ],
)
def test_h59_lisp_divpow(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_divpow(rounds=3)
    assert max(artifact.image) < 128
    assert divpow_ref(stdin) == expected
    img_path = BUILD / "test_h59_lisp_divpow.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected

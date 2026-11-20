"""Tests for H56: native fixed19 iterative loop-function Mini-Lisp VM (F fact, B fib, S sum)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_lisp_loopfn import build_lisp_v5 as build_lisp_loopfn, reference as loopfn_ref

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
VMS = [vm for vm in (BUILD / "bolge19", BUILD / "fast20") if vm.exists()]


def _run_vm(vm: Path, image: Path, stdin: bytes) -> bytes:
    proc = subprocess.run([str(vm), str(image)], input=stdin, capture_output=True, timeout=120)
    assert proc.returncode == 0, f"{vm.name} failed ({proc.returncode}): {proc.stderr!r}"
    return proc.stdout


@pytest.mark.parametrize(
    "stdin,expected",
    [
        (b"", b""),
        (b"\x00", b""),
        (b"(F 0 _)(F 1 _)(F 2 _)(F 3 _)(F 4 _)", b"1126H"),
        (b"(B 0 _)(B 1 _)(B 4 _)(B 6 _)(B 7 _)", b"0138="),
        (b"(S 0 _)(S 3 _)(S 5 _)(S 7 _)", b"06?L"),
        (b"(s x 3)(+ (F x _) (B 5 _))(? (> ! 9) (- ! 1) 0)", b"3;:"),
    ],
)
def test_h56_lisp_loopfn(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_loopfn(rounds=3)
    assert max(artifact.image) < 128
    assert loopfn_ref(stdin) == expected
    img_path = BUILD / "test_h56_lisp_loopfn.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected

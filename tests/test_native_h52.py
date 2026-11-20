"""Tests for H52: native fixed19 streaming nested S-expression Mini-Lisp VM v4 (with cons/car/cdr)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_lisp_v4 import build_lisp_v4, reference as v4_ref

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
        (b"(c 5 9)(a ! _)(d 0 _)", b"059"),
        (b"(a (c 4 7) _) (d (c 4 7) _)", b"47"),
        (b"(c (+ 1 2) (* 1 3)) (s x (c 4 !)) (d x _) (+ (a x _) (a ! _))", b"0107"),
        (b"(w 0 7) (r 0 _) (? (= x 0) 1 0) (D * .) (C 3 2)\x00", b"771.6"),
    ],
)
def test_h52_lisp_v4_cons_streaming(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_v4(rounds=3)
    assert max(artifact.image) < 128
    assert v4_ref(stdin) == expected
    img_path = BUILD / "test_h52_lisp_v4.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected

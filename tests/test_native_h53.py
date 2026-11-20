"""Tests for H53: native fixed19 streaming depth-3 nested S-expression Mini-Lisp VM v5."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_lisp_v5 import build_lisp_v5, reference as v5_ref

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
        (b"(+ (* 2 3) (- 9 (+ 1 2)))", b"<"),
        (b"(s x (c 2 3)) (a (d (c 1 x)) _)", b"02"),
        (b"(> 7 2) (> 2 7) (? (> (+ 2 3) 4) 9 0)", b"109"),
        (b"(c 4 5) (c 6 7) (c 8 9) (+ (a 0 _) (d 2 _))", b"012="),
    ],
)
def test_h53_lisp_v5_depth3(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_v5(rounds=3)
    assert max(artifact.image) < 128
    assert v5_ref(stdin) == expected
    img_path = BUILD / "test_h53_lisp_v5.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected

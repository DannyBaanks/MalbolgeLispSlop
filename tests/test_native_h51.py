"""Tests for H51: native fixed19 streaming nested S-expression Mini-Lisp VM v3."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_lisp_v3 import build_lisp_v3, reference as v3_ref

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
        (b"(s x (+ 2 3))  (* x 2)  (? (= x 5) 1 0)", b"5:1"),
        (b"(w 0 7) (r 0 _) (? (< ! 9) x 0) (D * .) (C 3 2)\x00", b"770.6"),
    ],
)
def test_h51_lisp_v3_streaming(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_v3(rounds=3)
    assert max(artifact.image) < 128
    assert v3_ref(stdin) == expected
    img_path = BUILD / "test_h51_lisp_v3.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected

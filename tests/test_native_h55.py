"""Tests for H55: native fixed19 streaming depth-3 Mini-Lisp VM v7 (explicit data stack P/K/T)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_lisp_v7 import build_lisp_v7, reference as v7_ref

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
        (b"(P 3 _)(P 5 _)(T _ _)(K _ _)(K _ _)(K _ _)", b"355530"),
        (b"(P (+ 2 3) _)(P (* 2 4) _)(+ (K _ _) (K _ _))", b"58="),
        (b"(s x 7)(P x _)(s x 1)(+ x (K _ _))", b"7718"),
        (b"(D + 1)(P (C 4 _) _)(c (T _ _) 2)(+ (K _ _) (a 0 _))", b"150:"),
    ],
)
def test_h55_lisp_v7_data_stack(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_v7(rounds=3)
    assert max(artifact.image) < 128
    assert v7_ref(stdin) == expected
    img_path = BUILD / "test_h55_lisp_v7.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected

"""Tests for H48: native fixed19 streaming nested S-expression evaluator v2."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_lisp_stream_v2 import build_lisp_stream_v2, reference as stream_ref

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
        (b"(+ (* 2 3) (- 9 (+ 1 2)))", b"<"),
        (b"  (= (+ 2 3) 5)", b"1"),
        (b"(< (* 2 2) 5)\x00", b"1"),
    ],
)
def test_h48_lisp_stream_v2(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_stream_v2(rounds=3)
    assert max(artifact.image) < 128
    assert stream_ref(stdin) == expected
    img_path = BUILD / "test_h48_lisp_stream_v2.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected

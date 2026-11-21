"""Tests for H60: integrated fixed19 Mini-Lisp VM v8 differential conformance across bolge19 and fast20."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_lisp_v8 import build_lisp_v8, reference as v8_ref

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
VMS = [vm for vm in (BUILD / "bolge19", BUILD / "fast20") if vm.exists()]


def _run_vm(vm: Path, image: Path, stdin: bytes) -> bytes:
    proc = subprocess.run([str(vm), str(image)], input=stdin, capture_output=True, timeout=120)
    assert proc.returncode == 0, f"{vm.name} failed ({proc.returncode}): {proc.stderr!r}"
    return proc.stdout


@pytest.fixture(scope="module")
def v8_image() -> Path:
    artifact = build_lisp_v8(rounds=3)
    assert max(artifact.image) < 128
    img_path = BUILD / "test_h60_lisp_v8.mb"
    img_path.write_bytes(artifact.image)
    return img_path


@pytest.mark.parametrize(
    "stdin",
    [
        b"",
        b"\x00",
        b"(+ 2 3)(- 9 4)(* 3 3)(= 5 5)(< 2 7)(> 8 1)",
        b"(A 1 2)(A 0 5)(O 0 0)(O 0 3)(N 0 _)(N 4 _)",
        b"(s x 4)(s p 2)(? (> x p) (+ x p) 0)",
        b"(D * .)(C 3 3)(D + 5)(C ! _)",
        b"(c 3 7)(c (+ 1 1) (* 2 3))(+ (a 0 _) (d 1 _))",
        b"(P 4 _)(P (+ 2 3) _)(+ (T _ _) (K _ _))(K _ _)",
        b"(s p 6)(P p _)(c p 2)(= (a 0 _) p)(? (A (> p 3) !) (+ (K _ _) (d 0 _)) 0)",
    ],
)
def test_h60_differential_conformance(v8_image: Path, stdin: bytes) -> None:
    expected = v8_ref(stdin)
    outputs = [_run_vm(vm, v8_image, stdin) for vm in VMS]
    for out in outputs:
        assert out == expected
    if len(outputs) > 1:
        assert all(out == outputs[0] for out in outputs[1:])

"""Tests for H50: native fixed19 integrated Mini-Lisp VM v2."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_lisp_v2 import build_lisp_v2, reference as v2_ref

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
        (b"(s x 3)(w 2 7)(+ 1 1)(r ! _)(* ! x)(D + .)(C ! 2)(S 3 _)", b"3727E.06"),
        (b"(S 3 _)(- ! 1)(w 0 !)(r 0 _)(= ! 5)(< ! 9)\x00", b"655511"),
        (b"(D * 3)(C 3 0)(s x !)(+ x 0)(w 1 x)(r 1 _)", b"399999"),
    ],
)
def test_h50_lisp_v2_loop(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_v2(rounds=3)
    assert max(artifact.image) < 128
    assert v2_ref(stdin) == expected
    img_path = BUILD / "test_h50_lisp_v2.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected

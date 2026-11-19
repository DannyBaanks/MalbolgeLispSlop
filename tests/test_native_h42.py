"""Tests for H42: native fixed19 pointer-based `cons`/`car`/`cdr` heap Mini-Lisp REPL."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_lisp_cons import build_lisp_cons, reference as cons_ref

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
        (b"(c 5 0)(c 7 !)(a ! _)(d 1 _)(a ! _)", b"01705"),
        (b"(c 3 4)(c 8 !)(d ! _)(d ! _)(a 0 _)(+ ! 6)", b"010439"),
        (b"(c 2 9)(c 4 0)(+ 0 1)(a ! _)(= ! 4)(- 9 5)(c ! 1)(d 2 _)\x00", b"01141421"),
    ],
)
def test_h42_lisp_cons_loop(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_cons(rounds=3)
    assert max(artifact.image) < 128
    assert cons_ref(stdin) == expected
    img_path = BUILD / "test_h42_lisp_cons.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected

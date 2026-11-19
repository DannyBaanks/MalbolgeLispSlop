"""Tests for H43: native fixed19 internal conditional loop (`(S n _)` sum 1..n) Mini-Lisp REPL."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_lisp_loop import build_lisp_loop, reference as loop_ref

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
        (b"(S 0 _)(S 1 _)(S 2 _)(S 3 _)", b"0136"),
        (b"(+ 1 2)(S ! _)(- ! 1)", b"365"),
        (b"(S 4 _)(S 5 _)\x00", b":?"),
    ],
)
def test_h43_lisp_internal_loop(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_loop(rounds=3)
    assert max(artifact.image) < 128
    assert loop_ref(stdin) == expected
    img_path = BUILD / "test_h43_lisp_loop.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected

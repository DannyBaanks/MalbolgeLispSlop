"""Tests for H44: native fixed19 internal-loop `fact(n)`, `fib(n)`, `sum(n)` Mini-Lisp REPL."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_lisp_rec import build_lisp_rec, reference as rec_ref

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
        (b"(F 0 _)(F 1 _)(F 3 _)(F 4 _)(F 5 _)", b"116H\x06"),
        (b"(B 0 _)(B 1 _)(B 4 _)(B 5 _)(B 6 _)(B 8 _)", b"01358E"),
        (b"(+ 1 2)(F ! _)(- ! 1)(B ! _)(S 3 _)\x00", b"36556"),
    ],
)
def test_h44_lisp_rec_loop(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_rec(rounds=3)
    assert max(artifact.image) < 128
    assert rec_ref(stdin) == expected
    img_path = BUILD / "test_h44_lisp_rec.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected

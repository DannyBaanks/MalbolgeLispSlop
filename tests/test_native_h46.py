"""Tests for H46: native fixed19 2-arg user-defined functions (`def`/`call`) Mini-Lisp REPL."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_lisp_fn2 import build_lisp_fn2, reference as fn2_ref

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
        (b"(D + .)(C 3 4)(D * 2)(C ! 0)", b".724"),
        (b"(s x 5)(D - 2)(C x 0)(D * .)(C 3 x)", b"523.?"),
        (b"(D + 4)(C 2 9)(s x !)(D * x)(C 1 0)\x00", b"46666"),
    ],
)
def test_h46_lisp_fn2_loop(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_fn2(rounds=3)
    assert max(artifact.image) < 128
    assert fn2_ref(stdin) == expected
    img_path = BUILD / "test_h46_lisp_fn2.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected

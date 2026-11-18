"""Tests for H39: native fixed19 user-defined 1-arg functions (`fn` / `ap`) REPL."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_lisp_fn import build_lisp_fn, reference as fn_ref

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
        (b"(fn + x 2)(ap f 3 0)(ap f ! 0)(fn - x 1)(ap f ! 0)", b"25716"),
        (b"(fn * x 3)(ap f 2 0)(fn + x 1)(ap f ! 0)(fn - x 4)(ap f ! 0)\x00", b"361743"),
        (b"(ap f 5 0)(fn * x 4)(ap f 2 0)(ap f 0 0)", b"5480"),
    ],
)
def test_h39_lisp_fn_loop(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_fn(rounds=3)
    assert max(artifact.image) < 128
    assert fn_ref(stdin) == expected
    img_path = BUILD / "test_h39_lisp_fn.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected

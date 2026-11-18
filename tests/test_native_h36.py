"""Tests for H36: native fixed19 named-variable Lisp REPL (`x`, `y`, `z`, `=`, `+`, `-`)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_lisp_env import build_lisp_env, reference as env_ref

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
        (b"(= x 5)(= y 3)(+ x y)(= z x)(- z 2)", b"53853"),
        (b"(+ x y)(= x 4)(= y x)(+ y 5)(- y 1)(= z y)(- z x)\x00", b"0449340"),
        (b"(= x 9)(= y 2)(= z x)(- z y)(+ y 7)(= x z)(+ x 0)", b"9297999"),
    ],
)
def test_h36_lisp_env_loop(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_env(rounds=3)
    assert max(artifact.image) < 128
    assert env_ref(stdin) == expected
    img_path = BUILD / "test_h36_lisp_env.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected

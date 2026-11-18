"""Tests for H37: native fixed19 `cons` (`c`), `car` (`a`), `cdr` (`d`) list REPL."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_lisp_lists import build_lisp_lists, reference as lists_ref

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
        (b"(c 7 0)(c 5 0)(c 3 0)(a 0 0)(d 0 0)(a 0 0)(d 0 0)(a 0 0)(d 0 0)\x00", b"753355770"),
        (b"(a 0 0)(c 9 0)(c 4 0)(d 0 0)(c 1 0)(a 0 0)", b"094911"),
        (b"(c 4 0)(d 0 0)(c 1 0)", b"401"),
        (b"(c 8 0)(c 6 0)(c 4 0)(c 2 0)(a 0 0)(d 0 0)(d 0 0)(d 0 0)(d 0 0)", b"864224680"),
    ],
)
def test_h37_lisp_lists_loop(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_lists(rounds=3)
    assert max(artifact.image) < 128
    assert lists_ref(stdin) == expected
    img_path = BUILD / "test_h37_lisp_lists.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected

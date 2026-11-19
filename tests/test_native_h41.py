"""Tests for H41: native fixed19 dynamic indexed memory (`PEEK`/`POKE`) Mini-Lisp REPL."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_lisp_mem import build_lisp_mem, reference as mem_ref

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
        (b"(w 0 5)(w 3 7)(+ 1 2)(r ! _)(+ 1 2)(w ! 9)(r 3 _)(- ! 2)(= ! 7)", b"573739971"),
        (b"(r 0 _)(w 7 4)(+ 3 4)(r ! _)(+ ! 5)(= ! 9)(w 1 !)(r 1 _)\x00", b"04749111"),
        (b"(w 2 8)(w 5 3)(- 7 2)(r ! _)(- ! 1)(r ! _)(= ! 8)", b"8353281"),
    ],
)
def test_h41_lisp_mem_loop(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_mem(rounds=3)
    assert max(artifact.image) < 128
    assert mem_ref(stdin) == expected
    img_path = BUILD / "test_h41_lisp_mem.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected

"""Tests for H34: native fixed19 multi-digit `(+ ab cd)` and `(- ab cd)` REPL."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_lisp_multidigit import build_lisp_multidigit, reference as md_ref

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
        (b"(+ 12 34)", b"046"),
        (b"(+ 99 99)", b"198"),
        (b"(- 50 17)", b"033"),
        (b"(- 09 09)", b"000"),
        (b"(+ 05 95)(- 80 01)(+ 42 58)", b"100079100"),
        (b"(+ 12 34)(+ 99 99)(- 50 17)(- 09 09)(+ 00 00)(- 99 01)\x00", b"046198033000000098"),
    ],
)
def test_h34_lisp_multidigit_loop(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_multidigit(rounds=5)
    assert max(artifact.image) < 128
    assert md_ref(stdin) == expected
    img_path = BUILD / "test_h34_lisp_multidigit.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected

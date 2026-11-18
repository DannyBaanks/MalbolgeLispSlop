"""Tests for H26..H29: native fixed19 store, carry-add, Fibonacci, and Lisp REPL loops."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_carry_loop import build_carry_loop, reference as carry_ref
from slopsynth.native_fib_loop import build_fib_loop, reference as fib_ref
from slopsynth.native_lisp_add_sub import build_lisp_add_sub, reference as add_sub_ref
from slopsynth.native_lisp_repl import build_lisp_repl, reference as repl_ref
from slopsynth.native_store import build_store_loop, reference as store_ref

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
VMS = [vm for vm in (BUILD / "bolge19", BUILD / "fast20") if vm.exists()]


def _run_vm(vm: Path, image: Path, stdin: bytes) -> bytes:
    proc = subprocess.run([str(vm), str(image)], input=stdin, capture_output=True, timeout=20)
    assert proc.returncode == 0, f"{vm.name} failed ({proc.returncode}): {proc.stderr!r}"
    return proc.stdout


@pytest.mark.parametrize(
    "stdin,expected",
    [
        (b"\x00", b""),
        (b"\x01A\x00", b"*"),
        (b"\x01A\x01B\x01C\x01D\x00", b"*ABC"),
        (b"\x01X\x01Y\x01Z", b"*XY"),
    ],
)
def test_h26_store_loop(stdin: bytes, expected: bytes) -> None:
    artifact = build_store_loop()
    assert max(artifact.image) < 128
    assert store_ref(stdin) == expected
    img_path = BUILD / "test_h26_store.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected


@pytest.mark.parametrize(
    "stdin,expected",
    [
        (b"\x00", b""),
        (b"\x01\x05\x01\x07\x01\x0a\x01\x14\x00", bytes([5, 12, 22, 42])),
        (b"\x01\x01\x01\x02\x01\x03\x01\x04\x01\x05\x00", bytes([1, 3, 6, 10, 15])),
        (b"\x01\x19\x01\x19\x01\x0f\x00", bytes([25, 50, 65])),
    ],
)
def test_h27_carry_add_loop(stdin: bytes, expected: bytes) -> None:
    artifact = build_carry_loop(rounds=3)
    assert max(artifact.image) < 128
    assert carry_ref(stdin, rounds=3) == expected
    img_path = BUILD / "test_h27_carry.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected


@pytest.mark.parametrize(
    "n,expected",
    [
        (0, []),
        (1, [1]),
        (6, [1, 1, 2, 3, 5, 8]),
        (13, [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233]),
    ],
)
def test_h28_fib_loop(n: int, expected: list[int]) -> None:
    artifact = build_fib_loop(rounds=4)
    assert max(artifact.image) < 128
    stdin = b"\x01" * n + b"\x00"
    exp_bytes = bytes(expected)
    assert fib_ref(stdin, rounds=4) == exp_bytes
    img_path = BUILD / "test_h28_fib.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == exp_bytes


@pytest.mark.parametrize(
    "stdin,expected",
    [
        (b"\x00", b""),
        (b"(+ 2 3)", b"5"),
        (b"(+ 2 3)(+ 4 5)(+ 1 7)(+ 0 9)", b"5989"),
        (b"(+ 0 0)(+ 8 1)(+ 3 6)\x00", b"099"),
    ],
)
def test_h29_lisp_repl_loop(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_repl(rounds=3)
    assert max(artifact.image) < 128
    assert repl_ref(stdin) == expected
    img_path = BUILD / "test_h29_lisp_repl.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected


@pytest.mark.parametrize(
    "stdin,expected",
    [
        (b"\x00", b""),
        (b"(+ 2 3)(- 9 4)(+ 1 7)(- 8 8)", b"5580"),
        (b"(- 7 2)(+ 3 6)(- 9 0)\x00", b"599"),
    ],
)
def test_h30_lisp_add_sub_loop(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_add_sub(rounds=3)
    assert max(artifact.image) < 128
    assert add_sub_ref(stdin) == expected
    img_path = BUILD / "test_h30_lisp_add_sub.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected

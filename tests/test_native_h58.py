"""Tests for H58: native fixed19 homoiconic quote/eval AST-heap Mini-Lisp REPL."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_lisp_eval_v2 import build_lisp_eval_v2, reference as eval_v2_ref

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
        (b"(p 0 *)(l 0 3)(r 0 2)(q 0 _)(e 0 _)", b"*32*6"),
        (b"(s x 5)(p 1 >)(l 1 x)(r 1 3)(e 1 _)", b"5>531"),
        (b"(p 2 ?)(l 2 !)(r 2 9)(e 2 _)(p 2 +)(q 2 _)", b"??99++"),
        (b"(p 3 *)(l 3 2)(r 3 4)(e 3 _)(l 3 !)(e 3 _)", b"*2488P"),
    ],
)
def test_h58_lisp_eval_v2(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_eval_v2(rounds=3)
    assert max(artifact.image) < 128
    assert eval_v2_ref(stdin) == expected
    img_path = BUILD / "test_h58_lisp_eval_v2.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected

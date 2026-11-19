"""Tests for H49: native fixed19 code-as-data AST-heap `eval` Mini-Lisp REPL."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from slopsynth.native_lisp_eval import build_lisp_eval, reference as eval_ref

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
        (b"(p 0 +)(l 0 3)(r 0 4)(e 0 _)(p 1 *)(l 1 7)(r 1 2)(e 1 _)", b"+347*72>"),
        (b"(p 2 -)(l 2 9)(r 2 4)(e 2 _)(p 3 =)(l 3 5)(r 3 5)(e 3 _)\x00", b"-945=551"),
        (b"(+ 1 2)(p ! <)(l 3 2)(r 3 8)(e 3 _)(- 9 !)", b"3<2818"),
    ],
)
def test_h49_lisp_eval_loop(stdin: bytes, expected: bytes) -> None:
    artifact = build_lisp_eval(rounds=3)
    assert max(artifact.image) < 128
    assert eval_ref(stdin) == expected
    img_path = BUILD / "test_h49_lisp_eval.mb"
    img_path.write_bytes(artifact.image)
    for vm in VMS:
        assert _run_vm(vm, img_path, stdin) == expected

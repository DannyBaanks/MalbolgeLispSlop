"""Tests for Gate H9 scoped native Lisp (+ 1 2) evaluation lowering."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from guest_ir.lisp.evaluator import build_eval_add_module
from slopsynth.assemble import AssemblyError
from slopsynth.eval_add import lower_eval_add
from slopsynth.lang import parse_placed
from slopsynth.model import RunStatus, run_model
from slopsynth.profile import load_profile
from tools.guest_runner import GuestStatus, RunConfig, run_guest

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "profiles" / "fixed19.json"
SLOP_PATH = ROOT / "examples" / "eval_add.slop"
VM_PATH = ROOT / "build" / "bolge19"


class NativeEvalAddTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = load_profile(PROFILE_PATH)
        cls.placed = parse_placed(SLOP_PATH.read_text(encoding="utf-8"))
        assert cls.placed.module is not None
        cls.module = cls.placed.module

    def test_lower_eval_add_produces_canonical_accepted_image(self) -> None:
        built = lower_eval_add(self.module, self.profile)
        self.assertEqual(built.cells, 259)
        self.assertTrue(built.walk.accepted)
        self.assertEqual(built.lowering, "fixed19-lisp-eval-add-v1")
        self.assertEqual(
            built.labels,
            (("main", (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)),),
        )

    def test_model_execution_byte_exact(self) -> None:
        built = lower_eval_add(self.module, self.profile)
        test_cases = [
            (b"(+ 1 2)", b"3"),
            (b"(+ 2 1)", b"3"),
            (b"(+ 1 2)\n", b"3"),
            (b"(+ 2 1)\n", b"3"),
        ]
        for stdin, expected in test_cases:
            res = run_model(
                built.image,
                stdin,
                self.profile,
                loader="canonical",
                max_steps=512,
                max_address=built.cells,
            )
            self.assertEqual(res.status, RunStatus.HALT)
            self.assertEqual(res.stdout, expected)
            self.assertEqual(res.steps, 11)

    def test_native_bolge19_execution(self) -> None:
        if not VM_PATH.is_file():
            self.skipTest("build/bolge19 not built")
        built = lower_eval_add(self.module, self.profile)
        config = RunConfig("canonical", 512, 5.0, 512 * 1024 * 1024, 64)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "eval_add.mb"
            path.write_bytes(built.image)
            test_cases = [
                (b"(+ 1 2)", b"3"),
                (b"(+ 2 1)", b"3"),
                (b"(+ 1 2)\n", b"3"),
                (b"(+ 2 1)\n", b"3"),
            ]
            for stdin, expected in test_cases:
                res = run_guest(path, stdin, config)
                self.assertEqual(res.status, GuestStatus.HALT)
                self.assertEqual(res.stdout, expected)
                self.assertEqual(res.returncode, 0)
                self.assertIn(b"HALT steps=11", res.stderr)

    def test_ir_module_builder_lowering(self) -> None:
        ir_mod = build_eval_add_module()
        built = lower_eval_add(ir_mod, self.profile)
        self.assertEqual(built.cells, 259)
        self.assertTrue(built.walk.accepted)
        res = run_model(
            built.image,
            b"(+ 1 2)",
            self.profile,
            loader="canonical",
            max_steps=50,
            max_address=259,
        )
        self.assertEqual(res.status, RunStatus.HALT)
        self.assertEqual(res.stdout, b"3")

    def test_refuses_operand_mismatch(self) -> None:
        bad_slop = """name bad_ops
entry main
case 282b2031203229,33
main:
    read lparen
    read plus
    read sp1
    read op1
    read sp2
    read op2
    add sum, op1, wrong
    sub result, sum, 48
    write result
    read rparen
    halt
"""
        placed = parse_placed(bad_slop)
        assert placed.module is not None
        with self.assertRaisesRegex(AssemblyError, "add operands"):
            lower_eval_add(placed.module, self.profile)

    def test_refuses_sub_operand_mismatch(self) -> None:
        bad_slop = """name bad_sub
entry main
case 282b2031203229,33
main:
    read lparen
    read plus
    read sp1
    read op1
    read sp2
    read op2
    add sum, op1, op2
    sub result, sum, 42
    write result
    read rparen
    halt
"""
        placed = parse_placed(bad_slop)
        assert placed.module is not None
        with self.assertRaisesRegex(AssemblyError, "sub operands"):
            lower_eval_add(placed.module, self.profile)


if __name__ == "__main__":
    unittest.main()

"""Tests for Gate H5 scoped native arithmetic lowering."""

from __future__ import annotations

from pathlib import Path
import subprocess
import unittest

from slopsynth.assemble import AssemblyError
from slopsynth.arithmetic import lower_arithmetic
from slopsynth.lang import parse_placed
from slopsynth.model import RunStatus, run_model
from slopsynth.profile import Profile, load_profile

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "profiles" / "fixed19.json"
SLOP_PATH = ROOT / "examples" / "add_sub.slop"
VM_PATH = ROOT / "build" / "bolge19"


class ArithmeticLoweringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = load_profile(PROFILE_PATH)
        cls.placed = parse_placed(SLOP_PATH.read_text(encoding="utf-8"))
        assert cls.placed.module is not None
        cls.module = cls.placed.module

    def test_lower_arithmetic_produces_canonical_accepted_image(self) -> None:
        built = lower_arithmetic(self.module, self.profile)
        self.assertEqual(built.cells, 259)
        self.assertTrue(built.walk.accepted)
        self.assertEqual(built.lowering, "fixed19-scoped-arithmetic-v1")
        self.assertEqual(built.labels, (("main", (105, 35, 50, 247)),))

    def test_model_execution_byte_exact(self) -> None:
        built = lower_arithmetic(self.module, self.profile)
        test_cases = [
            (b"\x00\x01", b"\x00"),
            (b"\x01\x01", b"\x01"),
            (b"\xff\xff", b"\xfd"),
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

    def test_native_bolge19_execution(self) -> None:
        import tempfile
        from tools.guest_runner import RunConfig, run_guest
        if not VM_PATH.is_file():
            self.skipTest("build/bolge19 not built")
        built = lower_arithmetic(self.module, self.profile)
        config = RunConfig("canonical", 512, 5, 512 * 1024 * 1024, 2)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "add_sub.mb"
            path.write_bytes(built.image)
            test_cases = [
                (b"\x00\x01", b"\x00"),
                (b"\x01\x01", b"\x01"),
                (b"\xff\xff", b"\xfd"),
            ]
            for stdin, expected in test_cases:
                res = run_guest(path, stdin, config)
                self.assertEqual(res.status.value, "HALT")
                self.assertEqual(res.stdout, expected)
                self.assertIn(b"HALT steps=", res.stderr)

    def test_refuses_operand_mismatch(self) -> None:
        bad_slop = """name bad_ops
entry main
case 0001,00
main:
    read left
    read right
    add sum, left, other
    sub result, sum, 1
    write result
    halt
"""
        placed = parse_placed(bad_slop)
        assert placed.module is not None
        with self.assertRaisesRegex(AssemblyError, "add operands"):
            lower_arithmetic(placed.module, self.profile)

    def test_refuses_sub_operand_mismatch(self) -> None:
        bad_slop = """name bad_sub
entry main
case 0001,00
main:
    read left
    read right
    add sum, left, right
    sub result, sum, 2
    write result
    halt
"""
        placed = parse_placed(bad_slop)
        assert placed.module is not None
        with self.assertRaisesRegex(AssemblyError, "sub operands"):
            lower_arithmetic(placed.module, self.profile)

    def test_refuses_case_contradiction(self) -> None:
        bad_slop = """name bad_case
entry main
case 0001,ff
main:
    read left
    read right
    add sum, left, right
    sub result, sum, 1
    write result
    halt
"""
        placed = parse_placed(bad_slop)
        assert placed.module is not None
        with self.assertRaisesRegex(AssemblyError, "contradicts"):
            lower_arithmetic(placed.module, self.profile)

    def test_refuses_profile_mismatch(self) -> None:
        custom_profile = Profile(
            name="other",
            trits=19,
            end=1162261467,
            eof_value=1162261466,
            dispatch=self.profile.dispatch,
            loaders=self.profile.loaders,
        )
        with self.assertRaisesRegex(AssemblyError, "exact bundled fixed19 profile"):
            lower_arithmetic(self.module, custom_profile)


if __name__ == "__main__":
    unittest.main()

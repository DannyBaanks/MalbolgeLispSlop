"""Tests for Gate H6 scoped native guest call and return lowering."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from slopsynth.assemble import AssemblyError
from slopsynth.call_return import lower_call_return
from slopsynth.ir_json import load_module
from slopsynth.lang import parse_placed
from slopsynth.model import RunStatus, run_model
from slopsynth.profile import Profile, load_profile
from tools.guest_runner import RunConfig, run_guest

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "profiles" / "fixed19.json"
SLOP_PATH = ROOT / "examples" / "call_return.slop"
JSON_PATH = ROOT / "examples" / "call_return.json"
VM_PATH = ROOT / "build" / "bolge19"


class CallReturnLoweringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = load_profile(PROFILE_PATH)
        cls.placed = parse_placed(SLOP_PATH.read_text(encoding="utf-8"))
        assert cls.placed.module is not None
        cls.module = cls.placed.module
        cls.json_module = load_module(JSON_PATH)

    def test_lower_call_return_produces_canonical_accepted_image(self) -> None:
        built = lower_call_return(self.module, self.profile)
        self.assertEqual(built.cells, 259)
        self.assertTrue(built.walk.accepted)
        self.assertEqual(built.lowering, "fixed19-scoped-call-return-v1")
        self.assertEqual(
            built.labels,
            (("main", (0, 99, 100, 96, 97)), ("identity", (67,))),
        )

    def test_json_and_slop_contracts_produce_identical_images(self) -> None:
        built_slop = lower_call_return(self.module, self.profile)
        built_json = lower_call_return(self.json_module, self.profile)
        self.assertEqual(built_slop.image, built_json.image)

    def test_model_execution_byte_exact(self) -> None:
        built = lower_call_return(self.module, self.profile)
        test_cases = [
            (b"\x00", b"\x00"),
            (b"\x01", b"\x01"),
            (b"\xff", b"\xff"),
            (b"\x42", b"\x42"),
            (b"A", b"A"),
        ]
        for stdin, expected in test_cases:
            res = run_model(
                built.image,
                stdin,
                self.profile,
                loader="canonical",
                max_steps=512,
                max_address=self.profile.end - 1,
            )
            self.assertEqual(res.status, RunStatus.HALT)
            self.assertEqual(res.stdout, expected)
            self.assertEqual(res.steps, 5)

    def test_native_bolge19_execution(self) -> None:
        if not VM_PATH.is_file():
            self.skipTest("build/bolge19 not built")
        built = lower_call_return(self.module, self.profile)
        config = RunConfig("canonical", 512, 5, 512 * 1024 * 1024, 2)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "call_return.mb"
            path.write_bytes(built.image)
            test_cases = [
                (b"\x00", b"\x00"),
                (b"\x01", b"\x01"),
                (b"\xff", b"\xff"),
                (b"\x42", b"\x42"),
            ]
            for stdin, expected in test_cases:
                res = run_guest(path, stdin, config)
                self.assertEqual(res.status.value, "HALT")
                self.assertEqual(res.stdout, expected)
                self.assertIn(b"HALT steps=5 c=97 d=5", res.stderr)

    def test_refuses_call_argument_mismatch(self) -> None:
        bad_slop = """name bad_arg
case 00,00
entry main
main:
    read x
    call y, identity, z
    write y
    halt
identity:
    ret x
"""
        placed = parse_placed(bad_slop)
        assert placed.module is not None
        with self.assertRaisesRegex(AssemblyError, "call argument"):
            lower_call_return(placed.module, self.profile)

    def test_refuses_write_value_mismatch(self) -> None:
        bad_slop = """name bad_write
case 00,00
entry main
main:
    read x
    call y, identity, x
    write z
    halt
identity:
    ret x
"""
        placed = parse_placed(bad_slop)
        assert placed.module is not None
        with self.assertRaisesRegex(AssemblyError, "written value"):
            lower_call_return(placed.module, self.profile)

    def test_refuses_callee_return_mismatch(self) -> None:
        bad_slop = """name bad_ret
case 00,00
entry main
main:
    read x
    call y, identity, x
    write y
    halt
identity:
    ret z
"""
        placed = parse_placed(bad_slop)
        assert placed.module is not None
        with self.assertRaisesRegex(AssemblyError, "callee return value"):
            lower_call_return(placed.module, self.profile)

    def test_refuses_case_contradiction(self) -> None:
        bad_slop = """name bad_case
case 00,ff
entry main
main:
    read x
    call y, identity, x
    write y
    halt
identity:
    ret x
"""
        placed = parse_placed(bad_slop)
        assert placed.module is not None
        with self.assertRaisesRegex(AssemblyError, "contradicts"):
            lower_call_return(placed.module, self.profile)

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
            lower_call_return(self.module, custom_profile)


if __name__ == "__main__":
    unittest.main()

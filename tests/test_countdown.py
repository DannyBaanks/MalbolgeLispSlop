"""Tests for Gate H7 scoped native guest countdown lowering."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from slopsynth.assemble import AssemblyError
from slopsynth.countdown import lower_countdown
from slopsynth.ir_json import load_module
from slopsynth.lang import parse_placed
from slopsynth.model import RunStatus, run_model
from slopsynth.profile import Profile, load_profile
from tools.guest_runner import RunConfig, run_guest

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "profiles" / "fixed19.json"
SLOP_PATH = ROOT / "examples" / "countdown.slop"
JSON_PATH = ROOT / "examples" / "countdown.json"
VM_PATH = ROOT / "build" / "bolge19"


class CountdownLoweringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = load_profile(PROFILE_PATH)
        cls.placed = parse_placed(SLOP_PATH.read_text(encoding="utf-8"))
        assert cls.placed.module is not None
        cls.module = cls.placed.module
        cls.json_module = load_module(JSON_PATH)

    def test_lower_countdown_produces_canonical_accepted_image(self) -> None:
        built = lower_countdown(self.module, self.profile)
        self.assertEqual(built.cells, 259)
        self.assertTrue(built.walk.accepted)
        self.assertEqual(built.lowering, "fixed19-scoped-countdown-v1")
        self.assertEqual(
            built.labels,
            (
                ("entry", (105,)),
                ("test", (109,)),
                ("step", (35, 89)),
                ("done", (71,)),
            ),
        )

    def test_json_and_slop_contracts_produce_identical_images(self) -> None:
        built_slop = lower_countdown(self.module, self.profile)
        built_json = lower_countdown(self.json_module, self.profile)
        self.assertEqual(built_slop.image, built_json.image)

    def test_model_execution_byte_exact(self) -> None:
        built = lower_countdown(self.module, self.profile)
        test_cases = [
            (b"\x00", b"\x00"),
            (b"\x01", b"\x01\x00"),
            (b"\x03", b"\x03\x02\x01\x00"),
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

    def test_native_bolge19_execution(self) -> None:
        if not VM_PATH.is_file():
            self.skipTest("build/bolge19 not built")
        built = lower_countdown(self.module, self.profile)
        config = RunConfig("canonical", 512, 5, 512 * 1024 * 1024, 64)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "countdown.mb"
            path.write_bytes(built.image)
            test_cases = [
                (b"\x00", b"\x00"),
                (b"\x01", b"\x01\x00"),
                (b"\x03", b"\x03\x02\x01\x00"),
            ]
            for stdin, expected in test_cases:
                res = run_guest(path, stdin, config)
                self.assertEqual(res.status.value, "HALT")
                self.assertEqual(res.stdout, expected)

    def test_refuses_different_profile(self) -> None:
        bogus_profile = Profile(
            name="bogus",
            trits=10,
            end=59049,
            eof_value=59048,
            dispatch=self.profile.dispatch,
            loaders=self.profile.loaders,
        )
        with self.assertRaises(AssemblyError):
            lower_countdown(self.module, bogus_profile)

    def test_refuses_wrong_block_count(self) -> None:
        bad_slop = """name bad_blocks
case 00,00
entry entry
entry:
    read n
    jump test
test:
    brz n, done, step
step:
    write n
    sub n, n, 1
    jump test
extra:
    read
    halt
done:
    write n
    halt
"""
        placed = parse_placed(bad_slop)
        assert placed.module is not None
        with self.assertRaises(AssemblyError):
            lower_countdown(placed.module, self.profile)

    def test_refuses_sub_operand_mismatch(self) -> None:
        bad_slop = """name bad_sub
case 00,00
entry entry
entry:
    read n
    jump test
test:
    brz n, done, step
step:
    write n
    sub n, n, 2
    jump test
done:
    write n
    halt
"""
        placed = parse_placed(bad_slop)
        assert placed.module is not None
        with self.assertRaises(AssemblyError):
            lower_countdown(placed.module, self.profile)

    def test_refuses_contradictory_case(self) -> None:
        bad_slop = """name bad_case
case 00,01
entry entry
entry:
    read n
    jump test
test:
    brz n, done, step
step:
    write n
    sub n, n, 1
    jump test
done:
    write n
    halt
"""
        placed = parse_placed(bad_slop)
        assert placed.module is not None
        with self.assertRaises(AssemblyError):
            lower_countdown(placed.module, self.profile)


if __name__ == "__main__":
    unittest.main()

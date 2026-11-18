"""H24: the unified native IR dispatcher routes each example to its lowering."""
from pathlib import Path
import unittest

from slopsynth.assemble import AssemblyError
from slopsynth.lang import parse_placed
from slopsynth.model import RunStatus, run_model
from slopsynth.native_ir import LOWERINGS, lower, lower_source
from slopsynth.native_arith_loop import build_arith_loop
from slopsynth.native_cipher import build_cipher
from slopsynth.native_cipher2 import build_cipher2
from slopsynth.native_count_in import build_count_in
from slopsynth.native_ir_loop import lower as lower_loop
from slopsynth.profile import load_profile

ROOT = Path(__file__).resolve().parents[1]
PROFILE = load_profile(ROOT / "profiles/fixed19.json")
EXAMPLES = ROOT / "examples"

# example file -> (expected lowering name, expected image bytes)
CASES = {
    "ir_loop.slop": ("fixed19-native-ir-loop-v1", None),       # built per-module inside lower_loop
    "ir_count.slop": ("fixed19-native-ir-count-v1", None),
    "ir_arith.slop": ("fixed19-native-ir-arith-v1", None),
    "ir_cipher.slop": ("fixed19-native-ir-cipher-v1", build_cipher().image),
    "ir_cipher2.slop": ("fixed19-native-ir-cipher2-v1", build_cipher2().image),
}


class DispatcherTests(unittest.TestCase):
    def test_every_example_dispatches_to_its_own_lowering(self):
        self.assertEqual(len(LOWERINGS), 5)
        for name in CASES:
            with self.subTest(example=name):
                src = (EXAMPLES / name).read_text(encoding="utf-8")
                result = lower_source(src)
                expected_name, expected_image = CASES[name]
                self.assertEqual(result.lowering, expected_name)
                if expected_image is not None:
                    self.assertEqual(result.image, expected_image)
                # and the image is byte-identical to the specialized lowering
                direct = lower(parse_placed(src).module)
                self.assertEqual(result.image, direct.image)

    def test_countdown_and_arith_images_match_their_builders(self):
        src = (EXAMPLES / "ir_count.slop").read_text(encoding="utf-8")
        self.assertEqual(lower_source(src).image, build_count_in(4).image)
        src = (EXAMPLES / "ir_arith.slop").read_text(encoding="utf-8")
        self.assertEqual(lower_source(src).image, build_arith_loop(4).image)
        src = (EXAMPLES / "ir_loop.slop").read_text(encoding="utf-8")
        self.assertEqual(lower_source(src).image, lower_loop(parse_placed(src).module).image)

    def test_declared_cases_run_in_the_model_under_the_strict_bound(self):
        for name in CASES:
            with self.subTest(example=name):
                placed = parse_placed((EXAMPLES / name).read_text(encoding="utf-8"))
                result = lower(placed.module)
                for case in placed.module.cases:
                    r = run_model(result.image, case.stdin, PROFILE, loader="raw",
                                  max_steps=3_000_000, max_address=len(result.image) - 1)
                    self.assertEqual(r.status, RunStatus.HALT)
                    self.assertEqual(r.stdout, case.stdout)

    def test_unknown_modules_are_refused_with_every_reason(self):
        src = (
            "name weird\ncase 00,00\nentry main\nmain:\n"
            "    read x\n    call y, identity, x\n    write y\n    halt\n"
            "identity:\n    ret x\n"
        )
        with self.assertRaises(AssemblyError) as caught:
            lower_source(src)
        msg = str(caught.exception)
        for name, _ in LOWERINGS:
            self.assertIn(name, msg)

    def test_straight_line_program_is_refused(self):
        with self.assertRaises(AssemblyError):
            lower_source("name echo\nread\nwrite\nhalt\n")


if __name__ == "__main__":
    unittest.main()

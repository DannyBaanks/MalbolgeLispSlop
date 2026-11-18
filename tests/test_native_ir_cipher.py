"""H21 regressions: IR cipher module -> native image, refusals, model runs."""
from pathlib import Path
import subprocess
import unittest

from slopsynth.assemble import AssemblyError
from slopsynth.lang import parse_placed
from slopsynth.model import RunStatus, run_model
from slopsynth.native_cipher import build_cipher, reference
from slopsynth.native_ir_cipher import LOWERING, lower
from slopsynth.profile import load_profile

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "examples/ir_cipher.slop"
SOURCE = MODULE.read_text(encoding="utf-8")
ENGINE = ROOT / "build/bolge19"
FAST20 = ROOT / "build/fast20"
INPUTS = [b"", b"\x00", b"\x02", b"\x02A", b"\x02A\x02B\x00", b"\x01\x02\xff\x00",
          b"\x03hi\x04yo\x00", b"\x01" * 8 + b"\x00", bytes(range(1, 60))]


class NativeIrCipherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = load_profile(ROOT / "profiles/fixed19.json")
        cls.module = parse_placed(SOURCE).module
        cls.built = lower(cls.module)

    def compile(self, source=SOURCE):
        return lower(parse_placed(source).module)

    def execute(self, stdin, max_steps=1_000_000):
        return run_model(self.built.image, stdin, self.profile, loader="raw",
                         max_steps=max_steps, max_address=len(self.built.image) - 1)

    def test_image_is_deterministic_and_identical_to_the_h20_builder(self):
        self.assertEqual(self.compile().image, self.built.image)
        self.assertEqual(self.built.image, build_cipher().image)
        self.assertEqual(self.built.lowering, LOWERING)
        self.assertLess(max(self.built.image), 128)

    def test_declared_cases_execute_in_the_model(self):
        self.assertTrue(self.module.cases)
        for case in self.module.cases:
            with self.subTest(stdin=case.stdin.hex()):
                result = self.execute(case.stdin)
                self.assertEqual(result.status, RunStatus.HALT)
                self.assertEqual(result.stdout, case.stdout)

    def test_campaign_inputs_match_the_reference_under_the_strict_bound(self):
        for data in INPUTS:
            with self.subTest(stdin=data.hex()):
                result = self.execute(data, max_steps=3_000_000)
                self.assertEqual(result.status, RunStatus.HALT)
                self.assertEqual(result.stdout, reference(data))
                self.assertEqual(result.final_c, self.built.cells["halt"])

    def test_no_memory_access_goes_above_the_image(self):
        result = self.execute(b"\x02A\x02B\x00", max_steps=3_000_000)
        result = run_model(self.built.image, b"\x02A\x02B\x00", self.profile, loader="raw",
                           max_steps=3_000_000, max_address=len(self.built.image) - 1, trace_accesses=True)
        self.assertLess(max(a.address for a in result.memory_accesses), len(self.built.image))

    def test_other_cfgs_are_refused(self):
        variants = (
            SOURCE.replace("brz s, zero, echo", "brz s, echo, zero"),
            SOURCE.replace("st ACC, 5", "st ACC, 6"),
            SOURCE.replace("craz ACC", "craz OTHER"),
            SOURCE.replace("    write\n    jump top", "    jump top"),
            SOURCE.replace("case 0241,c9", "case 0241,c8"),
            SOURCE.replace("brz s, zero, echo", "breq s, 1, zero, echo"),
        )
        for source in variants:
            with self.subTest(source=source.replace("\n", " | ")):
                with self.assertRaises(AssemblyError):
                    self.compile(source)

    @unittest.skipUnless(ENGINE.is_file() and FAST20.is_file(), "build/bolge19 and build/fast20 not built")
    def test_both_engines_agree_with_the_model(self):
        path = ROOT / "build/test_h21.mb"
        path.write_bytes(self.built.image)
        for data in INPUTS:
            with self.subTest(stdin=data.hex()):
                expected = reference(data)
                b = subprocess.run([str(ENGINE), str(path), "--loader", "raw", "--max-steps", "2000000"],
                                   input=data, capture_output=True, timeout=20)
                f = subprocess.run([str(FAST20), str(path)], input=data, capture_output=True, timeout=20)
                self.assertEqual((b.stdout, b.returncode), (expected, 0))
                self.assertEqual((f.stdout, f.returncode), (expected, 0))


if __name__ == "__main__":
    unittest.main()

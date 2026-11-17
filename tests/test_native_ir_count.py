"""H17 regressions: IR countdown module -> native image, refusals, model runs."""
from pathlib import Path
import subprocess
import unittest

from slopsynth.assemble import AssemblyError
from slopsynth.lang import parse_placed
from slopsynth.model import RunStatus, run_model
from slopsynth.native_count_in import MAX_COUNT, build_count_in
from slopsynth.native_ir_count import LOWERING, lower, module_source, reference
from slopsynth.profile import load_profile

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "examples/ir_count.slop"
SOURCE = MODULE.read_text(encoding="utf-8")
ENGINE = ROOT / "build/bolge19"
FAST20 = ROOT / "build/fast20"


class NativeIrCountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = load_profile(ROOT / "profiles/fixed19.json")
        cls.module = parse_placed(SOURCE).module
        cls.built = lower(cls.module)

    def compile(self, source=SOURCE):
        return lower(parse_placed(source).module)

    def execute(self, stdin=b"", max_steps=100_000):
        return run_model(self.built.image, stdin, self.profile, loader="raw",
                         max_steps=max_steps, max_address=len(self.built.image) - 1)

    def test_image_is_deterministic_and_identical_to_the_h16_builder(self):
        again = self.compile()
        self.assertEqual(again.image, self.built.image)
        self.assertEqual(self.built.image, build_count_in(self.built.count).image)
        self.assertEqual(self.built.count, 4)
        self.assertEqual(self.built.lowering, LOWERING)
        self.assertLess(max(self.built.image), 128)

    def test_declared_cases_execute_in_the_model(self):
        self.assertTrue(self.module.cases)
        for case in self.module.cases:
            with self.subTest(stdin=case.stdin.hex()):
                result = self.execute(case.stdin)
                self.assertEqual(result.status, RunStatus.HALT)
                self.assertEqual(result.stdout, case.stdout)

    def test_every_count_lowers_and_runs_under_the_strict_bound(self):
        for n in range(MAX_COUNT + 1):
            built = lower(parse_placed(module_source(n)).module)
            result = run_model(built.image, b"", self.profile, loader="raw",
                               max_steps=100_000, max_address=len(built.image) - 1,
                               trace_accesses=True)
            with self.subTest(n=n):
                self.assertEqual(result.status, RunStatus.HALT)
                self.assertEqual(result.stdout, reference(n))
                self.assertEqual(result.final_c, built.cells["halt"])
                self.assertLess(built.cells["halt"], len(built.image))
                self.assertLess(max(a.address for a in result.memory_accesses), len(built.image))
                self.assertEqual(built.image, build_count_in(n).image)

    def test_input_is_ignored(self):
        self.assertEqual(self.execute(b"\x00\xffhello").stdout, reference(self.built.count))

    def test_other_cfgs_are_refused(self):
        variants = (
            SOURCE.replace("breq v, 1, done, body", "breq v, 2, done, body"),
            SOURCE.replace("breq v, 1, done, body", "brz v, done, body"),
            SOURCE.replace("st Z, 81", "st Z, 80"),
            SOURCE.replace("st Z, 81", "st Z, 2187"),
            SOURCE.replace("st Z, 81", "st 94, 81"),
            SOURCE.replace("rot Z", "rot Y"),
            SOURCE.replace("    write\n    jump top", "    jump top"),
            SOURCE.replace("jump top\ntop:", "jump body\ntop:"),
            SOURCE.replace("case ,1b090301", "case ,1b090300"),
            SOURCE.replace("done:\n    halt", "done:\n    write\n    halt"),
        )
        for source in variants:
            with self.subTest(source=source.replace("\n", " | ")):
                with self.assertRaises(AssemblyError):
                    self.compile(source)

    def test_reference_matches_the_declared_cases(self):
        for case in self.module.cases:
            self.assertEqual(reference(self.built.count), case.stdout)

    @unittest.skipUnless(ENGINE.is_file() and FAST20.is_file(), "build/bolge19 and build/fast20 not built")
    def test_both_engines_agree_with_the_model(self):
        for n in range(MAX_COUNT + 1):
            built = lower(parse_placed(module_source(n)).module)
            path = ROOT / f"build/test_h17_{n}.mb"
            path.write_bytes(built.image)
            expected = reference(n)
            b = subprocess.run([str(ENGINE), str(path), "--loader", "raw", "--max-steps", "100000"],
                               stdin=subprocess.DEVNULL, capture_output=True, timeout=20)
            f = subprocess.run([str(FAST20), str(path)], stdin=subprocess.DEVNULL, capture_output=True, timeout=20)
            with self.subTest(n=n):
                self.assertEqual((b.stdout, b.returncode), (expected, 0))
                self.assertEqual((f.stdout, f.returncode), (expected, 0))


if __name__ == "__main__":
    unittest.main()

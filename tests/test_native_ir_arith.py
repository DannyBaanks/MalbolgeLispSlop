"""H19 regressions: IR arithmetic loop -> native image, refusals, model runs."""
from pathlib import Path
import subprocess
import unittest

from slopsynth.assemble import AssemblyError
from slopsynth.lang import parse_placed
from slopsynth.model import RunStatus, run_model
from slopsynth.native_arith_loop import MAX_COUNT, build_arith_loop
from slopsynth.native_ir_arith import LOWERING, lower, module_source
from slopsynth.native_arith_loop import reference
from slopsynth.profile import load_profile

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "examples/ir_arith.slop"
SOURCE = MODULE.read_text(encoding="utf-8")
ENGINE = ROOT / "build/bolge19"
FAST20 = ROOT / "build/fast20"


class NativeIrArithTests(unittest.TestCase):
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

    def test_image_is_deterministic_and_identical_to_the_h18_builder(self):
        self.assertEqual(self.compile().image, self.built.image)
        self.assertEqual(self.built.image, build_arith_loop(self.built.count).image)
        self.assertEqual(self.built.count, 4)
        self.assertEqual(self.built.lowering, LOWERING)
        self.assertLess(max(self.built.image), 128)

    def test_declared_cases_execute_in_the_model(self):
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
                self.assertLess(max(a.address for a in result.memory_accesses), len(built.image))
                self.assertEqual(built.image, build_arith_loop(n).image)

    def test_input_is_ignored(self):
        self.assertEqual(self.execute(b"\x00\xffhello").stdout, reference(self.built.count))

    def test_other_cfgs_are_refused(self):
        variants = (
            SOURCE.replace("breq v, 1, done, body", "breq v, 2, done, body"),
            SOURCE.replace("st Z, 81", "st Z, 80"),
            SOURCE.replace("st Z, 81", "st Z, 2187"),
            SOURCE.replace("st ACC, 5", "st ACC, 6"),
            SOURCE.replace("st Z, 81", "st ACC, 81"),  # same cell twice / Z name gone
            SOURCE.replace("craz ACC", "craz Z"),
            SOURCE.replace("rot Z", "rot ACC"),
            SOURCE.replace("    write\n    craz ACC", "    craz ACC"),  # body lost a write
            SOURCE.replace("case ,1bd309e503eb01ee", "case ,1bd309e503eb01ef"),
            SOURCE.replace("craz ACC", "rot ACC"),
        )
        for source in variants:
            with self.subTest(source=source.replace("\n", " | ")):
                with self.assertRaises(AssemblyError):
                    self.compile(source)

    @unittest.skipUnless(ENGINE.is_file() and FAST20.is_file(), "build/bolge19 and build/fast20 not built")
    def test_both_engines_agree_with_the_model(self):
        for n in range(MAX_COUNT + 1):
            built = lower(parse_placed(module_source(n)).module)
            path = ROOT / f"build/test_h19_{n}.mb"
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

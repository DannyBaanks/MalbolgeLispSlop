"""H15 regressions: IR module -> native loop, refusals, and model runs."""

from pathlib import Path
import unittest

from slopsynth.assemble import AssemblyError
from slopsynth.lang import parse_placed
from slopsynth.model import RunStatus, run_model
from slopsynth.native_ir_loop import EOF_WORD, lower, reference
from slopsynth.native_loop import EOF_BYTE
from slopsynth.profile import load_profile

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "examples/ir_loop.slop"
SOURCE = MODULE.read_text(encoding="utf-8")


class NativeIrLoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = load_profile(ROOT / "profiles/fixed19.json")
        cls.module = parse_placed(SOURCE).module
        cls.built = lower(cls.module)

    def compile(self, source=SOURCE):
        return lower(parse_placed(source).module)

    def execute(self, stdin: bytes, max_steps: int = 50_000):
        return run_model(self.built.image, stdin, self.profile, loader="raw",
                         max_steps=max_steps, max_address=len(self.built.image))

    def test_image_is_deterministic_and_raw_byte_safe(self):
        again = self.compile()
        self.assertEqual(again.image, self.built.image)
        self.assertLess(max(self.built.image), 128)
        self.assertEqual(self.built.loop_head, self.built.cells["landing"])
        self.assertGreater(len(self.built.image), 4_000)

    def test_declared_cases_execute_in_the_model(self):
        for case in self.module.cases:
            with self.subTest(stdin=case.stdin.hex()):
                result = self.execute(case.stdin)
                self.assertEqual(result.status, RunStatus.HALT)
                self.assertEqual(result.stdout, case.stdout)

    def test_selector_zero_and_empty_input_halt_without_output(self):
        self.assertEqual(self.execute(b"").stdout, b"")
        self.assertEqual(self.execute(b"\x00").stdout, b"")
        # a zero selector after one pass stops the loop and keeps the pass's byte
        self.assertEqual(self.execute(b"\x02A\x00").stdout, b"A")

    def test_truncated_payload_prints_the_eof_byte_then_halts(self):
        result = self.execute(b"\x02")
        self.assertEqual(result.status, RunStatus.HALT)
        self.assertEqual(result.stdout, bytes([EOF_BYTE]))

    def test_the_same_cells_run_on_every_pass(self):
        one = self.execute(b"\x02A\x00")
        two = self.execute(b"\x02A\x02B\x00")
        self.assertEqual(one.stdout, b"A")
        self.assertEqual(two.stdout, b"AB")
        self.assertEqual(two.steps - one.steps, self.built.steps_per_pass)
        self.assertEqual(two.steps - one.steps, 2_074)

    def test_the_exit_does_not_read_above_the_image(self):
        # every memory access of the run must stay inside the image
        result = run_model(self.built.image, b"\x02A\x00", self.profile, loader="raw",
                           max_steps=50_000, max_address=len(self.built.image), trace_accesses=True)
        self.assertEqual(result.status, RunStatus.HALT)
        self.assertLess(max(a.address for a in result.memory_accesses), len(self.built.image))

    def test_other_cfgs_are_refused(self):
        variants = (
            SOURCE.replace("brz A", "brz B"),
            SOURCE.replace("read\nbrz", "read B\nbrz"),
            SOURCE.replace("echo:\nread", "echo:\nadd A, A, 1\nread"),
            SOURCE.replace("zero:\nhalt", "zero:\nwrite\nhalt"),
            SOURCE.replace("jump top", "halt"),
        )
        for source in variants:
            with self.subTest(source=source):
                with self.assertRaises(AssemblyError):
                    self.compile(source)

    def test_contradicted_case_is_refused(self):
        with self.assertRaises(AssemblyError):
            self.compile(SOURCE.replace("case 024100,41", "case 024100,42"))

    def test_reference_matches_the_declared_cases(self):
        for case in self.module.cases:
            self.assertEqual(reference(case.stdin), case.stdout)
        self.assertEqual(reference(b"\x02"), bytes([EOF_BYTE]))
        self.assertEqual(reference(b"\x00\x02A"), b"")


if __name__ == "__main__":
    unittest.main()

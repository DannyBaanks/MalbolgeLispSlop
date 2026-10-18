"""H3 regressions: native loop control flow, and fail-closed scope."""

from dataclasses import replace
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from slopsynth.assemble import AssemblyError
from slopsynth.lang import parse_placed
from slopsynth.profile import load_profile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = """name loop_filter
case 00,
case 024100,41
case 0241024200,4142
entry top
top:
read
brz A, zero, nonzero
zero:
halt
nonzero:
read
write
jump top
"""


class LoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = load_profile(ROOT / "profiles/fixed19.json")

    def compile(self, source=SOURCE, profile=None):
        try:
            from slopsynth.loop import lower_loop
        except ImportError:
            self.fail("H3 has no native loop lowering")
        return lower_loop(parse_placed(source).module, profile or self.profile)

    def test_zero_and_iteration_paths_execute_in_the_model(self):
        from slopsynth.model import run_model
        built = self.compile()
        # Case 1: selector 0 halts with empty stdout
        res0 = run_model(
            built.image, bytes((0,)), self.profile,
            loader="canonical", max_steps=512, max_address=1024,
            trace_instructions=True,
        )
        self.assertEqual(res0.status.value, "HALT")
        self.assertEqual(res0.stdout, b"")

        # Case 2: selector 2 with payload A then 0 halts with b'A'
        res1 = run_model(
            built.image, bytes((2, ord("A"), 0)), self.profile,
            loader="canonical", max_steps=512, max_address=1024,
            trace_instructions=True,
        )
        self.assertEqual(res1.status.value, "HALT")
        self.assertEqual(res1.stdout, b"A")

        # Case 3: two iterations echo AB
        res2 = run_model(
            built.image, bytes((2, ord("A"), 2, ord("B"), 0)), self.profile,
            loader="canonical", max_steps=512, max_address=1024,
            trace_instructions=True,
        )
        self.assertEqual(res2.status.value, "HALT")
        self.assertEqual(res2.stdout, b"AB")

    def test_execution_in_the_real_vm(self):
        from tools.guest_runner import RunConfig, run_guest
        if not (ROOT / "build/bolge19").is_file():
            self.skipTest("build bolge19 first")
        built = self.compile()
        config = RunConfig("canonical", 512, 5, 512 * 1024 * 1024, 2)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "loop.mb"
            path.write_bytes(built.image)

            # Test 0 iterations:
            res = run_guest(path, b"\x00", config)
            self.assertEqual(res.status.value, "HALT")
            self.assertEqual(res.stdout, b"")

            # Test 1 iteration across all payload bytes for selector 2:
            for byte in range(256):
                with self.subTest(payload=byte):
                    observed = run_guest(path, bytes((2, byte, 0)), config)
                    self.assertEqual(observed.status.value, "HALT")
                    self.assertEqual(observed.stdout, bytes((byte,)))

            # Test 2 iterations:
            for p1, p2 in ((ord("A"), ord("B")), (0, 0), (255, 255), (10, 13)):
                with self.subTest(p1=p1, p2=p2):
                    observed = run_guest(path, bytes((2, p1, 2, p2, 0)), config)
                    self.assertEqual(observed.status.value, "HALT")
                    self.assertEqual(observed.stdout, bytes((p1, p2)))

            # EOF handling:
            observed = run_guest(path, b"", config)
            self.assertEqual(observed.status.value, "HALT")

    def test_registers_arithmetic_and_different_arms_are_refused(self):
        variants = (
            SOURCE.replace("brz A", "brz B"),
            SOURCE.replace("read\nbrz", "read B\nbrz"),
            SOURCE.replace("nonzero:\nread", "nonzero:\nadd A, A, 1\nread"),
            SOURCE.replace("zero:\nhalt", "zero:\nwrite\nhalt"),
            SOURCE.replace("jump top", "halt"),
        )
        for source in variants:
            with self.subTest(source=source):
                with self.assertRaises(AssemblyError):
                    self.compile(source)

    def test_changed_profile_and_false_case_are_refused(self):
        with self.assertRaises(AssemblyError):
            self.compile(profile=replace(self.profile, eof_value=0))
        with self.assertRaises(AssemblyError):
            self.compile(SOURCE.replace("case 024100,41", "case 024100,42"))

    def test_block_names_and_order_do_not_choose_the_behavior(self):
        renamed = SOURCE.replace("zero", "stop").replace("nonzero", "echo")
        self.assertEqual(self.compile().image, self.compile(renamed).image)


if __name__ == "__main__":
    unittest.main()

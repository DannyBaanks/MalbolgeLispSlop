"""H2 regressions: a real input-dependent jump, and fail-closed scope."""

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
SOURCE = """name filter
case 0141,41
entry top
top:
read
brz A, zero, nonzero
zero:
halt
nonzero:
read
write
halt
"""


class BranchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = load_profile(ROOT / "profiles/fixed19.json")

    def compile(self, source=SOURCE, profile=None):
        # Import here so the missing lowering is an explicit assertion failure.
        try:
            from slopsynth.branch import lower_branch
        except ImportError:
            self.fail("H2 has no native branch lowering")
        return lower_branch(parse_placed(source).module, profile or self.profile)

    def test_all_first_bytes_take_the_correct_guest_path(self):
        from slopsynth.model import run_model
        built = self.compile()
        for value in range(256):
            with self.subTest(value=value):
                result = run_model(
                    built.image, bytes((value, 65)), self.profile,
                    loader="canonical", max_steps=512, max_address=1024,
                    trace_instructions=True,
                )
                self.assertEqual(result.status.value, "HALT")
                self.assertEqual(result.stdout, b"" if value == 0 else b"A")
                self.assertTrue(any(e.address == 109 and e.operation == "jump"
                                    for e in result.instruction_trace))

    def test_eof_and_each_output_byte_execute_in_the_real_vm(self):
        from tools.guest_runner import RunConfig, run_guest
        if not (ROOT / "build/bolge19").is_file():
            self.skipTest("build bolge19 first")
        built = self.compile()
        config = RunConfig("canonical", 512, 5, 512 * 1024 * 1024, 2)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "branch.mb"
            path.write_bytes(built.image)
            # 1, 82, 109, 255 cover all four copies; 108 lands on JMP itself.
            # EOF exercises
            # the far-memory trampoline, not just the in-image byte paths.
            inputs = [b"", b"\x00", b"\x01"]
            inputs += [bytes((selector, value))
                       for selector in (1, 82, 108, 109, 255) for value in range(256)]
            for stdin in inputs:
                with self.subTest(stdin=stdin.hex()):
                    observed = run_guest(path, stdin, config)
                    expected = (b"" if stdin[:1] == b"\x00" else
                                stdin[1:2] or b"\xda")
                    self.assertEqual(observed.status.value, "HALT")
                    self.assertEqual(observed.stdout, expected)

    def test_registers_arithmetic_and_different_arms_are_refused(self):
        variants = (
            SOURCE.replace("brz A", "brz B"),
            SOURCE.replace("read\nbrz", "read B\nbrz"),
            SOURCE.replace("nonzero:\nread", "nonzero:\nadd A, A, 1\nread"),
            SOURCE.replace("zero:\nhalt", "zero:\nwrite\nhalt"),
        )
        for source in variants:
            with self.subTest(source=source):
                with self.assertRaises(AssemblyError):
                    self.compile(source)

    def test_changed_profile_and_false_case_are_refused(self):
        with self.assertRaises(AssemblyError):
            self.compile(profile=replace(self.profile, eof_value=0))
        with self.assertRaises(AssemblyError):
            self.compile(SOURCE.replace("case 0141,41", "case 0141,42"))

    def test_block_names_and_order_do_not_choose_the_behavior(self):
        renamed = SOURCE.replace("zero", "stop").replace("nonstop", "echo")
        self.assertEqual(self.compile().image, self.compile(renamed).image)
        reordered = SOURCE.replace("zero:\nhalt\nnonzero:\nread\nwrite\nhalt",
                                   "nonzero:\nread\nwrite\nhalt\nzero:\nhalt")
        self.assertEqual(self.compile().image, self.compile(reordered).image)
        empty = SOURCE.replace("case 0141,41", "case 0041,\ncase ,da")
        self.assertEqual(self.compile().image, self.compile(empty).image)

    def test_cli_emits_module_and_round_trips_it(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "filter.slop"
            output = Path(directory) / "filter.mb"
            source.write_text(SOURCE)
            result = subprocess.run(
                ["python3", str(ROOT / "tools/assemble.py"), str(source),
                 "--out", str(output), "--round-trip", "--line-width", "20"],
                capture_output=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(output.read_bytes().replace(b"\n", b""), self.compile().image)
            original = output.read_bytes()
            repeated = subprocess.run(
                ["python3", str(ROOT / "tools/assemble.py"), str(source), "--out", str(output)],
                capture_output=True, timeout=10,
            )
            self.assertEqual(repeated.returncode, 3)
            self.assertEqual(output.read_bytes(), original)

    def test_optimized_evidence_gate_rejects_a_vm_that_always_stops(self):
        # Inject a failed VM boundary, not a successful mock implementation.
        # The real gate must record FAIL even when Python strips assertions.
        script = """
import sys
from tools import verify_h2_branch as gate
from tools.guest_runner import GuestResult, GuestStatus
gate.orientation_control = lambda: {"test": "VM failure injection"}
gate.run_guest = lambda *args, **kwargs: GuestResult(b"", b"HALT steps=0", 0, GuestStatus.HALT)
sys.argv = ["verify_h2_branch.py", "--output-root", sys.argv[1]]
raise SystemExit(gate.main())
"""
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(["python3", "-O", "-c", script, directory],
                                    cwd=ROOT, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 1, result.stdout.decode() + result.stderr.decode())
            reports = list(Path(directory).glob("*/report.json"))
            self.assertEqual(len(reports), 1)
            report = json.loads(reports[0].read_text())
            self.assertIsNotNone(report["failure"])
            self.assertEqual(report["claims"]["H2-ZERO-STOP-ELSE-ECHO"], "FAIL")


if __name__ == "__main__":
    unittest.main()

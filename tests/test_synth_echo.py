from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from slopsynth.ir_json import load_program
from slopsynth.profile import Profile, load_profile
from slopsynth.search import SearchBudget, SynthesisStatus, synthesize_program


ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "build" / "bolge19"


class SynthesizedEchoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile: Profile = load_profile(ROOT / "profiles" / "fixed19.json")
        cls.program = load_program(ROOT / "examples" / "echo.json")

    def test_echo_synthesizes_and_runs_for_four_byte_inputs(self) -> None:
        budget = SearchBudget(max_cells=3, max_nodes=10_000, max_steps=8, max_address=8)
        result = synthesize_program(self.program, self.profile, budget)

        self.assertEqual(result.status, SynthesisStatus.FOUND)
        self.assertEqual(result.image, b"ubO")
        self.assertEqual(result.bounds, budget)
        self.assertTrue(ENGINE.is_file(), "build/bolge19 must be built before this test")

        for value in (b"A", b"z", b"\x00", b"\xff"):
            with self.subTest(value=value):
                actual = self.run_guest(result.image, value)
                self.assertEqual(actual.returncode, 0)
                self.assertEqual(actual.stdout, value)
                self.assertIn(b"HALT steps=2", actual.stderr)

    def test_candidate_over_cell_bound_reports_exact_budget(self) -> None:
        budget = SearchBudget(max_cells=2, max_nodes=10_000, max_steps=8, max_address=8)
        result = synthesize_program(self.program, self.profile, budget)

        self.assertEqual(result.status, SynthesisStatus.NOT_FOUND_WITHIN_BOUNDS)
        self.assertIsNone(result.image)
        self.assertEqual(result.bounds, budget)

    def test_budget_exhaustion_is_not_unsat(self) -> None:
        budget = SearchBudget(max_cells=3, max_nodes=0, max_steps=8, max_address=8)
        result = synthesize_program(self.program, self.profile, budget)

        self.assertEqual(result.status, SynthesisStatus.BUDGET_EXHAUSTED)
        self.assertEqual(result.explored_nodes, 0)
        self.assertEqual(result.bounds, budget)

    def run_guest(self, image: bytes | None, stdin: bytes) -> subprocess.CompletedProcess[bytes]:
        assert image is not None
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "synthesized.mb"
            path.write_bytes(image)
            return subprocess.run(
                [str(ENGINE), str(path), "--loader", "canonical", "--max-steps", "8"],
                input=stdin,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=2,
                check=False,
            )


if __name__ == "__main__":
    unittest.main()

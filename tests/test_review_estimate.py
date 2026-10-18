from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.estimate_review_time import estimate_artifact, estimate_review_time


class ReviewEstimateTests(unittest.TestCase):
    def test_estimate_uses_actual_artifact_size(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            artifact = Path(temporary) / "guest.mb"
            artifact.write_bytes(b"1234567890")

            estimate = estimate_artifact(
                artifact, bytes_per_second=1, hours_per_day=8
            )

        self.assertEqual(estimate.artifact_bytes, 10)
        self.assertAlmostEqual(estimate.uninterrupted_years, 10 / 31_536_000)
        self.assertAlmostEqual(estimate.workday_years, 10 / (8 * 3_600) / 365)

    def test_estimate_scales_with_reading_rate(self) -> None:
        slow = estimate_review_time(1000, bytes_per_second=1, hours_per_day=8)
        fast = estimate_review_time(1000, bytes_per_second=2, hours_per_day=8)

        self.assertAlmostEqual(slow.uninterrupted_years / 2, fast.uninterrupted_years)
        self.assertAlmostEqual(slow.workday_years / 2, fast.workday_years)

    def test_invalid_estimate_inputs_are_rejected(self) -> None:
        for args in (
            (-1, 1, 8),
            (1, 0, 8),
            (1, float("inf"), 8),
            (1, 1, 0),
            (1, 1, 25),
            (True, 1, 8),
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                estimate_review_time(*args)

    def test_cli_uses_current_file_size_and_labels_satire(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            artifact = Path(temporary) / "guest.mb"
            artifact.write_bytes(b"slop")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(
                        Path(__file__).resolve().parents[1]
                        / "tools"
                        / "estimate_review_time.py"
                    ),
                    str(artifact),
                    "--bytes-per-second",
                    "1",
                    "--hours-per-day",
                    "8",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=5,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        output = json.loads(completed.stdout)
        self.assertEqual(output["artifact_bytes"], 4)
        self.assertEqual(output["label"], "satire estimate only")
        self.assertIn("not semantic verification", output["note"])


if __name__ == "__main__":
    unittest.main()

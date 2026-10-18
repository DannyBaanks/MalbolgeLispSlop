from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from quine.evidence import QuineContract, QuineReport, load_contract


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "quine" / "contract.json"
BOUNDS = {
    "max_nodes": 10000,
    "wall_seconds": 10.0,
    "candidate_steps": 1_000_000,
    "candidate_timeout_seconds": 2.0,
    "candidate_memory_bytes": 536_870_912,
    "max_candidate_bytes": 100_000,
}


class QuineContractTests(unittest.TestCase):
    def test_contract_pins_fixed19_canonical_byte_exact_halt(self) -> None:
        contract = load_contract(CONTRACT)

        self.assertEqual(
            contract,
            QuineContract(
                profile="fixed-3^19",
                loader="canonical",
                newline_policy="no-final-newline",
            ),
        )

    def test_contract_rejects_unknown_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "contract.json"
            data = json.loads(CONTRACT.read_text(encoding="utf-8"))
            data["profile"] = "classic-3^10"
            path.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "profile"):
                load_contract(path)

    def test_contract_rejects_unknown_newline_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "contract.json"
            data = json.loads(CONTRACT.read_text(encoding="utf-8"))
            data["newline_policy"] = "whatever-the-host-does"
            path.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "newline_policy"):
                load_contract(path)

    def test_contract_rejects_weakened_guest_and_loader_rules(self) -> None:
        mutations = (
            ("ignored_loader_bytes", [9, 10, 32]),
            ("stdout_comparison", "text-normalized"),
            ("required_guest_status", "MAX_STEPS"),
        )
        for field, value in mutations:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "contract.json"
                data = json.loads(CONTRACT.read_text(encoding="utf-8"))
                data[field] = value
                path.write_text(json.dumps(data), encoding="utf-8")

                with self.assertRaises(ValueError):
                    load_contract(path)

    def test_report_serialization_is_versioned_and_deterministic(self) -> None:
        report = QuineReport(
            status="BUDGET_EXHAUSTED",
            candidate_path="candidates/0001.mb",
            source_sha256="a" * 64,
            stdout_sha256=None,
            steps=None,
            bounds=BOUNDS,
            reason="max_nodes reached",
        )

        encoded = report.to_bytes()

        self.assertEqual(encoded, report.to_bytes())
        self.assertEqual(
            json.loads(encoded),
            {
                "schema_version": 1,
                "status": "BUDGET_EXHAUSTED",
                "candidate_path": "candidates/0001.mb",
                "source_sha256": "a" * 64,
                "stdout_sha256": None,
                "steps": None,
                "bounds": BOUNDS,
                "reason": "max_nodes reached",
            },
        )

    def test_report_requires_all_search_bounds(self) -> None:
        bounds = dict(BOUNDS)
        del bounds["candidate_steps"]

        with self.assertRaisesRegex(ValueError, "candidate_steps"):
            QuineReport(
                status="NOT_DEMONSTRATED",
                candidate_path=None,
                source_sha256=None,
                stdout_sha256=None,
                steps=None,
                bounds=bounds,
                reason="bounded search completed without a quine",
            )

    def test_report_allows_zero_node_budget_to_record_exhaustion(self) -> None:
        bounds = dict(BOUNDS)
        bounds["max_nodes"] = 0

        report = QuineReport(
            status="BUDGET_EXHAUSTED",
            candidate_path=None,
            source_sha256=None,
            stdout_sha256=None,
            steps=None,
            bounds=bounds,
            reason="no candidate node could be explored",
        )

        self.assertEqual(report.bounds["max_nodes"], 0)

    def test_report_rejects_global_no_quine_status(self) -> None:
        with self.assertRaisesRegex(ValueError, "status"):
            QuineReport(
                status="NO_QUINE",
                candidate_path=None,
                source_sha256=None,
                stdout_sha256=None,
                steps=None,
                bounds=BOUNDS,
                reason="not a valid bounded result",
            )

    def test_demonstrated_report_requires_matching_byte_digests(self) -> None:
        with self.assertRaisesRegex(ValueError, "matching source/stdout digests"):
            QuineReport(
                status="DEMONSTRATED",
                candidate_path="candidates/0001.mb",
                source_sha256="a" * 64,
                stdout_sha256="b" * 64,
                steps=12,
                bounds=BOUNDS,
                reason="invalid mismatch",
            )

    def test_demonstrated_report_allows_steps_to_be_unavailable(self) -> None:
        report = QuineReport(
            status="DEMONSTRATED",
            candidate_path="candidates/0001.mb",
            source_sha256="a" * 64,
            stdout_sha256="a" * 64,
            steps=None,
            bounds=BOUNDS,
            reason="guest halted and stdout matched source bytes exactly",
        )

        self.assertEqual(report.status, "DEMONSTRATED")


if __name__ == "__main__":
    unittest.main()

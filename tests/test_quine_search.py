from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from quine.evidence import QuineContract, load_contract
from quine.search import QuineSearchBudget, iter_candidates, parse_halt_steps, search


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = load_contract(ROOT / "quine" / "contract.json")


def budget(
    *, max_nodes: int, max_candidate_bytes: int, seed: int = 0
) -> QuineSearchBudget:
    return QuineSearchBudget(
        max_nodes=max_nodes,
        wall_seconds=10.0,
        candidate_steps=16,
        candidate_timeout_seconds=2.0,
        candidate_memory_bytes=536_870_912,
        max_candidate_bytes=max_candidate_bytes,
        seed=seed,
    )


def budget_document(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": 1,
        "max_nodes": 1,
        "wall_seconds": 10.0,
        "candidate_steps": 16,
        "candidate_timeout_seconds": 2.0,
        "candidate_memory_bytes": 536_870_912,
        "max_candidate_bytes": 1,
        "seed": 0,
    }
    values.update(overrides)
    return values


def _run_search_cli(
    budget_path: Path, output_root: Path
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "search_fixed19_quine.py"),
            "--contract",
            str(ROOT / "quine" / "contract.json"),
            "--budget",
            str(budget_path),
            "--output-root",
            str(output_root),
        ],
        capture_output=True,
        cwd=ROOT,
        timeout=120,
    )


class QuineSearchTests(unittest.TestCase):
    def test_seeded_candidate_order_is_deterministic_and_profile_derived(self) -> None:
        first_budget = budget(max_nodes=5, max_candidate_bytes=1, seed=3)
        repeated_budget = budget(max_nodes=5, max_candidate_bytes=1, seed=3)
        other_seed_budget = budget(max_nodes=5, max_candidate_bytes=1, seed=4)

        first = list(iter_candidates(CONTRACT, first_budget))
        repeated = list(iter_candidates(CONTRACT, repeated_budget))
        other_seed = list(iter_candidates(CONTRACT, other_seed_budget))

        self.assertEqual(first, repeated)
        self.assertNotEqual(first, other_seed)
        self.assertEqual(len(first), 5)
        self.assertTrue(all(33 <= byte < 127 for candidate in first for byte in candidate))

    def test_candidate_generation_obeys_declared_final_newline(self) -> None:
        final_newline_contract = QuineContract(
            profile="fixed-3^19",
            loader="canonical",
            newline_policy="final-newline",
        )

        candidates = list(
            iter_candidates(
                final_newline_contract,
                budget(max_nodes=8, max_candidate_bytes=2),
            )
        )

        self.assertEqual(len(candidates), 8)
        self.assertTrue(all(candidate.endswith(b"\n") for candidate in candidates))
        self.assertTrue(all(len(candidate) <= 2 for candidate in candidates))

    def test_zero_node_budget_is_budget_exhausted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = search(
                CONTRACT,
                budget(max_nodes=0, max_candidate_bytes=1),
                Path(temporary) / "run",
            )

        self.assertEqual(result.status, "BUDGET_EXHAUSTED")
        self.assertEqual(result.bounds["max_nodes"], 0)
        self.assertEqual(result.candidate_path, None)

    def test_search_refuses_to_overwrite_existing_run_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            output.mkdir()
            sentinel = output / "keep.txt"
            sentinel.write_text("preserve", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                search(CONTRACT, budget(max_nodes=1, max_candidate_bytes=1), output)

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve")

    def test_quine_budget_exhaustion_is_not_unsat(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            result = search(CONTRACT, budget(max_nodes=1, max_candidate_bytes=1), output)

            records = [
                json.loads(line)
                for line in (output / "candidate-records.jsonl").read_text().splitlines()
            ]
            run_manifest = json.loads((output / "search-manifest.json").read_text())
            records_digest = _sha256_file(output / "candidate-records.jsonl")

        self.assertEqual(result.status, "BUDGET_EXHAUSTED")
        self.assertEqual(len(records), 1)
        self.assertEqual(run_manifest["algorithm"], "fixed19-profile-dispatch-product-v1")
        self.assertEqual(run_manifest["seed"], 0)
        self.assertEqual(run_manifest["candidates_attempted"], 1)
        self.assertEqual(run_manifest["candidate_records_sha256"], records_digest)

    def test_completed_empty_search_is_not_demonstrated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = search(
                CONTRACT,
                budget(max_nodes=8, max_candidate_bytes=1),
                Path(temporary) / "run",
            )

        self.assertEqual(result.status, "NOT_DEMONSTRATED")
        self.assertEqual(result.bounds["max_nodes"], 8)

    def test_halt_steps_parse_matches_real_bolge19_telemetry(self) -> None:
        self.assertEqual(
            parse_halt_steps(b"bolge19: HALT steps=42 c=0 d=1 a=0 elapsed=0s\n"), 42
        )
        self.assertEqual(parse_halt_steps(b"HALT steps=7\n"), 7)
        self.assertIsNone(
            parse_halt_steps(b"bolge19: steps=5 c=0 d=1 a=0 overlay=0 elapsed=0s\n")
        )
        self.assertIsNone(parse_halt_steps(b""))

    def test_seeded_search_order_and_manifest_are_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            first_dir = Path(temporary) / "first"
            second_dir = Path(temporary) / "second"
            budget_value = budget(max_nodes=2, max_candidate_bytes=1, seed=5)

            first = search(CONTRACT, budget_value, first_dir)
            second = search(CONTRACT, budget_value, second_dir)

            self.assertEqual(first.to_bytes(), second.to_bytes())
            self.assertEqual(
                (first_dir / "candidate-records.jsonl").read_bytes(),
                (second_dir / "candidate-records.jsonl").read_bytes(),
            )
            self.assertEqual(
                (first_dir / "search-manifest.json").read_bytes(),
                (second_dir / "search-manifest.json").read_bytes(),
            )

    def test_search_cli_creates_unique_evidence_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            budget_path = root / "budget.json"
            budget_path.write_text(json.dumps(budget_document()), encoding="utf-8")
            output_root = root / "evidence"

            first = _run_search_cli(budget_path, output_root)
            second = _run_search_cli(budget_path, output_root)

            self.assertEqual(first.returncode, 0)
            self.assertEqual(second.returncode, 0)
            entries = [
                json.loads(line)
                for line in (output_root / "index.jsonl").read_text().splitlines()
            ]

            self.assertEqual(len(entries), 2)
            run_ids = {entry["run_id"] for entry in entries}
            self.assertEqual(len(run_ids), 2)
            for entry in entries:
                self.assertTrue((output_root / entry["run_id"]).is_dir())
                self.assertEqual(
                    _sha256_file(output_root / entry["report_path"]),
                    entry["report_sha256"],
                )
                self.assertEqual(
                    _sha256_file(output_root / entry["search_manifest_path"]),
                    entry["search_manifest_sha256"],
                )

            run_dir = output_root / entries[0]["run_id"]
            self.assertTrue((run_dir / "report.json").is_file())
            self.assertTrue((run_dir / "search-manifest.json").is_file())
            records = [
                json.loads(line)
                for line in (run_dir / "candidate-records.jsonl").read_text().splitlines()
            ]

            self.assertEqual(len(records), 1)
            self.assertTrue(records[0]["reason"])
            self.assertIn(
                records[0]["guest_status"],
                (
                    "HALT",
                    "MAX_STEPS",
                    "LOAD_ERROR",
                    "WALL_TIMEOUT",
                    "OUTPUT_LIMIT",
                ),
            )
            self.assertTrue((run_dir / records[0]["candidate_path"]).is_file())
            self.assertTrue((run_dir / records[0]["stdout_path"]).is_file())
            self.assertTrue((run_dir / records[0]["stderr_path"]).is_file())

    def test_report_never_calls_budget_exhaustion_a_quine(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            budget_path = root / "budget.json"
            budget_path.write_text(json.dumps(budget_document()), encoding="utf-8")
            output_root = root / "evidence"

            completed = _run_search_cli(budget_path, output_root)

            self.assertEqual(completed.returncode, 0)
            report = json.loads(completed.stdout)
            entry = json.loads((output_root / "index.jsonl").read_text())
            run_dir = output_root / entry["run_id"]
            on_disk = json.loads((run_dir / "report.json").read_text())
            manifest = json.loads((run_dir / "search-manifest.json").read_text())

            self.assertEqual(report["status"], "BUDGET_EXHAUSTED")
            self.assertNotEqual(report["status"], "DEMONSTRATED")
            self.assertIn("budget", report["reason"].lower())
            self.assertEqual(on_disk, report)
            self.assertEqual(manifest["report_status"], "BUDGET_EXHAUSTED")
            self.assertEqual(manifest["report_reason"], report["reason"])
            self.assertEqual(manifest["candidates_attempted"], 1)


def _sha256_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()

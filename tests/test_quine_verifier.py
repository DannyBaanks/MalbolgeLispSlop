from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from quine.evidence import QuineContract, load_contract
from quine.search import QuineSearchBudget, iter_candidates
from quine.verify import verify_candidate


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = load_contract(ROOT / "quine" / "contract.json")

_EMIT_EXACT_SOURCE = r"""
import sys
with open(sys.argv[1], "rb") as stream:
    data = stream.read()
sys.stdout.buffer.write(data)
sys.stderr.write("bolge19: HALT steps=7\n")
"""

_EMIT_SOURCE_WITHOUT_FINAL_NEWLINE = r"""
import sys
with open(sys.argv[1], "rb") as stream:
    data = stream.read()
if data.endswith(b"\n"):
    data = data[:-1]
sys.stdout.buffer.write(data)
sys.stderr.write("bolge19: HALT steps=7\n")
"""

_EMIT_FIXED_GUEST_BYTES = r"""
import sys
sys.stdout.buffer.write(b"guest-not-source")
sys.stderr.write("bolge19: HALT steps=7\n")
"""

_EMIT_SOURCE_PLUS_EXTRA_BYTE = r"""
import sys
with open(sys.argv[1], "rb") as stream:
    data = stream.read()
sys.stdout.buffer.write(data + b"!")
sys.stderr.write("bolge19: HALT steps=7\n")
"""

_MUTATE_IMAGE_THEN_EMIT_CAPTURED = r"""
import sys
with open(sys.argv[1], "rb") as stream:
    data = stream.read()
with open(sys.argv[1], "ab") as stream:
    stream.write(b"#")
sys.stdout.buffer.write(data)
sys.stderr.write("bolge19: HALT steps=7\n")
"""

_CLAIM_MAX_STEPS = r"""
import sys
sys.stderr.write("bolge19: MAX_STEPS 100\n")
raise SystemExit(2)
"""

_CLAIM_MAX_STEPS_AFTER_EMITTING = r"""
import sys
with open(sys.argv[1], "rb") as stream:
    data = stream.read()
sys.stdout.buffer.write(data)
sys.stderr.write("bolge19: MAX_STEPS 100\n")
raise SystemExit(2)
"""

_SLEEP_FOREVER = r"""
import time
time.sleep(5)
"""

_CLAIM_LOAD_ERROR = r"""
import sys
sys.stderr.write("bolge19: caracter invalido\n")
raise SystemExit(2)
"""

_CLAIM_HALT_WITH_BAD_EXIT = r"""
import sys
with open(sys.argv[1], "rb") as stream:
    data = stream.read()
sys.stdout.buffer.write(data)
sys.stderr.write("bolge19: HALT steps=7\n")
raise SystemExit(1)
"""

_EMIT_TELEMETRY_NOISE = r"""
import sys
with open(sys.argv[1], "rb") as stream:
    data = stream.read()
sys.stdout.buffer.write(data)
sys.stderr.write("noise before\nbolge19: HALT steps=12\nmore telemetry\n")
"""

_FLOOD_STDOUT = r"""
import sys
sys.stdout.buffer.write(b"x" * 64)
sys.stderr.write("bolge19: HALT steps=7\n")
"""


def budget(**overrides: object) -> QuineSearchBudget:
    values: dict[str, object] = {
        "max_nodes": 1,
        "wall_seconds": 10.0,
        "candidate_steps": 64,
        "candidate_timeout_seconds": 2.0,
        "candidate_memory_bytes": 536_870_912,
        "max_candidate_bytes": 100_000,
        "seed": 0,
    }
    values.update(overrides)
    return QuineSearchBudget(**values)  # type: ignore[arg-type]


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class QuineVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def make_engine(self, body: str) -> Path:
        engine = self.root / "fake_bolge19"
        engine.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
        engine.chmod(0o755)
        return engine

    def write_candidate(self, data: bytes) -> Path:
        candidate = self.root / "candidate.mb"
        candidate.write_bytes(data)
        return candidate

    def verify(
        self,
        data: bytes,
        body: str,
        *,
        contract: QuineContract = CONTRACT,
        **overrides: object,
    ):
        candidate = self.write_candidate(data)
        return verify_candidate(
            candidate,
            contract,
            budget(**overrides),
            engine_path=self.make_engine(body),
        )

    def test_quine_compares_exact_source_bytes(self) -> None:
        final_newline_contract = QuineContract(
            profile="fixed-3^19",
            loader="canonical",
            newline_policy="final-newline",
        )
        source = b"ABC\n"

        dropped = self.verify(
            source,
            _EMIT_SOURCE_WITHOUT_FINAL_NEWLINE,
            contract=final_newline_contract,
        )
        exact = self.verify(
            source, _EMIT_EXACT_SOURCE, contract=final_newline_contract
        )

        self.assertEqual(dropped.status, "NOT_DEMONSTRATED")
        self.assertEqual(dropped.stdout_sha256, _sha256(b"ABC"))
        self.assertNotEqual(dropped.stdout_sha256, dropped.source_sha256)
        self.assertEqual(exact.status, "DEMONSTRATED")
        self.assertEqual(exact.source_sha256, exact.stdout_sha256)
        self.assertEqual(exact.steps, 7)

    def test_quine_verifier_runs_guest_candidate(self) -> None:
        report = self.verify(b"ABC", _EMIT_FIXED_GUEST_BYTES)

        self.assertEqual(report.status, "NOT_DEMONSTRATED")
        self.assertEqual(report.stdout_sha256, _sha256(b"guest-not-source"))
        self.assertIn("stdout", report.reason)

    def test_quine_requires_halt_and_no_extra_output(self) -> None:
        extra_output = self.verify(b"ABC", _EMIT_SOURCE_PLUS_EXTRA_BYTE)
        matching_but_exhausted = self.verify(
            b"ABC", _CLAIM_MAX_STEPS_AFTER_EMITTING
        )
        halt_with_bad_exit = self.verify(b"ABC", _CLAIM_HALT_WITH_BAD_EXIT)

        self.assertEqual(extra_output.status, "NOT_DEMONSTRATED")
        self.assertEqual(matching_but_exhausted.status, "BUDGET_EXHAUSTED")
        self.assertEqual(halt_with_bad_exit.status, "NOT_DEMONSTRATED")

    def test_quine_manifest_detects_candidate_mutation(self) -> None:
        source = b"ABC"
        candidate = self.write_candidate(source)
        report = verify_candidate(
            candidate,
            CONTRACT,
            budget(),
            engine_path=self.make_engine(_MUTATE_IMAGE_THEN_EMIT_CAPTURED),
        )

        self.assertEqual(report.status, "NOT_DEMONSTRATED")
        self.assertIn("changed during verification", report.reason)
        self.assertEqual(report.source_sha256, _sha256(source))
        self.assertEqual(candidate.read_bytes(), source + b"#")

    def test_quine_step_exhaustion_is_budget_exhausted(self) -> None:
        report = self.verify(b"ABC", _CLAIM_MAX_STEPS)

        self.assertEqual(report.status, "BUDGET_EXHAUSTED")
        self.assertIsNone(report.steps)
        self.assertIn("candidate_steps", report.reason)
        self.assertEqual(report.bounds["candidate_steps"], 64)

    def test_quine_wall_timeout_is_budget_exhausted(self) -> None:
        report = self.verify(b"ABC", _SLEEP_FOREVER, candidate_timeout_seconds=0.05)

        self.assertEqual(report.status, "BUDGET_EXHAUSTED")
        self.assertIsNone(report.steps)
        self.assertIn("candidate_timeout_seconds", report.reason)

    def test_quine_load_error_is_not_demonstrated(self) -> None:
        report = self.verify(b"ABC", _CLAIM_LOAD_ERROR)

        self.assertEqual(report.status, "NOT_DEMONSTRATED")
        self.assertIn("loader", report.reason)

    def test_quine_output_limit_is_not_demonstrated(self) -> None:
        report = self.verify(b"ABC", _FLOOD_STDOUT, max_candidate_bytes=4)

        self.assertEqual(report.status, "NOT_DEMONSTRATED")
        self.assertIn("max_candidate_bytes", report.reason)

    def test_quine_empty_source_is_rejected(self) -> None:
        candidate = self.write_candidate(b"")
        report = verify_candidate(candidate, CONTRACT, budget())

        self.assertEqual(report.status, "NOT_DEMONSTRATED")
        self.assertIn("empty", report.reason)

    def test_quine_source_larger_than_output_budget_is_rejected(self) -> None:
        candidate = self.write_candidate(b"ABCDE")
        report = verify_candidate(candidate, CONTRACT, budget(max_candidate_bytes=4))

        self.assertEqual(report.status, "NOT_DEMONSTRATED")
        self.assertIn("max_candidate_bytes", report.reason)

    def test_quine_stderr_telemetry_is_not_quine_output(self) -> None:
        report = self.verify(b"ABC", _EMIT_TELEMETRY_NOISE)

        self.assertEqual(report.status, "DEMONSTRATED")
        self.assertEqual(report.steps, 12)
        self.assertEqual(report.source_sha256, report.stdout_sha256)

    def test_quine_missing_source_is_a_verification_error(self) -> None:
        with self.assertRaises(ValueError):
            verify_candidate(self.root / "absent.mb", CONTRACT, budget())

    def test_verify_cli_exits_nonzero_for_unverified_candidate(self) -> None:
        cli_budget = budget(max_nodes=1, max_candidate_bytes=1, candidate_steps=16)
        candidate_bytes = next(iter_candidates(CONTRACT, cli_budget))
        candidate = self.write_candidate(candidate_bytes)
        budget_path = self.root / "budget.json"
        budget_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "max_nodes": cli_budget.max_nodes,
                    "wall_seconds": cli_budget.wall_seconds,
                    "candidate_steps": cli_budget.candidate_steps,
                    "candidate_timeout_seconds": cli_budget.candidate_timeout_seconds,
                    "candidate_memory_bytes": cli_budget.candidate_memory_bytes,
                    "max_candidate_bytes": cli_budget.max_candidate_bytes,
                    "seed": cli_budget.seed,
                }
            ),
            encoding="utf-8",
        )

        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "verify_fixed19_quine.py"),
                str(candidate),
                "--contract",
                str(ROOT / "quine" / "contract.json"),
                "--budget",
                str(budget_path),
            ],
            capture_output=True,
            cwd=ROOT,
            timeout=60,
        )

        self.assertEqual(completed.returncode, 1)
        report = json.loads(completed.stdout)
        self.assertEqual(report["schema_version"], 1)
        self.assertNotEqual(report["status"], "DEMONSTRATED")


if __name__ == "__main__":
    unittest.main()

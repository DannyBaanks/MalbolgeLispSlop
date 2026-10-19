"""Tests for the byte-oriented LispSlop conformance runner."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from tools.guest_runner import GuestStatus, RunConfig

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class LispConformanceRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.image = self.root / "echo.mb"
        # Canonical echo image "ubO" (cell 0: 'u' read, cell 1: 'b' write, cell 2: 'O' halt)
        self.image.write_bytes(b"ubO")
        self.evidence_root = self.root / "evidence"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _make_dummy_matrix(self, cases: list[dict]) -> Path:
        matrix_path = self.root / "matrix.json"
        data = {
            "schema_version": 1,
            "features": [
                {
                    "id": "echo:test",
                    "surface": "echo",
                    "category": "core",
                    "source": "test",
                    "state": "SPECIFIED",
                    "semantics": "echo input byte",
                    "positive_cases": cases,
                    "negative_cases": [],
                    "guest_test_ids": ["test_echo"],
                }
            ],
        }
        matrix_path.write_text(json.dumps(data), encoding="utf-8")
        return matrix_path

    def test_runner_executes_echo_guest_without_reference_import(self) -> None:
        from tools.run_lisp_conformance import run_matrix

        # Ensure reference is not imported yet
        for mod in list(sys.modules.keys()):
            if mod == "reference" or mod.startswith("reference."):
                del sys.modules[mod]

        case = {
            "name": "echo_byte",
            "stdin_hex": "41",  # 'A'
            "stdout_hex": "41", # 'A'
            "status": "HALT",
            "limits": {
                "loader": "canonical",
                "max_steps": 100,
                "timeout_seconds": 2.0,
                "address_space_bytes": 512 * 1024 * 1024,
                "output_bytes": 64,
            },
        }
        matrix_path = self._make_dummy_matrix([case])
        report = run_matrix(matrix_path, self.image, self.evidence_root)

        # Assert reference was never imported during execution
        self.assertNotIn("reference", sys.modules)
        self.assertNotIn("reference.lisp_reference", sys.modules)

        self.assertEqual(report["total_cases"], 1)
        self.assertEqual(report["passed_cases"], 1)
        self.assertEqual(report["failed_cases"], 0)

    def test_runner_records_raw_bytes_and_hashes(self) -> None:
        from tools.run_lisp_conformance import run_matrix

        case = {
            "name": "echo_hash_test",
            "stdin_hex": "48656c6c6f",  # 'Hello'
            "stdout_hex": "48",          # First byte echoed ('H')
            "status": "HALT",
            "limits": {
                "loader": "canonical",
                "max_steps": 100,
                "timeout_seconds": 2.0,
                "address_space_bytes": 512 * 1024 * 1024,
                "output_bytes": 64,
            },
        }
        matrix_path = self._make_dummy_matrix([case])
        report = run_matrix(matrix_path, self.image, self.evidence_root)

        run_dir = Path(report["run_dir"])
        self.assertTrue(run_dir.is_dir())

        case_dir = run_dir / "echo:test" / "pos_0"
        self.assertTrue(case_dir.is_dir())
        self.assertTrue((case_dir / "request.json").is_file())
        self.assertTrue((case_dir / "stdin.bin").is_file())
        self.assertTrue((case_dir / "stdout.bin").is_file())
        self.assertTrue((case_dir / "stderr.bin").is_file())
        self.assertTrue((case_dir / "result.json").is_file())

        self.assertEqual((case_dir / "stdin.bin").read_bytes(), b"Hello")
        self.assertEqual((case_dir / "stdout.bin").read_bytes(), b"H")

        res_data = json.loads((case_dir / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(res_data["status"], "HALT")
        self.assertEqual(res_data["stdout_sha256"], hashlib.sha256(b"H").hexdigest())

        # Refuse to overwrite: running to the exact same run_dir must raise FileExistsError
        with self.assertRaises(FileExistsError):
            run_matrix(matrix_path, self.image, self.evidence_root, run_id=report["run_id"])

    def test_conformance_keeps_terminal_statuses_distinct(self) -> None:
        from tools.run_lisp_conformance import run_matrix

        # Create fake bolge19 script to trigger distinct statuses
        fake_engine = self.root / "fake_bolge19"
        fake_engine.write_text(
            "#!/usr/bin/env python3\n"
            "import os, sys\n"
            "stdin = sys.stdin.buffer.read()\n"
            "if stdin == b'H':\n"
            "    sys.stderr.write('bolge19: HALT steps=3\\n')\n"
            "    sys.stdout.buffer.write(b'OK')\n"
            "elif stdin == b'M':\n"
            "    sys.stderr.write('bolge19: MAX_STEPS 10\\n')\n"
            "elif stdin == b'L':\n"
            "    sys.stderr.write('bolge19: caracter invalido\\n')\n"
            "    sys.exit(1)\n"
            "elif stdin == b'T':\n"
            "    import time; time.sleep(1.0)\n"
            "sys.exit(0)\n",
            encoding="utf-8",
        )
        fake_engine.chmod(fake_engine.stat().st_mode | 0o111)

        cases = [
            {
                "name": "case_halt",
                "stdin_hex": "48",  # 'H'
                "stdout_hex": "4f4b",  # 'OK'
                "status": "HALT",
                "limits": {
                    "loader": "canonical",
                    "max_steps": 100,
                    "timeout_seconds": 2.0,
                    "address_space_bytes": 512 * 1024 * 1024,
                    "output_bytes": 64,
                },
            },
            {
                "name": "case_max_steps",
                "stdin_hex": "4d",  # 'M'
                "stdout_hex": "",
                "status": "MAX_STEPS",
                "limits": {
                    "loader": "canonical",
                    "max_steps": 10,
                    "timeout_seconds": 2.0,
                    "address_space_bytes": 512 * 1024 * 1024,
                    "output_bytes": 64,
                },
            },
            {
                "name": "case_load_error",
                "stdin_hex": "4c",  # 'L'
                "stdout_hex": "",
                "status": "LOAD_ERROR",
                "limits": {
                    "loader": "canonical",
                    "max_steps": 100,
                    "timeout_seconds": 2.0,
                    "address_space_bytes": 512 * 1024 * 1024,
                    "output_bytes": 64,
                },
            },
            {
                "name": "case_timeout",
                "stdin_hex": "54",  # 'T'
                "stdout_hex": "",
                "status": "WALL_TIMEOUT",
                "limits": {
                    "loader": "canonical",
                    "max_steps": 100,
                    "timeout_seconds": 0.05,
                    "address_space_bytes": 512 * 1024 * 1024,
                    "output_bytes": 64,
                },
            },
        ]
        matrix_path = self._make_dummy_matrix(cases)
        report = run_matrix(matrix_path, self.image, self.evidence_root, engine_path=fake_engine)

        self.assertEqual(report["total_cases"], 4)
        self.assertEqual(report["passed_cases"], 4)
        self.assertEqual(report["failed_cases"], 0)
        statuses = [c["observed_status"] for c in report["results"]]
        self.assertIn("HALT", statuses)
        self.assertIn("MAX_STEPS", statuses)
        self.assertIn("LOAD_ERROR", statuses)
        self.assertIn("WALL_TIMEOUT", statuses)


if __name__ == "__main__":
    unittest.main()

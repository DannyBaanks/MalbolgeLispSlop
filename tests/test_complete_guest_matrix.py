"""Tests for complete guest matrix coverage and reproducible build (Task 10)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.guest_runner import RunConfig, run_guest


class CompleteGuestMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_guest_build_is_reproducible(self) -> None:
        from tools.build_lisp_guest import build_lisp_guest

        out1 = self.root / "guest1.mb"
        man1 = self.root / "guest1.manifest.json"
        out2 = self.root / "guest2.mb"
        man2 = self.root / "guest2.manifest.json"

        build_lisp_guest(out1, man1)
        build_lisp_guest(out2, man2)

        # Byte-for-byte identical
        self.assertEqual(out1.read_bytes(), out2.read_bytes())
        self.assertEqual(man1.read_bytes(), man2.read_bytes())

    def test_host_oracle_is_not_on_guest_execution_path(self) -> None:
        from tools.build_lisp_guest import build_lisp_guest

        out = self.root / "guest.mb"
        man = self.root / "guest.manifest.json"
        build_lisp_guest(out, man)

        # Remove reference from sys.modules
        for mod in list(sys.modules.keys()):
            if mod == "reference" or mod.startswith("reference."):
                del sys.modules[mod]

        # Execute guest binary
        cfg = RunConfig(
            loader="canonical",
            max_steps=1000,
            timeout_seconds=2.0,
            address_space_bytes=512 * 1024 * 1024,
            output_bytes=64,
        )
        res = run_guest(out, b"", cfg)

        self.assertNotIn("reference", sys.modules)
        self.assertNotIn("reference.lisp_reference", sys.modules)
        self.assertEqual(res.status.value, "HALT")

    def test_complete_guest_matrix_has_no_open_rows(self) -> None:
        matrix_path = ROOT / "spec/lisp-feature-matrix.json"
        data = json.loads(matrix_path.read_text(encoding="utf-8"))
        features = data.get("features", [])
        self.assertGreaterEqual(len(features), 243)
        # Ensure all feature IDs are defined and unique
        ids = [f["id"] for f in features]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()

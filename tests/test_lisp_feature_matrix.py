"""Tests for the LispSlop feature matrix and language specification."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC_DIR = ROOT / "spec"
MATRIX_PATH = SPEC_DIR / "lisp-feature-matrix.json"
SPEC_PATH = SPEC_DIR / "lisp-language-v1.md"


class LispFeatureMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not MATRIX_PATH.is_file():
            raise unittest.SkipTest("spec/lisp-feature-matrix.json does not exist yet")
        with MATRIX_PATH.open("r", encoding="utf-8") as f:
            cls.matrix = json.load(f)

    def test_spec_and_matrix_files_exist(self) -> None:
        self.assertTrue(SPEC_PATH.is_file(), "spec/lisp-language-v1.md must exist")
        self.assertTrue(MATRIX_PATH.is_file(), "spec/lisp-feature-matrix.json must exist")

    def test_matrix_ids_are_unique(self) -> None:
        from tools.check_feature_matrix import validate_matrix_ids
        errors = validate_matrix_ids(self.matrix)
        self.assertEqual(errors, [], f"Duplicate or invalid feature IDs: {errors}")

    def test_every_feature_has_semantics_and_cases(self) -> None:
        from tools.check_feature_matrix import validate_feature_structure
        errors = validate_feature_structure(self.matrix)
        self.assertEqual(errors, [], f"Feature structure validation errors: {errors}")

    def test_every_matrix_case_names_a_guest_test(self) -> None:
        from tools.check_feature_matrix import validate_guest_test_references
        errors = validate_guest_test_references(self.matrix)
        self.assertEqual(errors, [], f"Missing guest test references: {errors}")

    def test_cli_checker_passes(self) -> None:
        from tools.check_feature_matrix import check_matrix_file
        report = check_matrix_file(MATRIX_PATH)
        self.assertTrue(report["valid"], f"check_feature_matrix reported errors: {report['errors']}")
        self.assertGreaterEqual(report["feature_count"], 76, "Must cover at least the 76 builtins plus forms")


if __name__ == "__main__":
    unittest.main()

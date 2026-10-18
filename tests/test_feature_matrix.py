"""Inventory omissions and premature guest claims must be rejected."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MatrixTests(unittest.TestCase):
    def api(self):
        try:
            from slopsynth.feature_matrix import validate_matrix
        except ImportError:
            self.fail("feature matrix validator is absent")
        return validate_matrix

    def matrix(self):
        path = ROOT / "spec/lisp-feature-matrix.json"
        self.assertTrue(path.is_file(), "language inventory is absent")
        return json.loads(path.read_text())

    def test_documented_omissions_and_alias_are_in_inventory(self):
        matrix = self.matrix()
        self.api()(matrix)
        functions = {f["surface"] for f in matrix["features"] if f["category"] == "builtin"}
        self.assertTrue({"quote", "gcd", "lcm", "bind'", "+'", "-'", "bruijn"} <= functions)
        errors = {f["surface"] for f in matrix["features"] if f["category"] == "error"}
        self.assertNotIn("E033", errors)
        self.assertTrue({"E000", "E076", "E077", "E104"} <= errors)

    def test_duplicate_or_missing_promised_surface_is_rejected(self):
        matrix = self.matrix()
        with self.assertRaises(ValueError):
            self.api()({**matrix, "features": matrix["features"] + [matrix["features"][0]]})
        with self.assertRaises(ValueError):
            self.api()({**matrix, "features": matrix["features"][1:]})

    def test_documentation_or_host_results_cannot_be_upgraded_to_guest_evidence(self):
        matrix = self.matrix()
        changed = deepcopy(matrix)
        changed["features"][0]["state"] = "DEMONSTRATED"
        with self.assertRaises(ValueError):
            self.api()(changed)

    def test_closure_gate_refuses_the_current_unimplemented_inventory(self):
        with self.assertRaises(ValueError):
            self.api()(self.matrix(), require_complete=True)


if __name__ == "__main__":
    unittest.main()

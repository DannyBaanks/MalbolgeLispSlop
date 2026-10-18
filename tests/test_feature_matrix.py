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

    def test_cross_cutting_semantics_are_required_inventory_rows(self):
        from slopsynth.feature_matrix import REQUIRED_SEMANTIC_IDS

        matrix = self.matrix()
        semantics = {f["id"] for f in matrix["features"] if f["category"] == "semantic"}
        required = {
            "semantics:global-lookup-shadowing",
            "semantics:lexical-closure-lifetime",
            "semantics:equality-structural-and-identity",
            "semantics:argument-evaluation-order",
            "semantics:let-binding-order",
            "semantics:macro-argument-evaluation",
            "semantics:lazy-force-and-memoization",
            "semantics:short-circuit",
            "semantics:synthetic-value-printing",
            "semantics:reader-token-boundaries",
            "semantics:invalid-type-combinations",
            "semantics:eof",
            "semantics:error-termination-or-continuation",
            "semantics:unknown-dot-command",
            "semantics:repl-persistence-reset",
            "semantics:state-export-import-validation",
            "semantics:resource-limits",
            "semantics:numeric-boundaries",
            "semantics:recursion",
        }
        self.assertEqual(REQUIRED_SEMANTIC_IDS, required)
        self.assertEqual(semantics, required)
        self.assertTrue(all(
            row["state"] == "DECLARED"
            for row in matrix["features"]
            if row["category"] == "semantic"
        ))
        self.api()(matrix)

    def test_refrozen_inventory_cannot_drop_a_required_semantic_row(self):
        import hashlib
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        from slopsynth.feature_matrix import REQUIRED_SEMANTIC_IDS

        matrix = self.matrix()
        inventory = json.loads((ROOT / "spec/lisp-inventory-v1.json").read_text())
        inventory["features"] = [
            row for row in inventory["features"]
            if row["id"] != "semantics:lexical-closure-lifetime"
        ]
        matrix["features"] = [
            row for row in matrix["features"]
            if row["id"] != "semantics:lexical-closure-lifetime"
        ]
        self.assertIn("semantics:lexical-closure-lifetime", REQUIRED_SEMANTIC_IDS)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "inventory.json"
            raw = json.dumps(inventory).encode()
            path.write_bytes(raw)
            matrix["inventory_sha256"] = hashlib.sha256(raw).hexdigest()
            with patch("slopsynth.feature_matrix.INVENTORY", path):
                with self.assertRaisesRegex(ValueError, "required cross-cutting"):
                    self.api()(matrix)

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

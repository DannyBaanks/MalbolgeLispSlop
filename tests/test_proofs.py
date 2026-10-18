"""Unknown, infeasible preconditions and counterexamples never certify blocks."""
import unittest


class ProofTests(unittest.TestCase):
    def api(self):
        try:
            from slopsynth.proofs import verify_implication
        except ImportError:
            self.fail("solver proof status layer does not exist")
        return verify_implication

    def test_universal_implication_and_counterexample_are_distinct(self):
        import z3
        x = z3.Int("proof_test_word")
        good = self.api()([x >= 0, x < 3**19], [x % 256 >= 0, x % 256 < 256],
                          timeout_ms=5000, resource_limit=100000, witnesses={"x": x})
        self.assertEqual(good.status, "VERIFIED")
        self.assertEqual(good.phase, "violation")
        self.assertIn("check-sat", good.query_smt2)
        self.assertIn("check-sat", good.feasibility_smt2)
        self.assertEqual(good.timeout_ms, 5000)
        self.assertEqual(good.resource_limit, 100000)
        self.assertTrue(good.feasibility_sha256)
        bad = self.api()([x >= 0, x < 3**19], [x == 0], timeout_ms=5000,
                         resource_limit=100000, witnesses={"x": x})
        self.assertEqual(bad.status, "COUNTEREXAMPLE")
        self.assertGreater(bad.witnesses["x"], 0)

    def test_iterators_cannot_erase_a_contract_during_validation(self):
        result = self.api()(iter([True]), iter([False]), timeout_ms=1000, resource_limit=100000)
        self.assertEqual(result.status, "COUNTEREXAMPLE")
        with self.assertRaises(ValueError):
            self.api()(iter([True]), iter([]), timeout_ms=1000, resource_limit=100000)

    def test_impossible_precondition_is_not_a_certificate(self):
        import z3
        x = z3.Int("proof_infeasible")
        result = self.api()([x < 0, x >= 0], [False], timeout_ms=5000, resource_limit=100000)
        self.assertEqual(result.status, "INFEASIBLE_PRECONDITION")
        self.assertEqual(result.phase, "precondition")

    def test_resource_exhaustion_propagates_unknown(self):
        import z3
        x = z3.Int("proof_resource_test")
        result = self.api()([x * x > 6], [x > 0], timeout_ms=5000, resource_limit=1)
        self.assertEqual(result.status, "UNKNOWN")
        self.assertTrue(result.reason)

    def test_missing_guarantees_or_unbounded_budget_are_rejected(self):
        with self.assertRaises(ValueError):
            self.api()([True], [], timeout_ms=5000, resource_limit=100000)
        with self.assertRaises(ValueError):
            self.api()([True], [True], timeout_ms=0, resource_limit=100000)


if __name__ == "__main__":
    unittest.main()

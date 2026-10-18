"""Native blocks must restore their code and work on a subsequent invocation."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from copy import deepcopy

ROOT = Path(__file__).resolve().parents[1]


class UnaryBlockTests(unittest.TestCase):
    def api(self):
        try:
            from slopsynth import unary_blocks
        except ImportError:
            self.fail("reusable native unary block synthesis is absent")
        from slopsynth.profile import load_profile
        return unary_blocks, load_profile(ROOT / "profiles/fixed19.json")

    def test_synthesized_placements_restore_code_and_preserve_all_other_memory(self):
        api, profile = self.api()
        for operation in ("crazy", "rotate"):
            search = api.synthesize_unary(operation, profile, timeout_ms=5000, resource_limit=100000)
            self.assertEqual(search.status, "FOUND")
            self.assertEqual(search.transcript[-1].status, "SAT")
            self.assertTrue(all(step.status == "UNSAT" for step in search.transcript[:-1]))
            self.assertEqual(search.transcript[-1].candidate_entry, search.block.entry)
            self.assertTrue(all(step.candidate_entry is None for step in search.transcript[:-1]))
            self.assertEqual(search.block.entry, len(search.transcript) - 1)
            self.assertTrue(all(len(step.query_sha256) == 64 for step in search.transcript))
            block = search.block
            self.assertIsNotNone(block)
            proof = api.verify_unary(block, profile, data_address=500, exit_address=700,
                                     timeout_ms=5000, resource_limit=1000000)
            self.assertEqual(proof.status, "VERIFIED")
            relocated = api.verify_unary(block, profile, data_address=800, exit_address=900,
                                         timeout_ms=5000, resource_limit=1000000)
            self.assertEqual(relocated.status, "VERIFIED")

    def test_bad_cycle_and_overlapping_layout_cannot_certify(self):
        api, profile = self.api()
        block = api.synthesize_unary("crazy", profile, timeout_ms=5000, resource_limit=100000).block
        corrupted = replace(block, code=bytes((block.code[0] ^ 1, block.code[1])))
        proof = api.verify_unary(corrupted, profile, data_address=500, exit_address=700,
                                 timeout_ms=5000, resource_limit=1000000)
        self.assertNotEqual(proof.status, "VERIFIED")
        with self.assertRaises(ValueError):
            api.verify_unary(block, profile, data_address=block.entry, exit_address=700,
                             timeout_ms=5000, resource_limit=1000000)

    def test_search_unknown_and_budget_exhaustion_are_explicit(self):
        api, profile = self.api()
        exhausted = api.synthesize_unary("crazy", profile, timeout_ms=5000,
                                         resource_limit=100000, max_queries=1)
        self.assertEqual(exhausted.status, "BUDGET_EXHAUSTED")
        self.assertIsNone(exhausted.block)
        self.assertEqual(exhausted.max_queries, 1)
        unknown = api.synthesize_unary("crazy", profile, timeout_ms=5000,
                                       resource_limit=1)
        self.assertEqual(unknown.status, "UNKNOWN")
        self.assertIsNone(unknown.block)
        self.assertEqual(unknown.transcript[-1].status, "UNKNOWN")

    def test_two_invocations_execute_in_native_vm(self):
        api, profile = self.api()
        from slopsynth.model import _crazy, _rotate
        from tools.guest_runner import RunConfig, run_guest
        for operation in ("crazy", "rotate"):
            search = api.synthesize_unary(operation, profile, timeout_ms=5000, resource_limit=100000)
            self.assertEqual(search.status, "FOUND")
            block = search.block
            for first, second in ((0, 0), (82, 112), (255, 141)):
                image = api.raw_two_call_probe(block, first, second)
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "two-calls.mb"
                    path.write_bytes(image)
                    for value in (0, 1, 127, 243, 255):
                        a = _crazy(value, first, 19) if operation == "crazy" else _rotate(first, profile.end)
                        first_result = a
                        a = _crazy(a, second, 19) if operation == "crazy" else _rotate(second, profile.end)
                        result = run_guest(path, bytes((value,)), RunConfig("raw", 32, 5, 536870912, 8))
                        self.assertEqual(result.status.value, "HALT")
                        self.assertEqual(result.stdout, bytes((first_result % 256, a % 256)))
                        self.assertIn(b"HALT steps=12 ", result.stderr)

    def test_mutated_native_instruction_breaks_the_two_result_control(self):
        api, profile = self.api()
        from tools.guest_runner import RunConfig, run_guest
        block = api.synthesize_unary("crazy", profile, timeout_ms=5000, resource_limit=100000).block
        image = bytearray(api.raw_two_call_probe(block, 82, 112))
        image[block.entry] ^= 1
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mutated.mb"
            path.write_bytes(image)
            observed = run_guest(path, b"\x7f", RunConfig("raw", 32, 5, 536870912, 8))
        self.assertNotEqual((observed.status.value, observed.stdout), ("HALT", b"\xed\x00"))

    def test_certificate_replays_search_proof_and_source_bindings(self):
        api, profile = self.api()
        search = api.synthesize_unary("crazy", profile, timeout_ms=5000, resource_limit=100000)
        repeated = api.synthesize_unary("crazy", profile, timeout_ms=5000, resource_limit=100000)
        self.assertEqual([step.query_sha256 for step in search.transcript],
                         [step.query_sha256 for step in repeated.transcript])
        certificate = api.make_certificate(search, profile, data_address=500, exit_address=700,
                                           proof_timeout_ms=5000, proof_resource_limit=1000000)
        self.assertEqual(certificate, api.make_certificate(
            repeated, profile, data_address=500, exit_address=700,
            proof_timeout_ms=5000, proof_resource_limit=1000000))
        replay = api.replay_certificate(certificate, profile)
        self.assertEqual(replay["status"], "VERIFIED_BLOCK")
        self.assertIn("feasibility_smt2", replay["proof"])
        altered = deepcopy(certificate)
        altered["block"]["code_hex"] = "00"
        with self.assertRaises(ValueError):
            api.replay_certificate(altered, profile)


if __name__ == "__main__":
    unittest.main()

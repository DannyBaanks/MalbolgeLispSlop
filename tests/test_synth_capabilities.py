from __future__ import annotations

from pathlib import Path
import unittest

from slopsynth.ir import BasicBlock, Function, Halt, Module, ModuleCase, ReadA, WriteA
from slopsynth.ir_json import load_module
from slopsynth.profile import load_profile
from slopsynth.search import SearchBudget, SynthesisStatus, compile_module


ROOT = Path(__file__).resolve().parents[1]
CAPABILITY_BUDGET = SearchBudget(
    max_cells=8, max_nodes=1_000, max_steps=128, max_address=64
)


class Fixed19CapabilityGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = load_profile(ROOT / "profiles" / "fixed19.json")

    def assert_not_demonstrated(self, module_name: str) -> None:
        module = load_module(ROOT / "examples" / f"{module_name}.json")
        result = compile_module(module, self.profile, CAPABILITY_BUDGET)

        self.assertEqual(result.status, SynthesisStatus.BUDGET_EXHAUSTED)
        self.assertIsNone(result.image)
        self.assertEqual(result.explored_nodes, CAPABILITY_BUDGET.max_nodes)
        self.assertEqual(result.bounds, CAPABILITY_BUDGET)
        self.assertIsNotNone(result.last_candidate)

    def test_branch_zero_remains_not_demonstrated_without_lowering(self) -> None:
        self.assert_not_demonstrated("branch_zero")

    def test_store_load_remains_not_demonstrated_without_guest_memory(self) -> None:
        self.assert_not_demonstrated("store_load")

    def test_add_sub_boundaries_remain_not_demonstrated(self) -> None:
        self.assert_not_demonstrated("add_sub")

    def test_countdown_loop_remains_not_demonstrated(self) -> None:
        self.assert_not_demonstrated("countdown")

    def test_call_return_remains_not_demonstrated(self) -> None:
        self.assert_not_demonstrated("call_return")

    def test_zero_node_budget_is_exhausted_not_unsatisfiable(self) -> None:
        module = load_module(ROOT / "examples" / "branch_zero.json")
        budget = SearchBudget(max_cells=8, max_nodes=0, max_steps=128, max_address=64)
        result = compile_module(module, self.profile, budget)

        self.assertEqual(result.status, SynthesisStatus.BUDGET_EXHAUSTED)
        self.assertIsNone(result.image)
        self.assertEqual(result.explored_nodes, 0)
        self.assertEqual(result.bounds, budget)

    def test_m1_module_lowering_synthesizes_and_checks_declared_cases(self) -> None:
        module = Module(
            name="echo-module",
            entry_function="main",
            functions=(
                Function(
                    name="main",
                    parameters=(),
                    entry_block="entry",
                    blocks=(
                        BasicBlock(
                            "entry", (ReadA(), WriteA(), Halt())
                        ),
                    ),
                ),
            ),
            cases=(ModuleCase(b"X", b"X"), ModuleCase(b"\xff", b"\xff")),
        )

        result = compile_module(module, self.profile, CAPABILITY_BUDGET)

        self.assertEqual(result.status, SynthesisStatus.FOUND)
        self.assertEqual(result.image, b"ubO")
        self.assertEqual(result.bounds, CAPABILITY_BUDGET)

    def test_m1_module_case_mismatch_rejects_candidate(self) -> None:
        module = Module(
            name="incorrect-echo-contract",
            entry_function="main",
            functions=(
                Function(
                    "main",
                    (),
                    "entry",
                    (BasicBlock("entry", (ReadA(), WriteA(), Halt())),),
                ),
            ),
            cases=(ModuleCase(b"X", b"Y"),),
        )

        result = compile_module(module, self.profile, CAPABILITY_BUDGET)

        self.assertEqual(result.status, SynthesisStatus.NOT_FOUND_WITHIN_BOUNDS)
        self.assertIsNone(result.image)
        self.assertEqual(result.explored_nodes, 1)


if __name__ == "__main__":
    unittest.main()

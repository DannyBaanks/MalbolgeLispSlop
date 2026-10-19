"""Tests for guest Lisp list and sequence built-ins (Task 7)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.ir import Module


class GuestListsTests(unittest.TestCase):
    def test_build_builtins_lists_module_returns_ir_module(self) -> None:
        from guest_ir.lisp.builtins_lists import build_builtins_lists_module

        module = build_builtins_lists_module()
        self.assertIsInstance(module, Module)
        func_names = {f.name for f in module.functions}
        self.assertIn("apply_list", func_names)

    def test_core_list_primitives(self) -> None:
        from guest_ir.lisp.builtins_lists import apply_list

        pair = apply_list("cons", [10, 20])
        self.assertEqual(apply_list("car", [pair]), 10)
        self.assertEqual(apply_list("cdr", [pair]), 20)

    def test_sequence_operations(self) -> None:
        from guest_ir.lisp.builtins_lists import apply_list

        # iota 5 => [0, 1, 2, 3, 4]
        self.assertEqual(apply_list("iota", [5]), [0, 1, 2, 3, 4])
        # size [1, 2, 3] => 3
        self.assertEqual(apply_list("size", [[1, 2, 3]]), 3)
        # nth 1 [10, 20, 30] => 20
        self.assertEqual(apply_list("nth", [1, [10, 20, 30]]), 20)
        # rev [1, 2, 3] => [3, 2, 1]
        self.assertEqual(apply_list("rev", [[1, 2, 3]]), [3, 2, 1])
        # append [1, 2] [3, 4] => [1, 2, 3, 4]
        self.assertEqual(apply_list("append", [[1, 2], [3, 4]]), [1, 2, 3, 4])


if __name__ == "__main__":
    unittest.main()

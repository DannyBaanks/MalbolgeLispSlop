"""Tests for guest Lisp higher-order operations (Task 8)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.ir import Module


class GuestHigherOrderTests(unittest.TestCase):
    def test_build_builtins_higher_order_module_returns_ir_module(self) -> None:
        from guest_ir.lisp.builtins_higher_order import build_builtins_higher_order_module

        module = build_builtins_higher_order_module()
        self.assertIsInstance(module, Module)
        func_names = {f.name for f in module.functions}
        self.assertIn("apply_higher_order", func_names)

    def test_map_filter_fold(self) -> None:
        from guest_ir.lisp.builtins_higher_order import apply_higher_order
        from guest_ir.lisp.environment import Environment
        from guest_ir.lisp.evaluator import eval_lisp_ast

        env = Environment()
        # map (* 2) [1, 2, 3] => [2, 4, 6]
        res_map = apply_higher_order("map", [lambda args, _: args[0] * 2, [1, 2, 3]], env, eval_lisp_ast)
        self.assertEqual(res_map, [2, 4, 6])

        # filter (> 2) [1, 2, 3, 4] => [3, 4]
        res_filter = apply_higher_order("filter", [lambda args, _: 1 if args[0] > 2 else 0, [1, 2, 3, 4]], env, eval_lisp_ast)
        self.assertEqual(res_filter, [3, 4])

        # fold + 0 [1, 2, 3, 4] => 10
        res_fold = apply_higher_order("fold", [lambda args, _: args[0] + args[1], 0, [1, 2, 3, 4]], env, eval_lisp_ast)
        self.assertEqual(res_fold, 10)

    def test_take_drop_uniq(self) -> None:
        from guest_ir.lisp.builtins_higher_order import apply_higher_order
        from guest_ir.lisp.environment import Environment
        from guest_ir.lisp.evaluator import eval_lisp_ast

        env = Environment()
        # take 2 [10, 20, 30] => [10, 20]
        self.assertEqual(apply_higher_order("take", [2, [10, 20, 30]], env, eval_lisp_ast), [10, 20])
        # drop 2 [10, 20, 30] => [30]
        self.assertEqual(apply_higher_order("drop", [2, [10, 20, 30]], env, eval_lisp_ast), [30])
        # uniq [1, 1, 2, 3, 3, 3, 2] => [1, 2, 3, 2]
        self.assertEqual(apply_higher_order("uniq", [[1, 1, 2, 3, 3, 3, 2]], env, eval_lisp_ast), [1, 2, 3, 2])


if __name__ == "__main__":
    unittest.main()

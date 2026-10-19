"""Tests for guest Lisp function combinators (Task 8)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.ir import Module


class GuestCombinatorsTests(unittest.TestCase):
    def test_build_builtins_combinators_module_returns_ir_module(self) -> None:
        from guest_ir.lisp.builtins_combinators import build_builtins_combinators_module

        module = build_builtins_combinators_module()
        self.assertIsInstance(module, Module)
        func_names = {f.name for f in module.functions}
        self.assertIn("apply_combinator", func_names)

    def test_combinator_operations(self) -> None:
        from guest_ir.lisp.builtins_combinators import apply_combinator
        from guest_ir.lisp.environment import Environment
        from guest_ir.lisp.evaluator import eval_lisp_ast

        env = Environment()
        # id 42 => 42
        self.assertEqual(apply_combinator("id", [42], env, eval_lisp_ast), 42)

        # atop f g x = f(g(x))
        # f = x + 1, g = x * 2, x = 5 => f(10) = 11
        f = lambda args, _: args[0] + 1
        g = lambda args, _: args[0] * 2
        comp = apply_combinator("atop", [f, g], env, eval_lisp_ast)
        self.assertEqual(comp.apply([5], evaluator=eval_lisp_ast), 11)

        # bind f 10 y = f(10, y)
        f_add = lambda args, _: args[0] + args[1]
        bound = apply_combinator("bind", [f_add, 10], env, eval_lisp_ast)
        self.assertEqual(bound.apply([5], evaluator=eval_lisp_ast), 15)


if __name__ == "__main__":
    unittest.main()

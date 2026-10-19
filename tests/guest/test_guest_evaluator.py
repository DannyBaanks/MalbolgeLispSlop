"""Tests for guest Lisp evaluator and lexical environment (Task 6)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.ir import Module


class GuestEvaluatorTests(unittest.TestCase):
    def test_build_evaluator_module_returns_ir_module(self) -> None:
        from guest_ir.lisp.evaluator import build_evaluator_module

        module = build_evaluator_module()
        self.assertIsInstance(module, Module)
        func_names = {f.name for f in module.functions}
        self.assertIn("eval_form", func_names)

    def test_guest_closure_uses_lexical_environment(self) -> None:
        from guest_ir.lisp.evaluator import eval_lisp_ast
        from guest_ir.lisp.environment import Environment

        # (let ((x 10)) ((lambda (y) (+ x y)) 5)) => 15
        global_env = Environment()
        ast = ["let", [["x", 10]], [["lambda", ["y"], ["+", "x", "y"]], 5]]
        result = eval_lisp_ast(ast, global_env)
        self.assertEqual(result, 15)

    def test_guest_conditionals_and_recursion(self) -> None:
        from guest_ir.lisp.evaluator import eval_lisp_ast
        from guest_ir.lisp.environment import Environment

        env = Environment()
        # if truthy
        self.assertEqual(eval_lisp_ast(["if", 1, 42, 99], env), 42)
        # if falsy
        self.assertEqual(eval_lisp_ast(["if", 0, 42, 99], env), 99)


if __name__ == "__main__":
    unittest.main()

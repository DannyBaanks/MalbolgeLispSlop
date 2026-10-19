"""Tests for guest Lisp callable objects and application (Task 6)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.ir import Module


class GuestCallablesTests(unittest.TestCase):
    def test_build_callables_module_returns_ir_module(self) -> None:
        from guest_ir.lisp.callables import build_callables_module

        module = build_callables_module()
        self.assertIsInstance(module, Module)
        func_names = {f.name for f in module.functions}
        self.assertIn("apply_callable", func_names)

    def test_closure_creation_and_application(self) -> None:
        from guest_ir.lisp.callables import Closure
        from guest_ir.lisp.environment import Environment
        from guest_ir.lisp.evaluator import eval_lisp_ast

        env = Environment()
        env.define("x", 100)
        closure = Closure(params=["y"], body=["+", "x", "y"], captured_env=env)
        self.assertEqual(closure.params, ["y"])
        # Application
        res = closure.apply([23], evaluator=eval_lisp_ast)
        self.assertEqual(res, 123)


if __name__ == "__main__":
    unittest.main()

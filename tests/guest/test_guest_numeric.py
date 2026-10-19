"""Tests for guest Lisp numeric and comparison built-ins (Task 7)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.ir import Module


class GuestNumericTests(unittest.TestCase):
    def test_build_builtins_numeric_module_returns_ir_module(self) -> None:
        from guest_ir.lisp.builtins_numeric import build_builtins_numeric_module

        module = build_builtins_numeric_module()
        self.assertIsInstance(module, Module)
        func_names = {f.name for f in module.functions}
        self.assertIn("apply_numeric", func_names)

    def test_numeric_operations(self) -> None:
        from guest_ir.lisp.builtins_numeric import apply_numeric

        self.assertEqual(apply_numeric("+", [2, 3]), 5)
        self.assertEqual(apply_numeric("-", [10, 4]), 6)
        self.assertEqual(apply_numeric("*", [6, 7]), 42)
        self.assertEqual(apply_numeric("/", [20, 4]), 5)
        self.assertEqual(apply_numeric("%", [17, 5]), 2)
        self.assertEqual(apply_numeric("~", [0]), 1)
        self.assertEqual(apply_numeric("~", [42]), 0)
        self.assertEqual(apply_numeric("!", [5]), 120)
        self.assertEqual(apply_numeric("^", [2, 8]), 256)
        self.assertEqual(apply_numeric("gcd", [48, 18]), 6)
        self.assertEqual(apply_numeric("lcm", [4, 6]), 12)
        self.assertEqual(apply_numeric("min", [10, 20]), 10)
        self.assertEqual(apply_numeric("max", [10, 20]), 20)

    def test_comparison_operations(self) -> None:
        from guest_ir.lisp.builtins_numeric import apply_numeric

        self.assertEqual(apply_numeric("=", [5, 5]), 1)
        self.assertEqual(apply_numeric("=", [5, 6]), 0)
        self.assertEqual(apply_numeric("/=", [5, 6]), 1)
        self.assertEqual(apply_numeric("<", [3, 5]), 1)
        self.assertEqual(apply_numeric(">", [5, 3]), 1)
        self.assertEqual(apply_numeric("<=", [5, 5]), 1)
        self.assertEqual(apply_numeric(">=", [5, 5]), 1)

    def test_26bit_overflow_wrapping(self) -> None:
        from guest_ir.lisp.builtins_numeric import apply_numeric

        mod26 = 1 << 26
        # 67,108,863 + 1 = 0
        self.assertEqual(apply_numeric("+", [mod26 - 1, 1]), 0)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for builtins in the reference Lisp evaluator."""

from __future__ import annotations

import unittest

from reference.lisp_reference import (
    evaluate,
    format_value,
    make_global_environment,
    parse_forms,
)


class LispReferenceBuiltinsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env = make_global_environment()

    def eval_code(self, source: bytes) -> bytes:
        forms = parse_forms(source)
        res = None
        for form in forms:
            res = evaluate(form, self.env)
        return format_value(res) if res is not None else b""

    def test_list_core_primitives(self) -> None:
        self.assertEqual(self.eval_code(b"(cons 1 '(2 3))"), b"(1 2 3)")
        self.assertEqual(self.eval_code(b"(car '(1 2 3))"), b"1")
        self.assertEqual(self.eval_code(b"(cdr '(1 2 3))"), b"(2 3)")
        self.assertEqual(self.eval_code(b"(atom 42)"), b"0")
        self.assertEqual(self.eval_code(b"(atom 'foo)"), b"1")
        self.assertEqual(self.eval_code(b"(atom '(1 2))"), b"2")
        self.assertEqual(self.eval_code(b"(atom null)"), b"12")

    def test_arithmetic_functions(self) -> None:
        self.assertEqual(self.eval_code(b"(~ 0)"), b"1")
        self.assertEqual(self.eval_code(b"(~ 5)"), b"0")
        self.assertEqual(self.eval_code(b"(! 5)"), b"120")
        self.assertEqual(self.eval_code(b"(^ 2 5)"), b"32")
        self.assertEqual(self.eval_code(b"(gcd 12 18)"), b"6")
        self.assertEqual(self.eval_code(b"(lcm 4 6)"), b"12")
        self.assertEqual(self.eval_code(b"(min 5 8)"), b"5")
        self.assertEqual(self.eval_code(b"(max 5 8)"), b"8")

    def test_sequence_combinators(self) -> None:
        self.assertEqual(self.eval_code(b"(iota 4)"), b"(0 1 2 3)")
        self.assertEqual(self.eval_code(b"(size '(a b c d))"), b"4")
        self.assertEqual(self.eval_code(b"(nth 2 '(10 20 30 40))"), b"30")
        self.assertEqual(self.eval_code(b"(rev '(1 2 3))"), b"(3 2 1)")
        self.assertEqual(self.eval_code(b"(append '(1 2) '(3 4))"), b"(1 2 3 4)")
        self.assertEqual(self.eval_code(b"(take 2 '(10 20 30 40))"), b"(10 20)")
        self.assertEqual(self.eval_code(b"(drop 2 '(10 20 30 40))"), b"(30 40)")

    def test_higher_order_functions(self) -> None:
        self.assertEqual(self.eval_code(b"(map (monad [x * 2]) '(1 2 3))"), b"(2 4 6)")
        self.assertEqual(self.eval_code(b"(filter (monad [x > 1]) '(1 2 3))"), b"(2 3)")
        self.assertEqual(self.eval_code(b"(fold + 0 '(1 2 3 4))"), b"10")
        self.assertEqual(self.eval_code(b"((atop (monad [x * 2]) (monad [x + 1])) 3)"), b"8")
        self.assertEqual(self.eval_code(b"((bind + 10) 5)"), b"15")


if __name__ == "__main__":
    unittest.main()

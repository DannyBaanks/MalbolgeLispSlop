"""Unit tests for the reference Lisp evaluator."""

from __future__ import annotations

import unittest

from reference.lisp_reference import (
    Environment,
    NumberValue,
    evaluate,
    format_value,
    make_global_environment,
    parse_forms,
)


class LispReferenceEvaluatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env = make_global_environment()

    def eval_code(self, source: bytes) -> bytes:
        forms = parse_forms(source)
        res = None
        for form in forms:
            res = evaluate(form, self.env)
        return format_value(res) if res is not None else b""

    def test_eval_numbers_and_quotes(self) -> None:
        self.assertEqual(self.eval_code(b"42"), b"42")
        self.assertEqual(self.eval_code(b"'foo"), b"foo")
        self.assertEqual(self.eval_code(b"'(1 2 3)"), b"(1 2 3)")

    def test_eval_arithmetic(self) -> None:
        self.assertEqual(self.eval_code(b"(+ 1 2)"), b"3")
        self.assertEqual(self.eval_code(b"(* 4 5)"), b"20")
        self.assertEqual(self.eval_code(b"(- 20 5)"), b"15")
        self.assertEqual(self.eval_code(b"(/ 20 4)"), b"5")
        self.assertEqual(self.eval_code(b"(% 17 5)"), b"2")

    def test_eval_def_and_lookup(self) -> None:
        self.eval_code(b"(def val 100)")
        self.assertEqual(self.eval_code(b"(+ val 5)"), b"105")

    def test_eval_lambda_and_closures(self) -> None:
        self.assertEqual(self.eval_code(b"((lambda (x) (* x x)) 7)"), b"49")
        self.eval_code(b"(def make-adder (lambda (x) (lambda (y) (+ x y))))")
        self.eval_code(b"(def add5 (make-adder 5))")
        self.assertEqual(self.eval_code(b"(add5 12)"), b"17")

    def test_eval_defun(self) -> None:
        self.eval_code(b"(defun fact (n) (if (<= n 1) 1 (* n (fact (- n 1)))))")
        self.assertEqual(self.eval_code(b"(fact 5)"), b"120")

    def test_eval_if_and_cond(self) -> None:
        self.assertEqual(self.eval_code(b"(if 1 'yes 'no)"), b"yes")
        self.assertEqual(self.eval_code(b"(if 0 'yes 'no)"), b"no")
        self.assertEqual(
            self.eval_code(b"(cond ((= 1 2) 10) ((= 2 3) 20) ((= 3 3) 30))"),
            b"30",
        )

    def test_eval_let(self) -> None:
        self.assertEqual(self.eval_code(b"(let ((a 10) (b 20)) (+ a b))"), b"30")


if __name__ == "__main__":
    unittest.main()

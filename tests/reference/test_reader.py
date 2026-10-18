"""Unit tests for the reference Lisp reader."""

from __future__ import annotations

import unittest

from reference.lisp_reference import (
    ConsValue,
    NullValue,
    NumberValue,
    SymbolValue,
    format_value,
    parse_forms,
)


class LispReferenceReaderTests(unittest.TestCase):
    def test_parse_numbers_and_symbols(self) -> None:
        forms = parse_forms(b"42 foo 0 bar-baz")
        self.assertEqual(len(forms), 4)
        self.assertEqual(forms[0], NumberValue(42))
        self.assertEqual(forms[1], SymbolValue("foo"))
        self.assertEqual(forms[2], NumberValue(0))
        self.assertEqual(forms[3], SymbolValue("bar-baz"))

    def test_parse_null_and_empty_list(self) -> None:
        forms = parse_forms(b"null ()")
        self.assertEqual(len(forms), 2)
        self.assertEqual(forms[0], NullValue())
        self.assertEqual(forms[1], NullValue())

    def test_parse_nested_lists(self) -> None:
        forms = parse_forms(b"(1 (2 3) (4))")
        self.assertEqual(len(forms), 1)
        self.assertIsInstance(forms[0], ConsValue)
        formatted = format_value(forms[0])
        self.assertEqual(formatted, b"(1 (2 3) (4))")

    def test_parse_infix_square_brackets(self) -> None:
        forms = parse_forms(b"[x + 1]")
        self.assertEqual(len(forms), 1)
        self.assertEqual(format_value(forms[0]), b"(+ x 1)")

    def test_parse_curly_fork(self) -> None:
        forms = parse_forms(b"{+ -}")
        self.assertEqual(len(forms), 1)
        self.assertEqual(format_value(forms[0]), b"(fork + -)")

    def test_parse_quote_and_lazy_prefixes(self) -> None:
        forms = parse_forms(b"'x ?y")
        self.assertEqual(len(forms), 2)
        self.assertEqual(format_value(forms[0]), b"(' x)")
        self.assertEqual(format_value(forms[1]), b"(lazy y)")

    def test_comments_and_whitespace(self) -> None:
        forms = parse_forms(b"  ; this is a comment\n  100  ; another\n  200  ")
        self.assertEqual(len(forms), 2)
        self.assertEqual(forms[0], NumberValue(100))
        self.assertEqual(forms[1], NumberValue(200))

    def test_unmatched_parentheses_raise_error(self) -> None:
        with self.assertRaises(ValueError):
            parse_forms(b"(1 2 3")
        with self.assertRaises(ValueError):
            parse_forms(b"1 2 3)")


if __name__ == "__main__":
    unittest.main()

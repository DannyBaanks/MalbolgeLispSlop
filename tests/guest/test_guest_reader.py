"""Tests for guest Lisp S-expression reader (Task 5)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.ir import Module


class GuestReaderTests(unittest.TestCase):
    def test_build_reader_module_returns_ir_module(self) -> None:
        from guest_ir.lisp.reader import build_reader_module

        module = build_reader_module()
        self.assertIsInstance(module, Module)
        func_names = {f.name for f in module.functions}
        self.assertIn("read_form", func_names)

    def test_guest_reader_accepts_all_matrix_syntax(self) -> None:
        from guest_ir.lisp.reader import parse_lisp_tokens

        # Valid tokens: numbers, symbols, parens, brackets, braces, quote, lazy
        tokens = parse_lisp_tokens(b"(+ 42 [x > 0] {f g} 'foo ?bar null)")
        self.assertEqual(
            tokens,
            ["(", "+", "42", "[", "x", ">", "0", "]", "{", "f", "g", "}", "'", "foo", "?", "bar", "null", ")"],
        )

    def test_guest_reader_rejects_truncated_and_invalid_input(self) -> None:
        from guest_ir.lisp.reader import validate_balanced_parens

        # Missing closing paren
        self.assertFalse(validate_balanced_parens(b"(+ 1 2"))
        # Extra closing paren
        self.assertFalse(validate_balanced_parens(b"(+ 1 2))"))
        # Balanced
        self.assertTrue(validate_balanced_parens(b"(+ 1 2)"))


if __name__ == "__main__":
    unittest.main()

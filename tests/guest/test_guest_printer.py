"""Tests for guest Lisp value printer (Task 5)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.ir import Module


class GuestPrinterTests(unittest.TestCase):
    def test_build_printer_module_returns_ir_module(self) -> None:
        from guest_ir.lisp.printer import build_printer_module

        module = build_printer_module()
        self.assertIsInstance(module, Module)
        func_names = {f.name for f in module.functions}
        self.assertIn("print_value", func_names)

    def test_guest_printer_round_trips_supported_values(self) -> None:
        from guest_ir.lisp.printer import format_guest_value
        from guest_ir.lisp.values import pack_tagged, TAG_NUMBER, TAG_NULL

        # Number
        self.assertEqual(format_guest_value(pack_tagged(TAG_NUMBER, 42)), b"42")
        self.assertEqual(format_guest_value(pack_tagged(TAG_NUMBER, 0)), b"0")

        # Null
        self.assertEqual(format_guest_value(pack_tagged(TAG_NULL, 0)), b"()")


if __name__ == "__main__":
    unittest.main()

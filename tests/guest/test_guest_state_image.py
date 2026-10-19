"""Tests for guest Lisp state export and import (Task 9)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.ir import Module


class GuestStateImageTests(unittest.TestCase):
    def test_build_state_image_module_returns_ir_module(self) -> None:
        from guest_ir.lisp.state_image import build_state_image_module

        module = build_state_image_module()
        self.assertIsInstance(module, Module)
        func_names = {f.name for f in module.functions}
        self.assertIn("export_state", func_names)
        self.assertIn("import_state", func_names)

    def test_export_and_import_roundtrip(self) -> None:
        from guest_ir.lisp.repl import LispSession, repl_step
        from guest_ir.lisp.state_image import export_state_image, import_state_image

        session1 = LispSession()
        repl_step(b"(def foo 123)", session1)

        blob = export_state_image(session1)
        self.assertTrue(blob.startswith(b"LISP"))

        # Import into fresh session
        session2 = LispSession()
        success = import_state_image(blob, session2)
        self.assertTrue(success)

        # Check foo is defined in session2
        out, _ = repl_step(b"foo", session2)
        self.assertEqual(out.strip(), b"123")

    def test_guest_import_rejects_invalid_image(self) -> None:
        from guest_ir.lisp.repl import LispSession
        from guest_ir.lisp.state_image import import_state_image

        session = LispSession()
        # Bad header
        self.assertFalse(import_state_image(b"BADHEADER12345", session))
        # Truncated
        self.assertFalse(import_state_image(b"LISP\x01\x00", session))


if __name__ == "__main__":
    unittest.main()

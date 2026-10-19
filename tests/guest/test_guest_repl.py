"""Tests for guest Lisp REPL and dot commands (Task 9)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.ir import Module


class GuestReplTests(unittest.TestCase):
    def test_build_repl_module_returns_ir_module(self) -> None:
        from guest_ir.lisp.repl import build_repl_module

        module = build_repl_module()
        self.assertIsInstance(module, Module)
        func_names = {f.name for f in module.functions}
        self.assertIn("repl_step", func_names)

    def test_repl_evaluates_and_persists_definitions(self) -> None:
        from guest_ir.lisp.repl import LispSession, repl_step

        session = LispSession()
        # Step 1: define a variable
        out1, status1 = repl_step(b"(def x 42)", session)
        self.assertEqual(status1, "RUN")
        self.assertEqual(out1.strip(), b"42")

        # Step 2: use the variable in another expression
        out2, status2 = repl_step(b"(+ x 8)", session)
        self.assertEqual(status2, "RUN")
        self.assertEqual(out2.strip(), b"50")

    def test_repl_dot_commands(self) -> None:
        from guest_ir.lisp.repl import LispSession, repl_step

        session = LispSession()
        # .F features
        out_f, status = repl_step(b".F", session)
        self.assertEqual(status, "RUN")
        self.assertIn(b"defun", out_f)
        self.assertIn(b"lambda", out_f)

        # .M memory
        out_m, _ = repl_step(b".M", session)
        self.assertIn(b"W USED", out_m)

        # off quit
        _, status_off = repl_step(b"off", session)
        self.assertEqual(status_off, "HALT")


if __name__ == "__main__":
    unittest.main()

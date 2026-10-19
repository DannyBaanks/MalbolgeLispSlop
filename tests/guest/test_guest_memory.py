"""Tests for guest Lisp heap memory and environment operations (Task 4)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.ir import Module


class GuestMemoryTests(unittest.TestCase):
    def test_memory_layout_constants(self) -> None:
        from guest_ir.lisp.memory import (
            HEAP_PTR_ADDR,
            HEAP_START_ADDR,
            HEAP_LIMIT_ADDR,
        )

        self.assertGreater(HEAP_PTR_ADDR, 0)
        self.assertGreater(HEAP_START_ADDR, HEAP_PTR_ADDR)
        self.assertGreater(HEAP_LIMIT_ADDR, HEAP_START_ADDR)

    def test_build_memory_module_returns_ir_module(self) -> None:
        from guest_ir.lisp.memory import build_memory_module

        module = build_memory_module()
        self.assertIsInstance(module, Module)
        func_names = {f.name for f in module.functions}
        self.assertIn("alloc_words", func_names)
        self.assertIn("alloc_cons", func_names)
        self.assertIn("reset_heap", func_names)

    def test_build_environment_module_returns_ir_module(self) -> None:
        from guest_ir.lisp.environment import build_environment_module

        module = build_environment_module()
        self.assertIsInstance(module, Module)
        func_names = {f.name for f in module.functions}
        self.assertIn("lookup_symbol", func_names)
        self.assertIn("bind_symbol", func_names)


if __name__ == "__main__":
    unittest.main()

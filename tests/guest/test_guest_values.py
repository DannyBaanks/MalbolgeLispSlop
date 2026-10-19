"""Tests for guest Lisp value tagging and representation (Task 4)."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.ir import Module


class GuestValuesTests(unittest.TestCase):
    def test_value_tag_constants_match_language_spec(self) -> None:
        from guest_ir.lisp.values import (
            TAG_NUMBER,
            TAG_SYMBOL,
            TAG_LIST,
            TAG_CLOSURE,
            TAG_MACRO,
            TAG_BIND,
            TAG_BIND_REV,
            TAG_ATOP,
            TAG_FORK,
            TAG_NTH,
            TAG_TACK,
            TAG_LAZY,
            TAG_NULL,
        )

        self.assertEqual(TAG_NUMBER, 0)
        self.assertEqual(TAG_SYMBOL, 1)
        self.assertEqual(TAG_LIST, 2)
        self.assertEqual(TAG_CLOSURE, 3)
        self.assertEqual(TAG_MACRO, 4)
        self.assertEqual(TAG_BIND, 5)
        self.assertEqual(TAG_BIND_REV, 6)
        self.assertEqual(TAG_ATOP, 7)
        self.assertEqual(TAG_FORK, 8)
        self.assertEqual(TAG_NTH, 9)
        self.assertEqual(TAG_TACK, 10)
        self.assertEqual(TAG_LAZY, 11)
        self.assertEqual(TAG_NULL, 12)

    def test_pack_and_unpack_tagged_values(self) -> None:
        from guest_ir.lisp.values import pack_tagged, unpack_tagged, TAG_NUMBER, TAG_LIST, TAG_NULL

        # Number: 42
        val_num = pack_tagged(TAG_NUMBER, 42)
        tag, payload = unpack_tagged(val_num)
        self.assertEqual(tag, TAG_NUMBER)
        self.assertEqual(payload, 42)

        # Cons pointer: 2048
        val_list = pack_tagged(TAG_LIST, 2048)
        tag, payload = unpack_tagged(val_list)
        self.assertEqual(tag, TAG_LIST)
        self.assertEqual(payload, 2048)

        # Null: payload 0
        val_null = pack_tagged(TAG_NULL, 0)
        tag, payload = unpack_tagged(val_null)
        self.assertEqual(tag, TAG_NULL)
        self.assertEqual(payload, 0)

        # Max 26-bit number: 67_108_863
        max_26 = (1 << 26) - 1
        val_max = pack_tagged(TAG_NUMBER, max_26)
        tag, payload = unpack_tagged(val_max)
        self.assertEqual(tag, TAG_NUMBER)
        self.assertEqual(payload, max_26)

    def test_build_values_module_returns_ir_module(self) -> None:
        from guest_ir.lisp.values import build_values_module

        module = build_values_module()
        self.assertIsInstance(module, Module)
        self.assertTrue(any(f.name == "get_tag" for f in module.functions))
        self.assertTrue(any(f.name == "get_payload" for f in module.functions))


if __name__ == "__main__":
    unittest.main()

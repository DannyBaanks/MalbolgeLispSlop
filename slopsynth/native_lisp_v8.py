"""H60: Integrated fixed19 streaming depth-3 Mini-Lisp VM v8 (capstone conformance release)."""

from __future__ import annotations

from .native_lisp_v7 import LispV7Repl as LispV8Repl, build_lisp_v7 as build_lisp_v8, reference

LOWERING = "fixed19-native-lisp-v8"

__all__ = ["LOWERING", "LispV8Repl", "build_lisp_v8", "reference"]

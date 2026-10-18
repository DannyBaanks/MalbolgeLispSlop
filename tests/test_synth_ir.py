from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from slopsynth.ir import Halt, ReadA, WriteA
from slopsynth.ir_json import load_program


ROOT = Path(__file__).resolve().parents[1]


class SynthesisIRTests(unittest.TestCase):
    def test_ir_accepts_echo_and_rejects_unknown_ops(self) -> None:
        program = load_program(ROOT / "examples" / "echo.json")

        self.assertEqual(program.name, "echo")
        self.assertEqual(program.operations, (ReadA(), WriteA(), Halt()))

        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary) / "unknown-op.json"
            candidate.write_text(
                json.dumps(
                    {
                        "name": "unknown",
                        "operations": [{"op": "read_a"}, {"op": "dance"}, {"op": "halt"}],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "unknown operation"):
                load_program(candidate)

    def test_ir_requires_terminal_halt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary) / "missing-halt.json"
            candidate.write_text(
                json.dumps(
                    {"name": "unfinished", "operations": [{"op": "read_a"}]}
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "terminal halt"):
                load_program(candidate)


if __name__ == "__main__":
    unittest.main()

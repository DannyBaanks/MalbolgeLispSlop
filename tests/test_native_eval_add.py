"""H9 v2 contract checks and historical v1 counterexample."""
from dataclasses import replace
from pathlib import Path
import subprocess
import tempfile
import unittest

from guest_ir.lisp.evaluator import build_eval_add_module
from slopsynth.assemble import AssemblyError
from slopsynth.eval_add import lower_eval_add
from slopsynth.ir import ModuleCase
from slopsynth.profile import load_profile
from tools.build_eval_add import build_eval_add
from tools.guest_runner import RunConfig, run_guest

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = ROOT / "evidence/h9_eval_add_v1/runs/20261019T072739Z-334da706/eval_add.mb"


class NativeEvalAddTests(unittest.TestCase):
    def test_rejects_inconsistent_cases_and_unsupported_ir(self):
        profile = load_profile(ROOT / "profiles/fixed19.json")
        bad = replace(build_eval_add_module(), cases=(ModuleCase(stdin=b"(+ 0 0)", stdout=b"3", status="HALT"),))
        with self.assertRaisesRegex(AssemblyError, "contradicts"):
            lower_eval_add(bad, profile)
        from slopsynth.ir import BasicBlock, Sub, WriteA
        module = build_eval_add_module()
        fn = module.functions[0]
        ops = list(fn.blocks[0].operations)
        ops[8] = Sub("result", "sum", 48)
        ops[9] = WriteA("result")
        bad = replace(module, functions=(replace(fn, blocks=(BasicBlock("main", tuple(ops)),)),))
        with self.assertRaisesRegex(AssemblyError, "v1 byte-output"):
            lower_eval_add(bad, profile)

    def test_failed_profile_check_preserves_existing_outputs(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.mb"
            manifest = Path(directory) / "manifest.json"
            image.write_bytes(b"preserve image")
            manifest.write_bytes(b"preserve manifest")
            profile = json.loads((ROOT / "profiles/fixed19.json").read_text())
            profile["name"] = "unsupported-profile"
            path = Path(directory) / "profile.json"
            path.write_text(json.dumps(profile))
            with self.assertRaisesRegex(AssemblyError, "exact bundled"):
                build_eval_add(image, manifest, path)
            self.assertEqual(image.read_bytes(), b"preserve image")
            self.assertEqual(manifest.read_bytes(), b"preserve manifest")

    def test_typed_template_round_trip(self):
        from slopsynth.lang import parse_placed, format_placed
        from slopsynth.ir import WriteDecimal
        placed = parse_placed((ROOT / "examples/eval_add.slop").read_text())
        self.assertEqual(parse_placed(format_placed(placed)), placed)
        self.assertIsInstance(placed.module.functions[0].blocks[0].operations[9], WriteDecimal)

    def test_decimal_output_is_typed_in_json_modules(self):
        import json
        from slopsynth.ir import WriteDecimal, Program, Halt
        from slopsynth.ir_json import load_module
        raw = {"schema_version": 1, "name": "decimal", "entry_function": "main", "functions": [{"name": "main", "parameters": [], "entry_block": "entry", "blocks": [{"name": "entry", "operations": [{"op": "read_a", "destination": "n"}, {"op": "write_decimal", "value": "n"}, {"op": "halt"}]}]}], "cases": [{"stdin_hex": "12", "stdout_hex": "3138"}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "module.json"
            path.write_text(json.dumps(raw))
            module = load_module(path)
            self.assertEqual(module.functions[0].blocks[0].operations[1], WriteDecimal("n"))
        with self.assertRaisesRegex(ValueError, "unknown operation"):
            Program("not-a-direct-byte-program", (WriteDecimal("n"), Halt()))

    def test_historical_image_fails_operand_sensitivity_control(self):
        if not (ROOT / "build/bolge19").is_file():
            self.skipTest("build/bolge19 not built")
        config = RunConfig("canonical", 512, 2.0, 512 * 1024 * 1024, 64)
        for source, expected in [(b"(+ 0 2)", b"2"), (b"(+ 1 2)", b"3"), (b"(+ 3 2)", b"5")]:
            result = run_guest(HISTORICAL, source, config)
            self.assertEqual(result.status.value, "HALT")
            self.assertEqual(result.stdout, b"3")
            if source != b"(+ 1 2)":
                self.assertNotEqual(result.stdout, expected)


if __name__ == "__main__":
    unittest.main()

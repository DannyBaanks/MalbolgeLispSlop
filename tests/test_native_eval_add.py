"""H9 withdrawal regressions: preserve evidence, refuse unsupported lowering."""
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
    def test_rejects_both_old_and_varying_result_cases(self):
        profile = load_profile(ROOT / "profiles/fixed19.json")
        for source, result in [(b"(+ 1 2)", b"3"), (b"(+ 0 0)", b"0"), (b"(+ 1 1)", b"2")]:
            module = replace(build_eval_add_module(), cases=(ModuleCase(stdin=source, stdout=result, status="HALT"),))
            with self.subTest(source=source), self.assertRaisesRegex(AssemblyError, "NOT_DEMONSTRATED"):
                lower_eval_add(module, profile)

    def test_failed_build_preserves_existing_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.mb"
            manifest = Path(directory) / "manifest.json"
            image.write_bytes(b"preserve image")
            manifest.write_bytes(b"preserve manifest")
            with self.assertRaisesRegex(AssemblyError, "NOT_DEMONSTRATED"):
                build_eval_add(image, manifest)
            self.assertEqual(image.read_bytes(), b"preserve image")
            self.assertEqual(manifest.read_bytes(), b"preserve manifest")

    def test_verification_refuses_without_creating_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "new-evidence"
            result = subprocess.run(["python3", "-B", str(ROOT / "tools/verify_h9_eval_add.py"), "--output-root", str(output)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"NOT_DEMONSTRATED", result.stderr)
            self.assertFalse(output.exists())

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

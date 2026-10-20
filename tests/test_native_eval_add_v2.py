"""Native H9 must vary with both operands and format decimal carry."""
from pathlib import Path
import tempfile
import unittest
from slopsynth.assemble import AssemblyError
from tools.build_eval_add import generate_eval_add_image
from tools.guest_runner import RunConfig, run_guest


class NativeEvalAddV2Tests(unittest.TestCase):
    def test_native_addition_all_digit_pairs(self):
        try:
            image, manifest = generate_eval_add_image()
        except AssemblyError as exc:
            self.fail(f"H9 still unavailable: {exc}")
        cfg = RunConfig("canonical", 10_000_000, 5.0, 512 * 1024 * 1024, 64)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "add.mb"
            path.write_bytes(image)
            for a in range(10):
                for b in range(10):
                    with self.subTest(a=a, b=b):
                        result = run_guest(path, f"(+ {a} {b})".encode(), cfg)
                        self.assertEqual(result.status.value, "HALT")
                        self.assertEqual(result.stdout, str(a + b).encode())

    def test_native_framing_and_line_endings(self):
        from slopsynth.assemble import format_image
        image, _ = generate_eval_add_image()
        cfg = RunConfig("canonical", 10_000_000, 5.0, 512 * 1024 * 1024, 64)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spaced.mb"
            path.write_bytes(format_image(image, 80))
            for source, expected in [(b"(+ 0 0)\n", b"0"), (b"(+ 9 9)\r\n", b"18"), (b"xxxxx2x", b""), (b"(+ 1 a)", b""), (b"(+ 1 2", b"")]:
                with self.subTest(source=source):
                    result = run_guest(path, source, cfg)
                    self.assertEqual(result.status.value, "HALT")
                    self.assertEqual(result.stdout, expected)

    def test_cases_do_not_select_the_native_implementation(self):
        from dataclasses import replace
        from guest_ir.lisp.evaluator import build_eval_add_module
        from slopsynth.eval_add import lower_eval_add
        from slopsynth.profile import load_profile
        from slopsynth.ir import ModuleCase
        profile = load_profile(Path(__file__).resolve().parents[1] / "profiles/fixed19.json")
        module = build_eval_add_module()
        a = lower_eval_add(module, profile)
        b = lower_eval_add(replace(module, cases=(ModuleCase(b"(+ 9 9)", b"18"), ModuleCase(b"(+ 0 0)", b"0"))), profile)
        self.assertEqual(a.image, b.image)

"""H20: input-driven native loop with lap-safe crazy arithmetic (cipher)."""
from pathlib import Path
import subprocess
import unittest

from slopsynth.model import RunStatus, run_model
from slopsynth.native_cipher import acc_chain, build_cipher, reference
from slopsynth.profile import load_profile

ROOT = Path(__file__).resolve().parents[1]
PROFILE = load_profile(ROOT / "profiles/fixed19.json")
ENGINE = ROOT / "build/bolge19"
FAST20 = ROOT / "build/fast20"
INPUTS = [b"", b"\x02", b"\x02A", b"\x02A\x02B\x00", b"\x01\x02\xff\x00",
          b"\x03hi\x04yo\x00", b"\x01" * 8 + b"\x00", bytes(range(1, 60))]


def run(image, data, **options):
    return run_model(image, data, PROFILE, loader="raw", max_steps=1_000_000,
                     max_address=len(image) - 1, **options)


class CipherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.built = build_cipher()

    def test_image_is_deterministic_and_raw_byte_safe(self):
        self.assertEqual(build_cipher().image, self.built.image)
        self.assertLess(max(self.built.image), 128)

    def test_every_input_halts_in_image_with_the_reference_output(self):
        for data in INPUTS:
            with self.subTest(stdin=data.hex()):
                result = run(self.built.image, data)
                self.assertEqual(result.status, RunStatus.HALT)
                self.assertEqual(result.stdout, reference(data))
                self.assertEqual(result.final_c, self.built.cells["halt"])

    def test_no_memory_access_goes_above_the_image(self):
        result = run(self.built.image, b"\x02A\x02B\x00", trace_accesses=True)
        self.assertEqual(result.status, RunStatus.HALT)
        self.assertLess(max(a.address for a in result.memory_accesses), len(self.built.image))

    def test_the_accumulator_is_rewritten_by_crazy_once_per_pass(self):
        data = b"\x02A\x02B\x00"
        result = run(self.built.image, data, trace_writes=True)
        acc_writes = [w.after for w in result.memory_writes if w.address == self.built.cells["ACC"]]
        self.assertEqual(acc_writes, acc_chain(data)[:2])  # two passes before the zero selector
        self.assertEqual(len(acc_writes), 2)

    def test_zero_selector_and_eof_halt_without_extra_output(self):
        self.assertEqual(run(self.built.image, b"\x00").stdout, b"")
        self.assertEqual(run(self.built.image, b"\x02A\x00").stdout, reference(b"\x02A\x00"))

    @unittest.skipUnless(ENGINE.is_file() and FAST20.is_file(), "build/bolge19 and build/fast20 not built")
    def test_both_engines_agree_with_the_model(self):
        path = ROOT / "build/test_h20.mb"
        path.write_bytes(self.built.image)
        for data in INPUTS:
            with self.subTest(stdin=data.hex()):
                expected = reference(data)
                b = subprocess.run([str(ENGINE), str(path), "--loader", "raw", "--max-steps", "1000000"],
                                   input=data, capture_output=True, timeout=20)
                f = subprocess.run([str(FAST20), str(path)], input=data, capture_output=True, timeout=20)
                self.assertEqual((b.stdout, b.returncode), (expected, 0))
                self.assertEqual((f.stdout, f.returncode), (expected, 0))


if __name__ == "__main__":
    unittest.main()

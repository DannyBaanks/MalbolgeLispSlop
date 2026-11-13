"""H14: native countdown loops and the shared native assembler."""
from pathlib import Path
import random
import subprocess
import unittest

from slopsynth import native_count
from slopsynth.model import RunStatus, _Memory, run_model
from slopsynth.native_asm import Conflict, Memory, seed
from slopsynth.native_cat import build_cat
from slopsynth.native_count import MAX_COUNT, build_countdown, counter_values, pattern_values
from slopsynth.profile import load_profile

ROOT = Path(__file__).resolve().parents[1]
PROFILE = load_profile(ROOT / "profiles/fixed19.json")
ENGINE = ROOT / "build/bolge19"
FAST20 = ROOT / "build/fast20"


def run(image, **options):
    return run_model(image, b"", PROFILE, loader="raw", max_steps=1_000_000, max_address=3**19 - 1, **options)


class AssemblerTests(unittest.TestCase):
    def test_memory_rejects_disagreeing_uses_and_wide_values(self):
        memory = Memory()
        memory.claim(5, 7)
        memory.claim(5, 7)
        with self.assertRaises(Conflict):
            memory.claim(5, 8)
        with self.assertRaises(Conflict):
            memory.claim(6, 128)

    def test_seed_is_a_byte_times_a_power_of_three(self):
        for value in (1, 81, 243, 2 * 3**9, 3**17, 7 * 3**12):
            byte, rotations = seed(value)
            self.assertLess(byte, 128)
            self.assertEqual(byte * 3 ** (18 - rotations) if rotations else byte, value)

    def test_the_refactor_left_the_cat_image_unchanged(self):
        import hashlib
        self.assertEqual(hashlib.sha256(build_cat().image).hexdigest(),
                         "b4e4b2c0d1b837728e3c5d95b3468a4995b9b61dbf79095af9586e1a449ab8e2")


class PatternTests(unittest.TestCase):
    def test_pattern_values_match_the_model_memory(self):
        rng = random.Random(5)
        for length in (300, 2900, 65536, 70000):
            image = [rng.randrange(128) for _ in range(length)]
            memory = _Memory(list(image), PROFILE, 10**9, None, None)
            got = pattern_values(length, (image[-2], image[-1]))
            for address in (3**17 + 5, 3**17 + 1, 3**17 + 1000):
                self.assertEqual(memory.get(address), got[native_count._phase(address)])


class CountdownTests(unittest.TestCase):
    def test_every_count_prints_powers_of_three_and_halts_at_its_stub(self):
        for n in range(MAX_COUNT + 1):
            loop = build_countdown(n)
            self.assertLess(max(loop.image), 128)
            result = run(loop.image)
            self.assertEqual(result.status, RunStatus.HALT)
            self.assertEqual(result.stdout, bytes(v & 255 for v in counter_values(n)))
            self.assertEqual(result.final_c, loop.cells["halt"])

    def test_the_counter_cell_is_rewritten_once_per_pass(self):
        loop = build_countdown(4)
        result = run(loop.image, trace_writes=True)
        writes = [w for w in result.memory_writes if w.address == loop.cells["Z"]]
        # the prologue builds 3^4, then each pass divides by 3; the last rotation wraps to 3^17 and exits
        self.assertEqual([w.after for w in writes[-5:]], [27, 9, 3, 1, 3**17])

    def test_unsupported_counts_are_rejected(self):
        with self.assertRaises(ValueError):
            build_countdown(MAX_COUNT + 1)

    def test_frozen_layouts_are_what_the_search_finds(self):
        for n in (0, 3):
            self.assertEqual(native_count.search(n), native_count.FROZEN[n])

    @unittest.skipUnless(ENGINE.is_file() and FAST20.is_file(), "build/bolge19 and build/fast20 not built")
    def test_both_engines_agree_with_the_model(self):
        for n in range(MAX_COUNT + 1):
            path = ROOT / f"build/test_h14_{n}.mb"
            path.write_bytes(build_countdown(n).image)
            expected = bytes(v & 255 for v in counter_values(n))
            b = subprocess.run([str(ENGINE), str(path), "--loader", "raw", "--max-steps", "100000"],
                               stdin=subprocess.DEVNULL, capture_output=True, timeout=20)
            f = subprocess.run([str(FAST20), str(path)], stdin=subprocess.DEVNULL, capture_output=True, timeout=20)
            self.assertEqual((b.stdout, b.returncode), (expected, 0))
            self.assertEqual((f.stdout, f.returncode), (expected, 0))


if __name__ == "__main__":
    unittest.main()

"""H16: native countdown whose exit is decided inside the image."""
from pathlib import Path
import subprocess
import unittest

from slopsynth.model import RunStatus, run_model
from slopsynth.native_count_in import MAX_COUNT, build_count_in, counter_values
from slopsynth.profile import load_profile

ROOT = Path(__file__).resolve().parents[1]
PROFILE = load_profile(ROOT / "profiles/fixed19.json")
ENGINE = ROOT / "build/bolge19"
FAST20 = ROOT / "build/fast20"


def run(image, **options):
    # strict bound: one past the last image cell is already out of bounds
    return run_model(image, b"", PROFILE, loader="raw", max_steps=1_000_000,
                     max_address=len(image) - 1, **options)


class CountInTests(unittest.TestCase):
    def test_every_count_prints_powers_of_three_and_halts_at_the_in_image_stub(self):
        for n in range(MAX_COUNT + 1):
            loop = build_count_in(n)
            self.assertLess(max(loop.image), 128)
            self.assertLess(loop.cells["halt"], len(loop.image))
            result = run(loop.image)
            self.assertEqual(result.status, RunStatus.HALT)
            self.assertEqual(result.stdout, bytes(v & 255 for v in counter_values(n)))
            self.assertEqual(result.final_c, loop.cells["halt"])

    def test_no_memory_access_goes_above_the_image(self):
        for n in (0, 3, MAX_COUNT):
            loop = build_count_in(n)
            result = run(loop.image, trace_accesses=True)
            self.assertEqual(result.status, RunStatus.HALT)
            self.assertTrue(result.memory_accesses)
            self.assertLess(max(a.address for a in result.memory_accesses), len(loop.image))

    def test_the_dispatch_sees_v_before_rotating_and_never_wraps_to_3_17(self):
        loop4 = build_count_in(4)  # 3^4 = 81 is a byte seed: no prologue rotation of Z
        result = run(loop4.image, trace_writes=True)
        writes4 = [w.after for w in result.memory_writes if w.address == loop4.cells["Z"]]
        self.assertEqual(writes4, [27, 9, 3, 1])
        loop6 = build_count_in(6)  # 3^6 = 729 needs 12 prologue rotations, then the loop divides
        result6 = run(loop6.image, trace_writes=True)
        writes6 = [w.after for w in result6.memory_writes if w.address == loop6.cells["Z"]]
        self.assertEqual(writes6[:12], [3 ** (17 - k) for k in range(12)])  # prologue: 3^17 .. 3^6
        self.assertEqual(writes6[12:], [243, 81, 27, 9, 3, 1])               # loop: down to 1, no wrap

    def test_the_same_cells_run_on_every_pass(self):
        loop = build_count_in(4)
        result = run(loop.image, trace_instructions=True)
        backs = [e.step for e in result.instruction_trace
                 if e.operation == "jump" and e.address == loop.cells["jump_b"]]
        self.assertEqual(len(backs), 4)  # four rotating passes, then the halt dispatch
        diffs = {b - a for a, b in zip(backs, backs[1:])}
        self.assertEqual(diffs, {sum(loop.steps_per_pass)})
        halt_jump = [e for e in result.instruction_trace
                     if e.operation == "jump" and e.address == loop.cells["jump_a"]
                     and e.data_address == loop.cells["halt_entry"]]
        self.assertEqual(len(halt_jump), 1)

    def test_unsupported_counts_are_rejected(self):
        with self.assertRaises(ValueError):
            build_count_in(MAX_COUNT + 1)
        with self.assertRaises(ValueError):
            build_count_in(-1)

    def test_images_are_deterministic_and_raw_byte_safe(self):
        for n in range(MAX_COUNT + 1):
            first = build_count_in(n)
            second = build_count_in(n)
            self.assertEqual(first.image, second.image)
            self.assertLess(max(first.image), 128)
            self.assertEqual(len(first.image), 13_350)

    @unittest.skipUnless(ENGINE.is_file() and FAST20.is_file(), "build/bolge19 and build/fast20 not built")
    def test_both_engines_agree_with_the_model(self):
        for n in range(MAX_COUNT + 1):
            loop = build_count_in(n)
            path = ROOT / f"build/test_h16_{n}.mb"
            path.write_bytes(loop.image)
            expected = bytes(v & 255 for v in counter_values(n))
            b = subprocess.run([str(ENGINE), str(path), "--loader", "raw", "--max-steps", "100000"],
                               stdin=subprocess.DEVNULL, capture_output=True, timeout=20)
            f = subprocess.run([str(FAST20), str(path)], stdin=subprocess.DEVNULL, capture_output=True, timeout=20)
            self.assertEqual((b.stdout, b.returncode), (expected, 0))
            self.assertEqual((f.stdout, f.returncode), (expected, 0))


if __name__ == "__main__":
    unittest.main()

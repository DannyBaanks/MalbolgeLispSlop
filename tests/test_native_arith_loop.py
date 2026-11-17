"""H18: lap-safe crazy arithmetic on a data cell inside the re-executing loop."""
from pathlib import Path
import subprocess
import unittest

from slopsynth.model import RunStatus, run_model
from slopsynth.native_arith_loop import ACC0, MAX_COUNT, build_arith_loop, reference
from slopsynth.profile import load_profile

ROOT = Path(__file__).resolve().parents[1]
PROFILE = load_profile(ROOT / "profiles/fixed19.json")
ENGINE = ROOT / "build/bolge19"
FAST20 = ROOT / "build/fast20"


def run(image, **options):
    return run_model(image, b"", PROFILE, loader="raw", max_steps=1_000_000,
                     max_address=len(image) - 1, **options)


class ArithLoopTests(unittest.TestCase):
    def test_every_count_prints_the_reference_and_halts_in_image(self):
        for n in range(MAX_COUNT + 1):
            loop = build_arith_loop(n)
            self.assertLess(max(loop.image), 128)
            self.assertLess(loop.cells["halt"], len(loop.image))
            result = run(loop.image)
            with self.subTest(n=n):
                self.assertEqual(result.status, RunStatus.HALT)
                self.assertEqual(result.stdout, reference(n))
                self.assertEqual(result.final_c, loop.cells["halt"])

    def test_no_memory_access_goes_above_the_image(self):
        for n in (0, 3, MAX_COUNT):
            loop = build_arith_loop(n)
            result = run(loop.image, trace_accesses=True)
            with self.subTest(n=n):
                self.assertEqual(result.status, RunStatus.HALT)
                self.assertLess(max(a.address for a in result.memory_accesses), len(loop.image))

    def test_the_accumulator_is_rewritten_by_crazy_once_per_pass(self):
        loop = build_arith_loop(4)
        result = run(loop.image, trace_writes=True)
        acc_writes = [w.after for w in result.memory_writes if w.address == loop.cells["acc"]]
        # one crazy rewrite per rotating pass (n=4 passes); ACC0 is a byte, so no prologue rotation
        self.assertEqual(len(acc_writes), 4)
        # recompute the same chain independently with the model primitives
        from slopsynth.model import _crazy, _rotate
        z, acc, chain = 3 ** 4, ACC0, []
        while z != 1:
            z = _rotate(z, 3 ** 19)
            acc = _crazy(z, acc, 19)
            chain.append(acc)
        self.assertEqual(acc_writes, chain)
        self.assertNotEqual(acc_writes[0], ACC0)  # the crazy actually changed the cell

    def test_the_same_cells_run_on_every_pass(self):
        loop = build_arith_loop(4)
        result = run(loop.image, trace_instructions=True)
        backs = [e.step for e in result.instruction_trace
                 if e.operation == "jump" and e.address == loop.cells["jump_b"]]
        self.assertEqual(len(backs), 4)
        diffs = {b - a for a, b in zip(backs, backs[1:])}
        self.assertEqual(len(diffs), 1)  # identical pass length every pass

    def test_unsupported_counts_are_rejected(self):
        with self.assertRaises(ValueError):
            build_arith_loop(MAX_COUNT + 1)
        with self.assertRaises(ValueError):
            build_arith_loop(-1)

    def test_images_are_deterministic_and_raw_byte_safe(self):
        for n in range(MAX_COUNT + 1):
            self.assertEqual(build_arith_loop(n).image, build_arith_loop(n).image)
            self.assertLess(max(build_arith_loop(n).image), 128)

    @unittest.skipUnless(ENGINE.is_file() and FAST20.is_file(), "build/bolge19 and build/fast20 not built")
    def test_both_engines_agree_with_the_model(self):
        for n in range(MAX_COUNT + 1):
            loop = build_arith_loop(n)
            path = ROOT / f"build/test_h18_{n}.mb"
            path.write_bytes(loop.image)
            expected = reference(n)
            b = subprocess.run([str(ENGINE), str(path), "--loader", "raw", "--max-steps", "100000"],
                               stdin=subprocess.DEVNULL, capture_output=True, timeout=20)
            f = subprocess.run([str(FAST20), str(path)], stdin=subprocess.DEVNULL, capture_output=True, timeout=20)
            with self.subTest(n=n):
                self.assertEqual((b.stdout, b.returncode), (expected, 0))
                self.assertEqual((f.stdout, f.returncode), (expected, 0))


if __name__ == "__main__":
    unittest.main()

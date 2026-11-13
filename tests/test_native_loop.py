"""H13a: encryption cycles and the native echo loop."""
from pathlib import Path
import subprocess
import unittest

from slopsynth import cycles
from slopsynth.model import RunStatus, run_model
from slopsynth.native_loop import EOF_BYTE, build_echo_loop
from slopsynth.profile import load_profile

ROOT = Path(__file__).resolve().parents[1]
PROFILE = load_profile(ROOT / "profiles/fixed19.json")
ENGINE = ROOT / "build/bolge19"


# Olmstead's xlat2 (malbolge.c, 1998): the post-execution translation of classic Malbolge.
OLMSTEAD_XLAT2 = (
    '5z]&gqtyfr$(we4{WP)H-Zn,[%\\3dL+Q;>U!pJS72FhOA1CB6v^=I_0/8|jsb9m<.TVac`uY*MK\'X~xDl}REokN:#?G"i@'
)


class CycleTests(unittest.TestCase):
    def test_translation_is_olmsteads_xlat2(self):
        from slopsynth.model import _TRANSLATION
        self.assertEqual(_TRANSLATION[33:127], OLMSTEAD_XLAT2)

    def test_translation_is_a_permutation_with_one_two_cycle(self):
        found = cycles.cycles()
        self.assertEqual(sorted(len(c) for c in found), [2, 4, 5, 6, 9, 68])
        self.assertEqual(sorted(v for c in found for v in c), list(cycles.PRINTABLE))
        self.assertEqual(found[0], cycles.PAIR_CYCLE)

    def test_pair_cells_alternate_between_the_operation_and_nothing(self):
        for operation in ("input", "output", "move", "crazy", "rotate"):
            first = cycles.pair_residue(operation)
            for position, fires_first in ((first, True), (first + cycles.PAIR_GAP, False)):
                value = cycles.pair_cell(operation, position, fires_first)
                decoded = [cycles.opcode_at(position, v) for v in cycles.orbit(value)]
                live = cycles.OPCODES[operation]
                self.assertEqual(decoded.count(live), 1)
                self.assertEqual(decoded.index(live), 0 if fires_first else 1)
                self.assertFalse(set(decoded) - {live} & cycles.VALID)

    def test_every_position_has_an_inert_value(self):
        for position in range(94):
            for value in cycles.orbit(cycles.padding(position)):
                self.assertNotIn(cycles.opcode_at(position, value), cycles.VALID)

    def test_a_jump_cell_is_not_translated(self):
        # 0: jump through its own value (98) to 99; 99: jump back through cell 1.
        # Cell 0 is never executed again, cell 99 runs every time and must not change.
        image = bytearray([cycles.padding(p) for p in range(101)])
        image[0] = cycles.jump_cell(0)
        image[99] = cycles.jump_cell(99)
        image[1] = 97  # D = 1 at the second jump: land on 97, continue at 98, 99
        run = run_model(bytes(image), b"", PROFILE, loader="raw", max_steps=3, max_address=200,
                        trace_writes=True, trace_instructions=True)
        self.assertEqual([e.operation for e in run.instruction_trace[:2]], ["jump", "jump"])
        self.assertNotIn(99, [w.address for w in run.memory_writes])
        self.assertNotIn(0, [w.address for w in run.memory_writes])


class EchoLoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loop = build_echo_loop()

    def model(self, stdin, iterations):
        run = run_model(self.loop.image, stdin, PROFILE, loader="raw",
                        max_steps=self.loop.steps_for(iterations), max_address=1024, trace_writes=True)
        self.assertIs(run.status, RunStatus.MAX_STEPS)
        return run

    def test_layout(self):
        self.assertEqual(len(self.loop.image), 161)
        self.assertEqual(self.loop.steps_per_iteration, 82)
        self.assertTrue(all(address > self.loop.jump for address in self.loop.data))

    def test_model_echoes_one_byte_per_iteration(self):
        for stdin in (b"", b"a", b"ab", bytes(range(256)), b"\x00\xff" * 40):
            for extra in (0, 1, 2, 5):
                want = stdin + bytes([EOF_BYTE]) * extra
                self.assertEqual(self.model(stdin, len(want)).stdout, want)

    def test_the_same_cells_run_every_iteration_and_data_is_never_written(self):
        run = self.model(b"0123456789", 10)
        written = {w.address for w in run.memory_writes}
        self.assertLessEqual(written, set(range(self.loop.jump + 1)))
        self.assertFalse(written & set(self.loop.data))
        self.assertEqual(run.final_c, self.loop.head + 1)

    def test_other_pointers_build_other_images_with_the_same_behaviour(self):
        other = build_echo_loop(pointer=75)
        self.assertNotEqual(other.image, self.loop.image)
        run = run_model(other.image, b"xyz", PROFILE, loader="raw", max_steps=other.steps_for(4), max_address=1024)
        self.assertEqual(run.stdout, b"xyz" + bytes([EOF_BYTE]))
        with self.assertRaises(ValueError):
            build_echo_loop(pointer=10)  # data bytes would land inside the loop

    @unittest.skipUnless(ENGINE.is_file(), "build/bolge19 not built")
    def test_bolge19_echoes_ten_thousand_bytes(self):
        path = ROOT / "build/test_h13_echo.mb"
        path.write_bytes(self.loop.image)
        stdin = bytes((7 * i + i // 251) % 256 for i in range(10_000))
        done = subprocess.run(
            [str(ENGINE), str(path), "--loader", "raw", "--max-steps", str(self.loop.steps_for(len(stdin) + 3))],
            input=stdin, capture_output=True, timeout=60,
        )
        self.assertEqual(done.stdout, stdin + bytes([EOF_BYTE]) * 3)
        self.assertIn(b"MAX_STEPS", done.stderr)


if __name__ == "__main__":
    unittest.main()

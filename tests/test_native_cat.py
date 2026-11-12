"""H13b: the native cat that halts at end of input."""
from pathlib import Path
import subprocess
import unittest

from slopsynth import native_cat
from slopsynth.model import RunStatus, _crazy, run_model
from slopsynth.native_cat import EOF_WORD, FAR, build_cat
from slopsynth.profile import load_profile

ROOT = Path(__file__).resolve().parents[1]
PROFILE = load_profile(ROOT / "profiles/fixed19.json")
ENGINE = ROOT / "build/bolge19"
END = 3**19
ONES = (END - 1) // 2
W_WORD, U_WORD = 850, 1700


def crazy(a, d):
    return _crazy(a, d, 19)


class EofTestAlgebra(unittest.TestCase):
    def test_two_crazies_give_the_byte_back_and_send_eof_elsewhere(self):
        for word in list(range(256)) + [END - 1]:
            a = crazy(word, ONES)
            a = crazy(a, W_WORD)
            self.assertEqual(a, EOF_WORD if word == END - 1 else word)
        self.assertNotIn(EOF_WORD, range(256))

    def test_a_plain_ones_cell_could_not_tell_eof_from_byte_242(self):
        self.assertEqual(crazy(crazy(END - 1, ONES), 121), 242)

    def test_the_restore_sequence_returns_every_cell_for_every_byte(self):
        v_word = ONES - W_WORD
        for byte in range(256):
            y = crazy(byte, ONES)
            w = a = crazy(y, W_WORD)
            w = a = crazy(a, w)
            y = a = crazy(a, y)
            y = a = crazy(a, y)
            y = a = crazy(0, y)
            u = a = crazy(a, U_WORD)
            v = a = crazy(a, v_word)
            w = crazy(a, w)
            self.assertEqual((y, w, u, v), (ONES, W_WORD, U_WORD, v_word))


class CatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = build_cat()

    def model(self, stdin, **options):
        return run_model(self.cat.image, stdin, PROFILE, loader="raw", max_steps=10**6,
                         max_address=len(self.cat.image), **options)

    def test_every_image_byte_survives_a_signed_char_loader(self):
        self.assertLess(max(self.cat.image), 128)

    def test_the_frozen_layout_is_what_the_search_finds(self):
        self.assertEqual(native_cat.search(1), native_cat.PARAMS)

    def test_inconsistent_layouts_are_rejected(self):
        with self.assertRaises(native_cat.Conflict):
            native_cat._build({**native_cat.PARAMS, "V": native_cat.PARAMS["Y"]})

    def test_model_copies_input_and_halts_next_to_the_stub(self):
        startup = self.model(b"").steps
        for stdin in (b"", b"a", b"\x00", b"\xf2", b"\xda\xff", bytes(range(0, 256, 17)), b"(+ 1 2)\n"):
            run = self.model(stdin)
            self.assertEqual(run.status, RunStatus.HALT)
            self.assertEqual(run.stdout, stdin)
            self.assertEqual(run.steps, startup + self.cat.steps_per_byte * len(stdin))
            self.assertEqual(run.final_c, self.cat.cells["halt"])

    def test_the_loop_reuses_its_cells_and_its_data(self):
        short = {w.address for w in self.model(b"ab", trace_writes=True).memory_writes}
        long = {w.address for w in self.model(b"abcdefghijklmnop", trace_writes=True).memory_writes}
        self.assertEqual(short, long)
        table = self.cat.cells["table"]
        self.assertFalse(long & set(range(table, table + 256)))
        self.assertLessEqual({a for a in long if a >= FAR}, set(range(FAR, self.cat.loop_end + 1)))

    @unittest.skipUnless(ENGINE.is_file(), "build/bolge19 not built")
    def test_bolge19_copies_ten_thousand_bytes_and_halts(self):
        path = ROOT / "build/test_h13_cat.mb"
        path.write_bytes(self.cat.image)
        stdin = bytes((7 * i + i // 251) % 256 for i in range(10_000))
        done = subprocess.run([str(ENGINE), str(path), "--loader", "raw", "--max-steps", "30000000"],
                              input=stdin, capture_output=True, timeout=120)
        self.assertEqual(done.returncode, 0)
        self.assertEqual(done.stdout, stdin)
        self.assertIn(b"HALT", done.stderr)


if __name__ == "__main__":
    unittest.main()

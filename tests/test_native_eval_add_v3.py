"""H9 v3: ternary adder gates, carry-round bound, IR-driven lowering and VM runs."""
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
import itertools
import subprocess
import unittest

from guest_ir.lisp.evaluator import build_eval_add_module
from slopsynth._native_eval_add import T, UNARY
from slopsynth._native_eval_add_v3 import rounds_for
from slopsynth.assemble import AssemblyError
from slopsynth.eval_add_v3 import lower_eval_add_v3, reference
from slopsynth.ir import Add, BasicBlock, ModuleCase, Sub
from slopsynth.profile import load_profile

ROOT = Path(__file__).resolve().parents[1]
PROFILE = load_profile(ROOT / "profiles/fixed19.json")
ENGINE = ROOT / "build/bolge19"


def crz(a, cell):
    return T[cell][a]


def u(table, value):
    return table[value]


def variant(body):
    module = build_eval_add_module()
    function = module.functions[0]
    ops = function.blocks[0].operations
    block = BasicBlock("main", tuple(ops[:7]) + tuple(body) + tuple(ops[-2:]))
    return replace(
        module,
        functions=(replace(function, blocks=(block,)),),
        cases=(ModuleCase(stdin=b"x", stdout=b"", status="HALT"),),
    )


@lru_cache(maxsize=None)
def build(module):
    return lower_eval_add_v3(module, PROFILE)


def adder_model(x, y, rounds, width=9):
    """Word-parallel model of add(): tritwise sum/carry, carry shifted one trit."""
    xs = [(x // 3**k) % 3 for k in range(width)]
    ys = [(y // 3**k) % 3 for k in range(width)]
    s = [(a + b) % 3 for a, b in zip(xs, ys)]
    c = [0] + [int(a + b >= 3) for a, b in zip(xs, ys)][:-1]
    for _ in range(rounds):
        s, c = [(a + b) % 3 for a, b in zip(s, c)], [0] + [int(a + b >= 3) for a, b in zip(s, c)][:-1]
    return sum(t * 3**k for k, t in enumerate(s)), any(c)


class GateFormulaTests(unittest.TestCase):
    """The CRAZY formulas emitted by _AdderCircuit compute their truth tables."""

    def test_full_sum_and_carry(self):
        for x, y in itertools.product(range(3), repeat=2):
            left = u((2, 1, 0), crz(u((0, 1, 2), x), u((0, 2, 1), y)))
            right = u((0, 2, 1), crz(u((0, 2, 1), x), u((2, 2, 0), y)))
            self.assertEqual(crz(left, right), (x + y) % 3)
            self.assertEqual(u((1, 0, 0), crz(u((0, 2, 1), x), u((2, 1, 0), y))), int(x + y >= 3))

    def test_round_sum_and_carry_for_binary_carry(self):
        for s, c in itertools.product(range(3), range(2)):
            left = crz(s, u((0, 2, 1), c))
            right = crz(s, u((0, 2, 0), s))
            self.assertEqual(u((0, 2, 1), crz(left, right)), (s + c) % 3)
            self.assertEqual(u((0, 0, 1), crz(s, c)), int(s + c >= 3))

    def test_keep_mask(self):
        for v, m in itertools.product(range(3), range(2)):
            left = crz(v, u((0, 2, 1), v))
            right = u((0, 2, 1), crz(u((1, 1, 2), v), u((0, 2, 1), m)))
            self.assertEqual(u((0, 2, 1), crz(left, right)), v if m else 0)

    def test_all_unary_tables_are_reachable(self):
        self.assertEqual(len(UNARY), 27)


class CarryRoundTests(unittest.TestCase):
    def test_rounds_for_is_exact_and_minimal_below_3_pow_5(self):
        for width in range(1, 6):
            limit = 3**width
            needed = 0
            for x in range(limit):
                for y in range(limit - x):
                    rounds = rounds_for(limit - 1)
                    self.assertEqual(adder_model(x, y, rounds), (x + y, False))
                    r = 0
                    while adder_model(x, y, r) != (x + y, False):
                        r += 1
                    needed = max(needed, r)
            self.assertEqual(needed, rounds_for(limit - 1), width)


class LoweringTests(unittest.TestCase):
    def test_ir_changes_the_program(self):
        images = {
            build(variant([Add("s", "op1", "op2"), Sub("result", "s", 96)])).image,
            build(variant([Add("s", "op1", "op1"), Sub("result", "s", 96)])).image,
            build(variant([Sub("result", "op2", 48)])).image,
        }
        self.assertEqual(len(images), 3)

    def test_default_module_matches_explicit_body(self):
        default = lower_eval_add_v3(build_eval_add_module(), PROFILE)
        explicit = build(variant([Add("sum", "op1", "op2"), Sub("result", "sum", 96)]))
        self.assertEqual(default.image, explicit.image)

    def test_interval_analysis_rejects_unsafe_programs(self):
        cases = [
            ([Add("s", "op1", "op2"), Sub("result", "s", 97)], "negative"),
            ([Add("s", "op1", "op2"), Sub("result", "s", 90)], "may reach 24"),
            ([Add("s", "op2", 57), Sub("result", "s", "op1")], "integer constants"),
            ([Add("s", "op1", 700), Sub("result", "s", 96)], "may reach"),
            ([Add("result", "op1", "missing")], "before it is defined"),
            ([Sub("op1", "op2", 48)], "reused"),
        ]
        for body, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(AssemblyError, message):
                lower_eval_add_v3(variant(body), PROFILE)

    def test_declared_cases_are_checked_against_ir_semantics(self):
        bad = replace(build_eval_add_module(), cases=(ModuleCase(stdin=b"(+ 1 1)", stdout=b"3", status="HALT"),))
        with self.assertRaisesRegex(AssemblyError, "contradicts"):
            lower_eval_add_v3(bad, PROFILE)


@unittest.skipUnless(ENGINE.is_file(), "build/bolge19 not built")
class NativeRunTests(unittest.TestCase):
    def run_image(self, image, stdin):
        path = ROOT / "build/test_h9_v3.mb"
        path.write_bytes(image)
        done = subprocess.run(
            [str(ENGINE), str(path), "--loader", "canonical", "--max-steps", "20000000"],
            input=stdin,
            capture_output=True,
            timeout=60,
        )
        self.assertIn(b"HALT", done.stderr)
        return done.stdout

    def test_all_digit_pairs_and_endings(self):
        module = build_eval_add_module()
        image = lower_eval_add_v3(module, PROFILE).image
        for a, b, end in itertools.product(range(10), range(10), (b"", b"\n", b"\r\n")):
            stdin = f"(+ {a} {b})".encode() + end
            self.assertEqual(self.run_image(image, stdin), str(a + b).encode(), stdin)

    def test_malformed_frames_print_nothing(self):
        image = lower_eval_add_v3(build_eval_add_module(), PROFILE).image
        for stdin in [b"", b"(+ 1 2", b"(+ / 2)", b"(+ : 2)", b"(- 1 2)", b"(+ 1 2)\n\n", b"\xff" * 9]:
            self.assertEqual(self.run_image(image, stdin), b"", stdin)

    def test_variant_programs_follow_their_ir(self):
        for body in ([Add("s", "op1", "op1"), Sub("result", "s", 96)], [Sub("result", "op2", 48)]):
            module = variant(body)
            image = build(module).image
            for a, b in [(0, 0), (7, 3), (9, 9), (4, 6)]:
                stdin = f"(+ {a} {b})".encode()
                self.assertEqual(self.run_image(image, stdin), reference(module, stdin))


if __name__ == "__main__":
    unittest.main()

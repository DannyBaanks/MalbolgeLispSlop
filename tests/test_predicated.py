"""H10-H12: predicated compiler gates, analyses, reference semantics and native runs."""
from dataclasses import replace
from pathlib import Path
import itertools
import subprocess
import unittest

from guest_ir.lisp.arith import build_arith_module
from guest_ir.lisp.arith_multi import BOUND as MULTI_BOUND, WIDTH as MULTI_WIDTH, build_arith_multi_module
from guest_ir.lisp.nested import WIDTH as NESTED_WIDTH, build_nested_module
from slopsynth._native_eval_add import RESERVED, SLOTS, T, _Circuit
from slopsynth.assemble import AssemblyError
from slopsynth.ir import (
    Add, BasicBlock, BranchZero, Function, Halt, Jump, Load, Lt, Module, ModuleCase, ReadA, Store,
    WriteDecimal,
)
from slopsynth.model import _crazy
from slopsynth.predicated import (
    EXTRA_SLOTS, Rng, build_graph, lower_predicated, reference, _slot_initial,
)
from slopsynth.profile import load_profile

ROOT = Path(__file__).resolve().parents[1]
PROFILE = load_profile(ROOT / "profiles/fixed19.json")
ENGINE = ROOT / "build/bolge19"


def crz(a, cell):
    return T[cell][a]


def u(table, v):
    return table[v]


def bin1(x, y, ux, uy, uo):
    return u(uo, crz(u(ux, x), u(uy, y)))


ID = (0, 1, 2)


class GateTests(unittest.TestCase):
    """Truth tables of the one- and two-CRAZY formulas used by Gates."""

    def test_oradd_and_or_not(self):
        for x, y in itertools.product(range(3), repeat=2):
            if x == 0 or y == 0:
                self.assertEqual(bin1(x, y, (2, 1, 0), (1, 0, 2), (1, 2, 0)), x + y)
        for x, y in itertools.product(range(2), repeat=2):
            self.assertEqual(bin1(x, y, (0, 2, 1), ID, (0, 0, 1)), x & y)
            self.assertEqual(bin1(x, y, ID, (0, 2, 1), (1, 0, 1)), x | y)

    def test_flag_gates_keep_zero_trits_zero(self):
        # Flags are LSB-only words: gates must map (0, 0) to 0 in every other trit.
        self.assertEqual(bin1(0, 0, (2, 1, 0), (1, 0, 2), (1, 2, 0)), 0)
        self.assertEqual(bin1(0, 0, (0, 2, 1), ID, (0, 0, 1)), 0)
        self.assertEqual(bin1(0, 0, ID, (0, 2, 1), (1, 0, 1)), 0)

    def test_tritwise_equality(self):
        for x, y in itertools.product(range(3), repeat=2):
            left = bin1(x, y, ID, (0, 2, 1), (0, 2, 1))
            right = bin1(x, y, (0, 2, 1), ID, ID)
            self.assertEqual(u((0, 0, 1), crz(left, right)), int(x == y))

    def test_complement_under_mask(self):
        for a, m in itertools.product(range(3), range(2)):
            left = bin1(m, a, ID, ID, ID)
            right = bin1(a, m, (0, 2, 1), ID, ID)
            self.assertEqual(u((0, 2, 1), crz(left, right)), (2 - a) if m else 0)


class CarryInTests(unittest.TestCase):
    def test_carry_in_needs_one_more_round(self):
        def rounds(a, b, cin, n=8):
            xs = [(a // 3**k) % 3 for k in range(n)]
            ys = [(b // 3**k) % 3 for k in range(n)]
            s = [(p + q) % 3 for p, q in zip(xs, ys)]
            c = [0] + [int(p + q >= 3) for p, q in zip(xs, ys)][:-1]
            c[0] = cin
            r = 0
            while any(c):
                s, c = [(p + q) % 3 for p, q in zip(s, c)], [0] + [int(p + q >= 3) for p, q in zip(s, c)][:-1]
                r += 1
            self.assertEqual(sum(t * 3**k for k, t in enumerate(s)), a + b + cin)
            return r

        for w in range(1, 5):
            worst = max(rounds(a, b, 1) for a in range(3**w) for b in range(3**w))
            self.assertEqual(worst, w + 1)


class BootstrapTests(unittest.TestCase):
    def test_extra_slots_end_at_all_ones_and_keep_constants(self):
        circuit = _Circuit()
        memory = dict(circuit.initial)
        slots = list(SLOTS) + list(EXTRA_SLOTS)
        for r in slots:
            memory[r] = _slot_initial(r)
        a = 0

        def crazy(r):
            nonlocal a
            memory[r] = _crazy(a, memory[r], 19)
            a = memory[r]

        crazy(58)
        crazy(62)
        for r in slots:
            crazy(r)
            crazy(62)
        self.assertTrue(all(memory[r] == 3**19 // 2 for r in slots))
        self.assertEqual(memory[62], 0)
        self.assertEqual(memory[58], 3**19 // 2)
        self.assertFalse(set(EXTRA_SLOTS) & (set(RESERVED) | set(SLOTS)))


def _module(blocks, cases=(ModuleCase(stdin=b"x", stdout=b""),)):
    return Module("m", "f", (Function("f", (), blocks[0].name, tuple(blocks)),), tuple(cases))


class SemanticsTests(unittest.TestCase):
    def test_guest_cases_match_reference(self):
        for module, width, bound in (
            (build_arith_module(), 7, 0),
            (build_arith_multi_module(), MULTI_WIDTH, MULTI_BOUND),
            (build_nested_module(), NESTED_WIDTH, 0),
        ):
            for case in module.cases:
                self.assertEqual(reference(module, case.stdin, width, bound), case.stdout)

    def test_unrolling_bound_halts_like_the_reference(self):
        counter = _module([
            BasicBlock("entry", (Add("n", 0, 0), Jump("loop"))),
            BasicBlock("loop", (ReadA("c"), BranchZero("c", "done", "more"))),
            BasicBlock("more", (Add("n", "n", 1), Jump("loop"))),
            BasicBlock("done", (WriteDecimal("n"), Halt())),
        ])
        self.assertEqual(reference(counter, b"\x01\x01\x00", 7, 2), b"2")
        self.assertEqual(reference(counter, b"\x01\x01\x01\x00", 7, 2), b"")
        graph = build_graph(counter, 7, 2)
        self.assertEqual(sum(n.op == "read" for n in graph.nodes), 3)

    def test_loops_need_a_bound(self):
        loop = _module([
            BasicBlock("entry", (ReadA("c"), BranchZero("c", "done", "entry"))),
            BasicBlock("done", (Halt(),)),
        ])
        self.assertEqual(sum(n.op == "read" for n in build_graph(loop, 7, 0).nodes), 0)
        self.assertEqual(reference(loop, b"\x01\x00", 7, 0), b"")

    def test_reads_must_have_static_indices(self):
        uneven = _module([
            BasicBlock("entry", (ReadA("c"), BranchZero("c", "two", "join"))),
            BasicBlock("two", (ReadA("d"), Jump("join"))),
            BasicBlock("join", (ReadA("e"), WriteDecimal("e"), Halt())),
        ])
        with self.assertRaisesRegex(AssemblyError, "different numbers of bytes"):
            build_graph(uneven)

    def test_value_sets_narrow_dynamic_loads(self):
        r = Rng(1, 19, {1, 7, 13, 19})
        self.assertEqual(r, (1, 19))
        self.assertEqual(r.vals, frozenset({1, 7, 13, 19}))
        memory = _module([
            BasicBlock("entry", (ReadA("c"), Store(0, "c"), Store(5, "c"), Add("p", 0, 0),
                                 BranchZero("c", "far", "near"))),
            BasicBlock("far", (Add("p", "p", 5), Jump("near"))),
            BasicBlock("near", (Load("v", "p"), WriteDecimal("v"), Halt())),
        ])
        graph = build_graph(memory)
        selects = [n for n in graph.nodes if n.op == "select" and len(n.args) == 4]
        self.assertTrue(selects)  # two candidate cells {0, 5}, not six
        self.assertEqual(reference(memory, b"\x07"), b"7")

    def test_declared_cases_are_checked(self):
        bad = replace(build_arith_module(), cases=(ModuleCase(stdin=b"(+ 1 1)", stdout=b"3"),))
        with self.assertRaisesRegex(AssemblyError, "contradicts"):
            lower_predicated(bad, PROFILE)


@unittest.skipUnless(ENGINE.is_file(), "build/bolge19 not built")
class NativeTests(unittest.TestCase):
    """H10 runs here; H11 and H12 (58M and 28M cells) run in tools/verify_predicated.py."""

    @classmethod
    def setUpClass(cls):
        cls.module = build_arith_module()
        cls.path = ROOT / "build/test_h10.mb"
        cls.path.write_bytes(lower_predicated(cls.module, PROFILE).image)

    def run_vm(self, stdin):
        done = subprocess.run(
            [str(ENGINE), str(self.path), "--loader", "canonical", "--max-steps", "100000000"],
            input=stdin, capture_output=True, timeout=60,
        )
        self.assertIn(b"HALT", done.stderr)
        return done.stdout

    def test_operators_signs_and_endings(self):
        for op, a, b, end in itertools.product("+-*", (0, 3, 7, 9), (0, 4, 9), ("", "\n", "\r\n")):
            stdin = f"({op} {a} {b}){end}".encode()
            self.assertEqual(self.run_vm(stdin), reference(self.module, stdin), stdin)

    def test_equal_operands_do_not_print_negative_zero(self):
        for a in range(10):
            self.assertEqual(self.run_vm(f"(- {a} {a})".encode()), b"0")

    def test_malformed_frames_print_nothing(self):
        for stdin in (b"", b"(/ 1 2)", b"(+ 1 2", b"(+ : 2)", b"(+ 1 2)\r", b"\xff" * 9):
            self.assertEqual(self.run_vm(stdin), b"", stdin)


if __name__ == "__main__":
    unittest.main()

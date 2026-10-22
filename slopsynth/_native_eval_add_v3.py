"""Native ternary-adder circuit for H9 v3, emitted from a lowered IR plan.

Unlike v2, no sum is wired at build time. The VM recovers the ASCII bytes of the
operands, adds and subtracts with a word-parallel ternary adder (tritwise sum
mod 3 and carry; the carry is shifted one trit per round), and prints decimal
output by detecting the tens digit from a carry into trit 5. Digit validity is
also arithmetic: a byte is a digit iff x + 195 carries into trit 5 and x + 185
does not. Only the frame punctuation is still compared byte by byte.

Every tritwise function is CRAZY plus unary maps; the formulas below were found
by exhaustive search over two-input ternary functions:

    sum   s_full(x, y) = (x + y) mod 3        two CRAZY gates
    carry g_full(x, y) = [x + y >= 3]         one CRAZY gate
    s_01 / g_01: the same for a carry trit in {0, 1}
    keep(v, m)  = v where m = 1, else 0       two CRAZY gates

Rounds: each round preserves s + c = x + y, and after round j the carry word is
zero below trit j + 1. A carry at trit >= W would make s + c >= 3^W, so W - 1
rounds are exact whenever x + y < 3^W. The lowering derives W from interval
analysis of the IR.

The circuit is acyclic and executes once, like v2. Layout, data ring, EOF
handling, grammar check and conditional output reuse the v2 `_Circuit`.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._native_eval_add import CHAR1, E, ONE, PTR, TWO, UNARY, Z, _Circuit
from .model import _crazy

SHIFT_LEFT = 17  # the VM rotates the low 18 trits right; 17 rotations = one trit left
WIDTH = 6  # arithmetic values live in the low six trits (< 729)
FRAME = b"(+ a b)"
DIGIT_POSITIONS = (3, 5)
INPUT_SLOTS = (42, 43, 44, 45, 47, 48, 49)  # v2 SLOTS for the seven frame bytes


def rounds_for(max_sum: int) -> int:
    """Carry rounds that make the adder exact for sums up to max_sum."""
    width = 1
    while 3**width <= max_sum:
        width += 1
    return max(width - 1, 0)


@dataclass(frozen=True, slots=True)
class Step:
    """One lowered operation. Operands are frame positions, names or constants."""

    kind: str  # "add", "sub_const" or "write_decimal"
    destination: str | None
    left: str | int | None = None
    right: str | int | None = None
    rounds: int = 0


class _AdderCircuit(_Circuit):
    def unary_ip(self, r, table):
        """Apply a unary tritwise map in place; may return a new register."""
        for kind, k in UNARY[table]:
            if kind == "ctrl":
                self.ctrl(k, r)
            else:
                dst = self.uniform(k)
                self.load(r)
                self.act("crazy", dst)
                self.drop(r)
                r = dst
        return r

    def un(self, src, table):
        return self.unary_ip(self.copy(src), table)

    def cz_consume(self, a, b):
        """crz(A=a, cell=b), i.e. T[b][a] per trit, stored in b; a and b are consumed."""
        self.load(a)
        self.act("crazy", b)
        self.drop(a)
        return b

    def shl(self, r):
        for _ in range(SHIFT_LEFT):
            self.act("rotate", r)
        return r

    def s_full(self, x, y):
        left = self.cz_consume(self.copy(x), self.un(y, (0, 2, 1)))
        left = self.unary_ip(left, (2, 1, 0))
        right = self.cz_consume(self.un(x, (0, 2, 1)), self.un(y, (2, 2, 0)))
        right = self.unary_ip(right, (0, 2, 1))
        return self.cz_consume(left, right)

    def g_full(self, x, y):
        g = self.cz_consume(self.un(x, (0, 2, 1)), self.un(y, (2, 1, 0)))
        return self.unary_ip(g, (1, 0, 0))

    def s_01(self, s, c):
        left = self.cz_consume(self.copy(s), self.un(c, (0, 2, 1)))
        right = self.cz_consume(self.copy(s), self.un(s, (0, 2, 0)))
        return self.unary_ip(self.cz_consume(left, right), (0, 2, 1))

    def g_01(self, s, c):
        return self.unary_ip(self.cz_consume(self.copy(s), self.copy(c)), (0, 0, 1))

    def keep(self, v, m):
        left = self.cz_consume(self.copy(v), self.un(v, (0, 2, 1)))
        right = self.cz_consume(self.un(v, (1, 1, 2)), self.un(m, (0, 2, 1)))
        right = self.unary_ip(right, (0, 2, 1))
        return self.unary_ip(self.cz_consume(left, right), (0, 2, 1))

    def add(self, x, y, rounds):
        """Return a new register with x + y; x and y are preserved."""
        s = self.s_full(x, y)
        c = self.shl(self.g_full(x, y))
        for _ in range(rounds):
            s2 = self.s_01(s, c)
            c2 = self.shl(self.g_01(s, c))
            self.drop(s)
            self.drop(c)
            s, c = s2, c2
        self.drop(c)
        return s

    def sub_const(self, x, k, rounds):
        """x - k for x >= k: add 3^WIDTH - k, then keep the low WIDTH trits."""
        complement = self.const(3**WIDTH - k)
        total = self.add(x, complement, rounds)
        self.drop(complement)
        low = self.const((3**WIDTH - 1) // 2)  # 1 in each of the low WIDTH trits
        result = self.keep(total, low)
        self.drop(total)
        self.drop(low)
        return result

    def const(self, value):
        """Build a constant from the scalar 1/2 registers; digits never carry."""
        r = self.uniform(0)
        for k in range(18):
            digit = (value // 3**k) % 3
            if digit:
                t = self.copy((ONE, TWO)[digit - 1])
                for _ in range((18 - k) % 18):
                    self.act("rotate", t)
                n = self.s_full(r, t)
                self.drop(r)
                self.drop(t)
                r = n
        return r

    def flag(self, src, k):
        """Trit k of src as a 0/1 LSB flag (a stray 2 from EOF garbage becomes 0)."""
        return self.unary_ip(self.trit(src, k), (0, 1, 0))

    def byte(self, slot):
        """Undo the input store: slots hold crz(byte, 1...1), which swaps 0 and 1."""
        return self.unary_ip(self.copy(slot), (1, 0, 2))

    def is_digit(self, x):
        flags = []
        for k in (195, 185):  # x >= 48 and x >= 58
            constant = self.const(k)
            total = self.add(x, constant, rounds_for(255 + k))
            self.drop(constant)
            flags.append(self.flag(total, 5))
            self.drop(total)
        lo, hi = flags
        not_hi = self.NOT(hi)
        self.drop(hi)
        self.mask(not_hi)
        ok = self.AND(lo, not_hi)
        self.drop(lo)
        self.drop(not_hi)
        return ok

    def frame_grammar(self):
        grammar = self.copy(ONE)
        for r, ch in [(42, 40), (43, 43), (44, 32), (47, 32), (49, 41)]:
            f = self.eqbyte(r, _crazy(ch, E // 2, 19))
            t = self.AND(grammar, f)
            self.drop(grammar)
            self.drop(f)
            grammar = t
            self.drop(r)
        suffix = self.copy(Z)
        for x, y in [(E - 1, E - 1), (10, E - 1), (13, 10)]:
            f = self.eqbyte(51, _crazy(x, E // 2, 19))
            g = self.eqbyte(55, _crazy(y, E // 2, 19))
            t = self.AND(f, g)
            self.drop(f)
            self.drop(g)
            v = self.OR(suffix, t)
            self.drop(suffix)
            self.drop(t)
            suffix = v
        t = self.AND(grammar, suffix)
        self.drop(grammar)
        self.drop(suffix)
        self.drop(51)
        self.drop(55)
        return t


def _compile(reads, steps, bases=(0, 0)):
    """reads: frame position per IR read name; steps: lowered arithmetic and output."""
    c = _AdderCircuit()
    c.bootstrap()
    valid = c.frame_grammar()
    digits = {}
    for position in DIGIT_POSITIONS:
        slot = INPUT_SLOTS[position]
        digits[position] = c.byte(slot)
        c.drop(slot)
        ok = c.is_digit(digits[position])
        t = c.AND(valid, ok)
        c.drop(valid)
        c.drop(ok)
        valid = t

    values = {}

    def operand(ref):
        """Register for an operand plus whether the caller owns (must drop) it."""
        if isinstance(ref, int):
            return c.const(ref), True
        if ref in values:
            return values[ref], False
        position = reads[ref]
        if position in digits:
            return digits[position], False
        # Punctuation is fixed by the validated frame.
        return c.const(FRAME[position]), True

    tens = units = None
    for step in steps:
        if step.kind in ("add", "sub_const"):
            left, own_left = operand(step.left)
            if step.kind == "add":
                right, own_right = operand(step.right)
                result = c.add(left, right, step.rounds)
                if own_right:
                    c.drop(right)
            else:
                result = c.sub_const(left, step.right, step.rounds)
            if own_left:
                c.drop(left)
            values[step.destination] = result
        elif step.kind == "write_decimal":
            value, own = operand(step.left)
            # tens iff value + 233 >= 243, i.e. value >= 10 (value <= 19)
            k233 = c.const(233)
            total = c.add(value, k233, rounds_for(19 + 233))
            c.drop(k233)
            tens = c.flag(total, 5)
            c.drop(total)
            # units byte = value + 38 + 10 * (1 - tens), always 48..57
            nt = c.NOT(tens)
            c.mask(nt)
            nt2 = c.copy(nt)
            for _ in range(16):
                c.act("rotate", nt2)
            ten = c.s_full(nt, nt2)
            c.drop(nt)
            c.drop(nt2)
            k38 = c.const(38)
            offset = c.add(k38, ten, rounds_for(48))
            c.drop(k38)
            c.drop(ten)
            units = c.add(value, offset, rounds_for(19 + 48))
            c.drop(offset)
            if own:
                c.drop(value)
        else:
            raise ValueError(f"unknown lowered step {step.kind}")
    for register in list(values.values()) + list(digits.values()):
        c.drop(register)

    base = c.word(bases[0])
    addr = c.merge(base, valid)
    c.drop(base)
    c.drop(valid)
    c.copy(addr, PTR)
    c.drop(addr)
    c.jump(PTR)
    b0 = c.pad()
    c.code.append("halt")
    base = c.word(bases[1])
    nt = c.NOT(tens)
    c.mask(nt)
    c.drop(tens)
    addr = c.merge(base, nt)
    c.drop(base)
    c.drop(nt)
    c.copy(addr, PTR)
    c.drop(addr)
    c.load(CHAR1)
    c.jump(PTR)
    b1 = c.pad()
    c.code.append("output")
    c.code.append("move")
    c.d = 67
    c.load(units)
    c.act("output")
    c.code.append("halt")
    return c, (b0, b1)


def build_native_program_v3(reads, steps):
    """Return a deterministic canonical image and conditional landing bases."""
    _, bases = _compile(reads, steps)
    built, second_bases = _compile(reads, steps, bases)
    if second_bases != bases:
        raise ValueError("H9 v3 layout changed during relocation")
    return built.image(), bases, tuple(built.input_sites)

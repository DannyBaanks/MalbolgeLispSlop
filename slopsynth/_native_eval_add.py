"""Native, acyclic digit-adder circuit for H9 v2.

No input/output cases select the implementation. The emitted program saves nine
input bytes (fixed frame plus optional line ending), decodes each digit into ten
one-hot flags, ANDs the operands' flags, and combines the sum rails into decimal
output. All gates execute as Malbolge CRAZY/ROT/INPUT/MOVD/JMP/OUTPUT instructions.

A 55-cell data ring at 40..94 keeps D addressable without a host trampoline.
Every ordinary action occupies 60 cells, with NOP/MOVD padding. This makes label
addresses independent of the ternary digits used to synthesize those addresses.
Two layout passes therefore produce identical positions. Code is executed once;
self-encryption only affects consumed code and jump landing pads.

EOF is used as the VM's all-2-trit control word. The caller must close stdin after
one frame. This is a finite digit circuit, not a general Lisp evaluator or ALU.
"""

from functools import lru_cache
from pathlib import Path
from .encode import encode_dispatch_sequence
from .profile import load_profile
from .model import _crazy
from collections import deque

T = ((1, 0, 0), (1, 0, 2), (2, 2, 1))
E = 3**19
# Uniform constants, scalar 1/2, LSB mask, ASCII 1, and branch register.
O, Z, ONE, TWO, MASK, CHAR1 = 58, 62, 41, 53, 54, 50
PTR = 66
SLOTS = [42, 43, 44, 45, 47, 48, 49, 51, 55]
RESERVED = {O, Z, ONE, TWO, MASK, CHAR1, PTR, 67, 68}
P = load_profile(Path(__file__).resolve().parents[1] / "profiles/fixed19.json")
UNARY = {(0, 1, 2): ()}
q = deque(UNARY)
while q:
    a = q.popleft()
    for kind in ("ctrl", "cell"):
        for k in range(3):
            v = tuple(T[d][k] if kind == "ctrl" else T[k][d] for d in a)
            if v not in UNARY:
                UNARY[v] = UNARY[a] + ((kind, k),)
                q.append(v)


class _Circuit:
    def __init__(self):
        self.code = ["nop"] * 99
        self.code[0] = "jump"
        self.d = 1
        self.initial = {58: 40, 62: 36, 40: 41, 41: 92, 94: 39, 50: 49, 67: 66, 68: 66}
        self.free = set(range(40, 94)) - RESERVED - set(SLOTS)
        valid = set(P.dispatch.values())
        for r in SLOTS:
            self.initial[r] = next(
                b
                for b in range(33, 127)
                if (b + r) % 94 in valid and all((b // 3**k) % 3 != 2 for k in range(6))
            )

    def tick(self):
        if self.d == 94:
            self.code.append("move")
            self.d = 40
        else:
            self.code.append("nop")
            self.d += 1

    def act(self, op, r=None):
        start = len(self.code)
        if r is not None:
            while self.d != r:
                self.tick()
        self.code.append(op)
        self.d += 1
        while len(self.code) - start < 60:
            self.tick()
        assert len(self.code) - start == 60

    def alloc(self):
        if not self.free:
            raise RuntimeError("no registers")
        r = min(self.free)
        self.free.remove(r)
        return r

    def drop(self, r):
        assert r not in RESERVED and r not in self.free
        self.free.add(r)

    def load(self, r):
        # EOF is a tritwise involution on stored data: applying twice restores M[r].
        self.act("input")
        self.act("crazy", r)
        self.act("input")
        self.act("crazy", r)

    def ctrl(self, k, r):
        if k == 2:
            self.act("input")
        else:
            self.load(Z if k == 0 else O)
        self.act("crazy", r)

    def reset(self, r, k=1):
        # Controls (1,2,0) map every possible cell trit to 1.
        for ctrl in (1, 2, 0):
            self.ctrl(ctrl, r)
        if k == 0:
            self.ctrl(1, r)
        elif k == 2:
            self.ctrl(2, r)

    def copy(self, src, dst=None):
        # With data=all-1, CRAZY swaps 0/1 and leaves 2; two stores copy a word.
        dst = self.alloc() if dst is None else dst
        tmp = self.alloc()
        self.reset(tmp)
        self.reset(dst)
        self.load(src)
        self.act("crazy", tmp)
        self.act("crazy", dst)
        self.drop(tmp)
        return dst

    def crz(self, a, b):
        dst = self.copy(b)
        self.load(a)
        self.act("crazy", dst)
        return dst

    def uniform(self, k):
        r = self.alloc()
        self.reset(r, k)
        return r

    def unary(self, src, table):
        cur = self.copy(src)
        for kind, k in UNARY[table]:
            if kind == "ctrl":
                self.ctrl(k, cur)
            else:
                dst = self.uniform(k)
                self.load(cur)
                self.act("crazy", dst)
                self.drop(cur)
                cur = dst
        return cur

    def mask(self, r):
        # Upper trits follow (1,2,1,1) -> 0; LSB follows (2,2,2,2) -> identity.
        self.load(MASK)
        self.act("crazy", r)
        self.ctrl(2, r)
        for _ in range(2):
            self.load(MASK)
            self.act("crazy", r)

    def trit(self, src, k):
        r = self.copy(src)
        for _ in range(k):
            self.act("rotate", r)
        self.mask(r)
        return r

    def eqbyte(self, r, value):
        flag = None
        for k in range(6):
            trit = self.trit(r, k)
            v = (value // 3**k) % 3
            eq = self.unary(trit, tuple(int(j == v) for j in range(3)))
            self.drop(trit)
            self.mask(eq)
            if flag is None:
                flag = eq
            else:
                dst = self.AND(flag, eq)
                self.drop(flag)
                self.drop(eq)
                flag = dst
        return flag

    def NOT(self, a):
        return self.unary(a, (1, 0, 2))

    def AND(self, a, b):
        t = self.copy(a)
        self.ctrl(2, t)
        mapped = self.uniform(1)
        self.load(t)
        self.act("crazy", mapped)
        self.drop(t)
        dst = self.copy(b)
        self.load(mapped)
        self.act("crazy", dst)
        self.drop(mapped)
        self.ctrl(2, dst)
        return dst

    def OR(self, a, b):
        t = self.copy(b)
        self.ctrl(2, t)
        q = self.crz(a, t)
        self.drop(t)
        r = self.unary(q, (1, 0, 1))
        self.drop(q)
        return r

    def merge(self, x, y):
        # c(c(c(x,2),c(y,y)),c(c(y,x),c(2,x)))
        two = self.uniform(2)
        a = self.crz(x, two)
        self.drop(two)
        b = self.crz(y, y)
        l = self.crz(a, b)
        self.drop(a)
        self.drop(b)
        a = self.crz(y, x)
        two = self.uniform(2)
        b = self.crz(two, x)
        self.drop(two)
        r = self.crz(a, b)
        self.drop(a)
        self.drop(b)
        v = self.crz(l, r)
        self.drop(l)
        self.drop(r)
        return v

    def word(self, value, dst=None):
        # Build all 18 low trits, including zero digits, for invariant code layout.
        if not 0 <= value < 3**18:
            raise ValueError("native label exceeds the low-18-trit address domain")
        r = self.uniform(0)
        for k in range(18):
            digit = (value // 3**k) % 3
            t = self.copy((Z, ONE, TWO)[digit])
            for _ in range((18 - k) % 18):
                self.act("rotate", t)
            n = self.merge(r, t)
            self.drop(r)
            self.drop(t)
            r = n
        if dst is not None:
            self.copy(r, dst)
            self.drop(r)
            return dst
        return r

    def bootstrap(self):
        self.act("crazy", 58)
        self.act("crazy", 62)
        for r in SLOTS:
            self.act("crazy", r)
            self.act("crazy", 62)
        self.act("crazy", 40)
        self.act("crazy", 41)
        self.input_sites = []
        for r in SLOTS:
            self.input_sites.append(len(self.code))
            self.act("input")
            self.act("crazy", r)
        self.copy(ONE, TWO)
        self.ctrl(2, TWO)
        self.reset(MASK)
        self.load(TWO)
        self.act("crazy", MASK)

    def jump(self, r):
        # Do not pad after a control transfer; both successors have explicit layouts.
        while self.d != r:
            self.tick()
        self.code.append("jump")
        self.d += 1

    def pad(self):
        while len(self.code) % 3:
            self.code.append("nop")
        base = len(self.code)
        self.code.append("nop")
        return base

    def image(self):
        image = bytearray(encode_dispatch_sequence(self.code, P))
        for r, v in self.initial.items():
            image[r] = v
        return bytes(image)


def _compile(bases=(0, 0)):
    c = _Circuit()
    c.bootstrap()
    grammar = c.copy(ONE)
    for r, ch in [(42, 40), (43, 43), (44, 32), (47, 32), (49, 41)]:
        f = c.eqbyte(r, _crazy(ch, E // 2, 19))
        t = c.AND(grammar, f)
        c.drop(grammar)
        c.drop(f)
        grammar = t
        c.drop(r)
    suffix = c.copy(Z)
    for x, y in [(E - 1, E - 1), (10, E - 1), (13, 10)]:
        f = c.eqbyte(51, _crazy(x, E // 2, 19))
        g = c.eqbyte(55, _crazy(y, E // 2, 19))
        t = c.AND(f, g)
        c.drop(f)
        c.drop(g)
        v = c.OR(suffix, t)
        c.drop(suffix)
        c.drop(t)
        suffix = v
    t = c.AND(grammar, suffix)
    c.drop(grammar)
    c.drop(suffix)
    grammar = t
    c.drop(51)
    c.drop(55)
    aa = [c.eqbyte(45, _crazy(48 + i, (E // 2), 19)) for i in range(10)]
    c.drop(45)
    bb = [c.eqbyte(48, _crazy(48 + i, (E // 2), 19)) for i in range(10)]
    c.drop(48)
    sums = [None] * 19
    for i, a in enumerate(aa):
        for j, b in enumerate(bb):
            flag = c.AND(a, b)
            n = i + j
            if sums[n] is None:
                sums[n] = flag
            else:
                t = c.OR(sums[n], flag)
                c.drop(sums[n])
                c.drop(flag)
                sums[n] = t
        c.drop(a)
    for r in bb:
        c.drop(r)
    units = c.uniform(0)
    for k in range(4):
        rails = []
        for digit in (1, 2):
            r = c.copy(Z)
            for n, flag in enumerate(sums):
                if ((48 + n % 10) // 3**k) % 3 == digit:
                    t = c.OR(r, flag)
                    c.drop(r)
                    r = t
            rails.append(r)
        # choose 1 or 2 from disjoint one-hot rails
        one = c.NOT(rails[0])
        c.drop(rails[0])
        two = c.copy(rails[1])
        c.ctrl(2, two)
        c.drop(rails[1])
        trit = c.crz(one, two)
        c.drop(one)
        c.drop(two)
        for _ in range((18 - k) % 18):
            c.act("rotate", trit)
        t = c.merge(units, trit)
        c.drop(units)
        c.drop(trit)
        units = t
    tens = c.copy(Z)
    valid = c.copy(Z)
    for n, flag in enumerate(sums):
        t = c.OR(valid, flag)
        c.drop(valid)
        valid = t
        if n >= 10:
            t = c.OR(tens, flag)
            c.drop(tens)
            tens = t
        c.drop(flag)
    t = c.AND(valid, grammar)
    c.drop(valid)
    c.drop(grammar)
    valid = t
    base = c.word(bases[0])
    addr = c.merge(base, valid)
    c.drop(base)
    c.drop(valid)
    c.copy(addr, PTR)
    c.drop(addr)
    c.jump(PTR)
    b0 = c.pad()
    c.code.append("halt")
    # Valid jumps past HALT with D=67. For tens output, paths then join through
    # MOVD: both M[67] and M[68] contain 66, restoring D=67 after 0/1 outputs.
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


@lru_cache(maxsize=1)
def build_native_digit_adder() -> tuple[bytes, tuple[int, int], tuple[int, ...]]:
    """Return a deterministic canonical image and conditional landing bases."""
    first, bases = _compile()
    del first
    built, second_bases = _compile(bases)
    if second_bases != bases:
        raise ValueError("H9 layout changed during relocation")
    return built.image(), bases, tuple(built.input_sites)

"""H10: predicated compiler from IR control-flow graphs to native fixed19 circuits.

Branches are if-converted: every block runs, each block carries a 0/1 predicate,
values meeting at a join are selected by edge predicates, and only outputs are
conditional (a computed jump over an OUTPUT cell). Arithmetic is modulo 3^WIDTH
on canonical words (all trits above WIDTH are zero); ReadA yields a byte or the
EOF sentinel reduced modulo 3^WIDTH.

Supported operations: ReadA, Add, Sub, Mul, Lt, WriteA (low byte), WriteDecimal,
BranchZero, Jump, Halt. The CFG must be acyclic (loops are rejected here; see
`unroll` for bounded unrolling) and every path into a block must have read the
same number of input bytes, so each read has a static input index.

Interval analysis is path sensitive for the patterns `Lt(x, k)` and
`Sub(x, k) == 0` used as branch conditions. It decides carry rounds and how
many decimal digits WriteDecimal needs. Code that runs on an inactive path may
compute garbage; it never reaches an output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .assemble import AssemblyError, format_image
from .canonical import CanonicalWalk, walk_canonical
from .ir import Add, BranchZero, Halt, Jump, Lt, Module, Mul, ReadA, Sub, WriteA, WriteDecimal
from .profile import Profile, load_profile
from ._native_eval_add import ONE, PTR, SLOTS, TWO, Z
from ._native_eval_add_v3 import _AdderCircuit, rounds_for

WIDTH = 7
MOD = 3**WIDTH
FULL = (0, MOD - 1)
ID = (0, 1, 2)
WORD_TRITS = 16  # landing addresses must stay below 3^16 cells
LOWERING = "fixed19-predicated-v1"


# ---------------------------------------------------------------- gates ----


class Gates(_AdderCircuit):
    """Tritwise gates; formulas found by exhaustive CRAZY/unary search."""

    def bin1(self, x, y, ux, uy, uo):
        """uo(crz(A=ux(x), cell=uy(y))) in a new register; x and y are preserved."""
        return self.unary_ip(self.cz_consume(self.un(x, ux), self.un(y, uy)), uo)

    def oradd(self, x, y):
        """x + y per trit where one of the two trits is 0."""
        return self.bin1(x, y, (2, 1, 0), (1, 0, 2), (1, 2, 0))

    def and01(self, x, y):
        return self.bin1(x, y, (0, 2, 1), ID, (0, 0, 1))

    def or01(self, x, y):
        return self.bin1(x, y, ID, (0, 2, 1), (1, 0, 1))

    def not01(self, f):
        r = self.un(f, (1, 0, 0))
        self.mask(r)
        return r

    def eqt(self, x, y):
        """1 where the trits of x and y are equal, else 0."""
        left = self.bin1(x, y, ID, (0, 2, 1), (0, 2, 1))
        right = self.bin1(x, y, (0, 2, 1), ID, ID)
        return self.unary_ip(self.cz_consume(left, right), (0, 0, 1))

    def comp(self, a, m):
        """2 - a where m = 1, else 0 (ternary complement under a mask)."""
        left = self.bin1(m, a, ID, ID, ID)
        right = self.bin1(a, m, (0, 2, 1), ID, ID)
        return self.unary_ip(self.cz_consume(left, right), (0, 2, 1))

    def shift_left(self, r, s):
        for _ in range((18 - s) % 18):
            self.act("rotate", r)
        return r

    def shift_right(self, r, s):
        for _ in range(s):
            self.act("rotate", r)
        return r

    def const(self, value):
        r = self.uniform(0)
        for k in range(18):
            digit = (value // 3**k) % 3
            if digit:
                t = self.shift_left(self.copy((ONE, TWO)[digit - 1]), k)
                n = self.oradd(r, t)
                self.drop(r)
                self.drop(t)
                r = n
        return r

    def word(self, value, dst=None):
        """Address constant with a code length independent of its value."""
        if not 0 <= value < 3**WORD_TRITS:
            raise AssemblyError("landing address exceeds the supported code size")
        r = self.uniform(0)
        for k in range(WORD_TRITS):
            digit = (value // 3**k) % 3
            t = self.shift_left(self.copy((Z, ONE, TWO)[digit]), k)
            n = self.oradd(r, t)
            self.drop(r)
            self.drop(t)
            r = n
        if dst is not None:
            self.copy(r, dst)
            self.drop(r)
            return dst
        return r

    def reduce_and(self, r, width):
        """AND of trits 0..width-1 into the LSB (consumes r); returns a 0/1 flag."""
        s = 1
        while s < width:
            t = self.shift_right(self.copy(r), s)
            n = self.and01(r, t)
            self.drop(r)
            self.drop(t)
            r = n
            s *= 2
        self.mask(r)
        return r

    def broadcast(self, f, width=WIDTH):
        """Copy a 0/1 LSB flag into trits 0..width-1 (and possibly a few above)."""
        b = self.copy(f)
        s = 1
        while s < width:
            t = self.shift_left(self.copy(b), s)
            n = self.or01(b, t)
            self.drop(b)
            self.drop(t)
            b = n
            s *= 2
        return b

    def add_cin(self, x, y, rounds, carry_in=False):
        s = self.s_full(x, y)
        c = self.shl(self.g_full(x, y))
        if carry_in:
            one = self.copy(ONE)
            n = self.oradd(c, one)
            self.drop(c)
            self.drop(one)
            c = n
        for _ in range(rounds):
            s2 = self.s_01(s, c)
            c2 = self.shl(self.g_01(s, c))
            self.drop(s)
            self.drop(c)
            s, c = s2, c2
        self.drop(c)
        return s


# ------------------------------------------------------------------ SSA ----


@dataclass
class Node:
    op: str
    args: tuple = ()
    lo: int = 0
    hi: int = 0
    uses: int = 0
    meta: tuple = ()


@dataclass
class Graph:
    nodes: list[Node] = field(default_factory=list)
    consts: dict[int, int] = field(default_factory=dict)
    true: int | None = None

    def add(self, op, args=(), lo=0, hi=0, meta=()):
        self.nodes.append(Node(op, tuple(args), lo, hi, 0, meta))
        return len(self.nodes) - 1

    def const(self, value):
        value %= MOD
        if value not in self.consts:
            self.consts[value] = self.add("const", (value,), value, value)
        return self.consts[value]

    def flag_true(self):
        if self.true is None:
            self.true = self.add("true", (), 1, 1)
        return self.true

    def and_(self, f, g):
        if f == self.true:
            return g
        if g == self.true:
            return f
        return self.add("and", (f, g), 0, 1)

    def or_(self, f, g):
        if self.true in (f, g):
            return self.true
        return self.add("or", (f, g), 0, 1)

    def not_(self, f):
        return self.add("not", (f,), 0, 1)


def _wrap(lo, hi):
    return (lo, hi) if 0 <= lo and hi < MOD else FULL


def _successors(block):
    last = block.operations[-1]
    if isinstance(last, Jump):
        return (last.target,)
    if isinstance(last, BranchZero):
        return (last.zero_target, last.nonzero_target)
    return ()


def _topological(function):
    blocks = {b.name: b for b in function.blocks}
    for block in function.blocks:
        last = block.operations[-1]
        if not isinstance(last, (Jump, BranchZero, Halt)):
            raise AssemblyError(f"block {block.name!r} must end with jump, branch or halt")
        for op in block.operations[:-1]:
            if isinstance(op, (Jump, BranchZero, Halt)):
                raise AssemblyError(f"block {block.name!r} has a terminator before its end")
    order, state = [], {}

    def visit(name):
        if state.get(name) == 1:
            raise AssemblyError(f"loop through block {name!r}: use bounded unrolling")
        if state.get(name) == 2:
            return
        state[name] = 1
        for succ in _successors(blocks[name]):
            visit(succ)
        state[name] = 2
        order.append(name)

    visit(function.entry_block)
    return [blocks[name] for name in reversed(order)]


def build_graph(module: Module) -> Graph:
    """If-convert the module's single function into a predicated SSA graph."""
    if len(module.functions) != 1 or module.functions[0].parameters:
        raise AssemblyError("H10 compiles one parameterless function")
    function = module.functions[0]
    g = Graph()
    incoming = {function.entry_block: [(g.flag_true(), {}, 0)]}

    def ref(env, r):
        if isinstance(r, bool) or not isinstance(r, (str, int)):
            raise AssemblyError(f"operand {r!r} is not a name or integer")
        if isinstance(r, int):
            c = g.const(r)
            return c, (r % MOD, r % MOD)
        if r not in env:
            raise AssemblyError(f"{r!r} is not defined on every path to its use")
        return env[r]

    for block in _topological(function):
        edges = incoming.pop(block.name, [])
        if not edges:
            continue
        reads = {count for _, _, count in edges}
        if len(reads) != 1:
            raise AssemblyError(f"paths into {block.name!r} read different numbers of bytes")
        count = reads.pop()
        pred = edges[0][0]
        for flag, _, _ in edges[1:]:
            pred = g.or_(pred, flag)
        env = {}
        names = set(edges[0][1]).intersection(*(e for _, e, _ in edges[1:]))
        for name in names:
            values = [e[name] for _, e, _ in edges]
            if all(v[0] == values[0][0] for v in values):
                env[name] = (values[0][0], (min(v[1][0] for v in values), max(v[1][1] for v in values)))
            else:
                lo = min(v[1][0] for v in values)
                hi = max(v[1][1] for v in values)
                pairs = tuple(x for (flag, _, _), v in zip(edges, values) for x in (flag, v[0]))
                env[name] = (g.add("select", pairs, lo, hi), (lo, hi))
        for op in block.operations:
            if isinstance(op, ReadA):
                env[op.destination] = (g.add("read", (count,), 0, MOD - 1), FULL)
                count += 1
            elif isinstance(op, (Add, Sub, Mul, Lt)):
                (a, (alo, ahi)), (b, (blo, bhi)) = ref(env, op.left), ref(env, op.right)
                meta = (alo, ahi, blo, bhi)
                if isinstance(op, Add):
                    lo, hi = _wrap(alo + blo, ahi + bhi)
                    node = g.add("add", (a, b), lo, hi, meta)
                elif isinstance(op, Sub):
                    lo, hi = _wrap(alo - bhi, ahi - blo)
                    node = g.add("sub", (a, b), lo, hi, meta)
                elif isinstance(op, Mul):
                    lo, hi = _wrap(alo * blo, ahi * bhi)
                    node = g.add("mul", (a, b), lo, hi, meta)
                else:
                    lo, hi = 0, 1
                    node = g.add("lt", (a, b), lo, hi, meta)
                env[op.destination] = (node, (lo, hi))
            elif isinstance(op, WriteA):
                v, _ = ref(env, op.value)
                g.add("out", (pred, v))
            elif isinstance(op, WriteDecimal):
                v, (lo, hi) = ref(env, op.value)
                g.add("outdec", (pred, v), lo, hi)
            elif isinstance(op, BranchZero):
                v, _ = ref(env, op.value)
                zero = g.add("eqz", (v,), 0, 1)
                envs = _refine(g, env, op.value, v)
                for target, flag, refined in (
                    (op.zero_target, g.and_(pred, zero), envs[0]),
                    (op.nonzero_target, g.and_(pred, g.not_(zero)), envs[1]),
                ):
                    incoming.setdefault(target, []).append((flag, refined, count))
            elif isinstance(op, Jump):
                incoming.setdefault(op.target, []).append((pred, dict(env), count))
            elif isinstance(op, Halt):
                pass
            else:
                raise AssemblyError(f"H10 cannot compile {type(op).__name__}")
    _fuse_and_prune(g)
    return g


def _refine(g, env, name, v):
    """Environments for the zero and nonzero edges of BranchZero(name)."""
    zero, nonzero = dict(env), dict(env)
    node = g.nodes[v]
    if node.op == "lt":
        a, b = node.args
        if g.nodes[b].op == "const":
            k = g.nodes[b].args[0]
            for var, (val, (lo, hi)) in env.items():
                if val == a:
                    nonzero[var] = (val, (lo, min(hi, k - 1)))
                    zero[var] = (val, (max(lo, k), hi))
    if node.op == "sub":
        a, b = node.args
        if g.nodes[b].op == "const":
            k = g.nodes[b].args[0]
            for var, (val, _) in env.items():
                if val == a:
                    zero[var] = (val, (k, k))
                if val == v:
                    zero[var] = (val, (0, 0))
    if isinstance(name, str) and name in env and node.op != "const":
        zero[name] = (v, (0, 0))
    return zero, nonzero


def _fuse_and_prune(g):
    """eqz(sub(x, k)) -> eqc(x, k) when the sub has no other use; then drop dead nodes."""
    def count_uses():
        for n in g.nodes:
            n.uses = 0
        for n in g.nodes:
            if n.op in ("const", "read"):
                continue
            for a in n.args:
                g.nodes[a].uses += 1

    count_uses()
    for n in g.nodes:
        if n.op == "eqz":
            s = g.nodes[n.args[0]]
            if s.op == "sub" and s.uses == 1 and g.nodes[s.args[1]].op == "const":
                n.op, n.args = "eqc", (s.args[0], s.args[1])
                s.op, s.args = "dead", ()
    live = [False] * len(g.nodes)
    for i in reversed(range(len(g.nodes))):
        n = g.nodes[i]
        if n.op in ("out", "outdec"):
            live[i] = True
        if live[i] and n.op not in ("const", "read"):
            for a in n.args:
                live[a] = True
    for i, n in enumerate(g.nodes):
        if not live[i]:
            n.op, n.args = "dead", ()
    count_uses()


# ------------------------------------------------------------- emission ----


class _Emitter:
    def __init__(self, g: Graph, bases):
        self.g = g
        self.c = Gates()
        self.bases = list(bases)
        self.landings = []
        self.reg = {}
        self.left = [n.uses for n in g.nodes]
        self.shared = {}

    # -- shared constants that live for the whole program
    def shared_const(self, value):
        if value not in self.shared:
            self.shared[value] = self.c.const(value)
        return self.shared[value]

    def mask_w(self):
        return self.shared_const((MOD - 1) // 2)

    def canonical(self, r):
        k = self.c.keep(r, self.mask_w())
        self.c.drop(r)
        return k

    def use(self, i):
        r = self.reg[i]
        return r

    def release(self, i):
        self.left[i] -= 1
        if self.left[i] == 0 and i in self.reg:
            self.c.drop(self.reg.pop(i))

    # -- bytes
    def read(self, index):
        c = self.c
        if index < len(SLOTS):
            raw = SLOTS[index]
            c.free.discard(raw)
        else:
            while self.physical <= index:
                raw = c.uniform(1)
                c.act("input")
                c.act("crazy", raw)
                self.pending[self.physical] = raw
                self.physical += 1
            raw = self.pending.pop(index)
        value = c.unary_ip(c.copy(raw), (1, 0, 2))  # the store swapped 0 and 1
        c.drop(raw)
        return self.canonical(value)

    # -- arithmetic
    def add(self, a, b, hi):
        if hi < MOD:
            return self.c.add_cin(a, b, rounds_for(hi))
        return self.canonical(self.c.add_cin(a, b, WIDTH))

    def sub(self, a, b):
        comp = self.c.comp(b, self.mask_w())
        total = self.c.add_cin(a, comp, WIDTH, carry_in=True)
        self.c.drop(comp)
        return total  # caller masks or reads the borrow trit

    def mul(self, x, y, hi_x, hi_y):
        c = self.c
        trits = max(1, rounds_for(hi_y) + 1)
        x2 = self.add(x, x, 2 * hi_x)
        acc = None
        for k in range(trits):
            t = c.trit(y, k)
            terms = []
            for value, table in ((x, (0, 1, 0)), (x2, (0, 0, 1))):
                f = c.un(t, table)
                b = c.broadcast(f)
                c.drop(f)
                terms.append(c.keep(value, b))
                c.drop(b)
            c.drop(t)
            term = c.oradd(*terms)
            for r in terms:
                c.drop(r)
            term = self.canonical(c.shift_left(term, k))
            if acc is None:
                acc = term
            else:
                n = self.add(acc, term, MOD)
                c.drop(acc)
                c.drop(term)
                acc = n
        c.drop(x2)
        return acc

    def eqc(self, x, y_reg):
        e = self.c.eqt(x, y_reg)
        return self.c.reduce_and(e, WIDTH)

    def select(self, pairs):
        c = self.c
        acc = None
        for f, v in pairs:
            b = c.broadcast(f)
            k = c.keep(v, b)
            c.drop(b)
            if acc is None:
                acc = k
            else:
                n = c.oradd(acc, k)
                c.drop(acc)
                c.drop(k)
                acc = n
        return acc

    def ge_const(self, x, hi_x, k):
        """(flag x >= k, candidate x - k masked) for 0 <= x <= hi_x."""
        t = rounds_for(max(hi_x, k)) + 1  # 3^t > max(hi_x, k)
        threshold = self.c.const(3**t - k)
        s = self.c.add_cin(x, threshold, rounds_for(hi_x + 3**t - k))
        self.c.drop(threshold)
        flag = self.c.flag(s, t)
        cand = self.c.keep(s, self.shared_const((3**t - 1) // 2))
        self.c.drop(s)
        return flag, cand

    # -- output
    def out(self, f, value):
        c = self.c
        if f is None:
            c.load(value)
            c.act("output")
            return
        skip = c.not01(f)
        base = c.word(self.bases[len(self.landings)] if len(self.bases) > len(self.landings) else 0)
        addr = c.oradd(base, skip)
        c.drop(base)
        c.drop(skip)
        c.copy(addr, PTR)
        c.drop(addr)
        c.load(value)
        c.jump(PTR)
        self.landings.append(c.pad())
        c.code.append("output")
        c.code.append("move")  # both paths leave D = 67 through M[67] = M[68] = 66
        c.d = 67

    def outdec(self, f, v, hi):
        c = self.c
        digits = len(str(hi))
        rem, rem_hi = c.copy(v), hi
        seen = None
        for j in range(digits - 1, 0, -1):
            p = 10**j
            top = min(9, rem_hi // p)
            if top == 0:
                continue
            flags, cands = [], []
            for m in range(1, top + 1):
                flag, cand = self.ge_const(rem, rem_hi, m * p)
                flags.append(flag)
                cands.append(cand)
            # digit = number of thresholds passed; next remainder = matching candidate
            digit = c.copy(flags[0])
            for m in range(1, top):
                n = c.add_cin(digit, flags[m], rounds_for(m + 1))
                c.drop(digit)
                digit = n
            pairs = [(c.not01(flags[0]), rem)]
            for m in range(top):
                if m + 1 == top:
                    exact = flags[m]
                else:
                    above = c.not01(flags[m + 1])
                    exact = c.and01(flags[m], above)
                    c.drop(above)
                pairs.append((exact, cands[m]))
            new_rem = self.select(pairs)
            for exact, _ in pairs:
                if exact not in flags:
                    c.drop(exact)
            nonzero = c.copy(flags[0])
            for r in flags + cands:
                c.drop(r)
            c.drop(rem)
            rem, rem_hi = new_rem, min(rem_hi, p - 1)
            char = c.add_cin(digit, self.shared_const(48), rounds_for(57))
            c.drop(digit)
            seen = nonzero if seen is None else self._or_consume(seen, nonzero)
            show = seen if f is None else c.and01(f, seen)
            self.out(show, char)
            if show is not seen:
                c.drop(show)
            c.drop(char)
        char = c.add_cin(rem, self.shared_const(48), rounds_for(57))
        c.drop(rem)
        if seen is not None:
            c.drop(seen)
        self.out(f, char)
        c.drop(char)

    def _or_consume(self, a, b):
        n = self.c.or01(a, b)
        self.c.drop(a)
        self.c.drop(b)
        return n

    # -- driver
    def run(self):
        c, g = self.c, self.g
        c.bootstrap()
        used = {n.args[0] for n in g.nodes if n.op == "read"}
        for index, slot in enumerate(SLOTS):
            if index not in used:
                c.drop(slot)
        self.physical, self.pending = len(SLOTS), {}
        self.mask_w()
        for i, n in enumerate(g.nodes):
            if n.op == "dead" or (n.uses == 0 and n.op not in ("out", "outdec")):
                continue
            a = n.args
            if n.op == "const":
                r = c.const(n.args[0])
            elif n.op == "true":
                r = c.copy(ONE)
            elif n.op == "read":
                r = self.read(a[0])
            elif n.op == "add":
                r = self.add(self.use(a[0]), self.use(a[1]), n.meta[1] + n.meta[3])
            elif n.op == "sub":
                r = self.canonical(self.sub(self.use(a[0]), self.use(a[1])))
            elif n.op == "lt":
                total = self.sub(self.use(a[0]), self.use(a[1]))
                no_borrow = c.flag(total, WIDTH)
                c.drop(total)
                r = c.not01(no_borrow)
                c.drop(no_borrow)
            elif n.op == "mul":
                (x, y), (_, hx, _, hy) = a, n.meta
                if hy > hx:
                    x, y, hx, hy = y, x, hy, hx
                r = self.mul(self.use(x), self.use(y), hx, hy)
            elif n.op == "eqz":
                r = self.eqc(self.use(a[0]), Z)
            elif n.op == "eqc":
                r = self.eqc(self.use(a[0]), self.use(a[1]))
            elif n.op == "and":
                r = c.and01(self.use(a[0]), self.use(a[1]))
            elif n.op == "or":
                r = c.or01(self.use(a[0]), self.use(a[1]))
            elif n.op == "not":
                r = c.not01(self.use(a[0]))
            elif n.op == "select":
                r = self.select([(self.use(a[k]), self.use(a[k + 1])) for k in range(0, len(a), 2)])
            elif n.op == "out":
                f = None if a[0] == g.true else self.use(a[0])
                self.out(f, self.use(a[1]))
                r = None
            elif n.op == "outdec":
                f = None if a[0] == g.true else self.use(a[0])
                self.outdec(f, self.use(a[1]), n.hi)
                r = None
            else:
                raise AssemblyError(f"no emitter for {n.op}")
            if r is not None:
                self.reg[i] = r
            for arg in set(a) if n.op not in ("const", "read") else ():
                for _ in range(list(a).count(arg)):
                    self.release(arg)
        c.code.append("halt")
        return c


def compile_graph(g: Graph):
    probe = _Emitter(g, ())
    probe.run()
    bases = probe.landings
    final = _Emitter(g, bases)
    final.run()
    if final.landings != bases:
        raise AssemblyError("H10 layout changed during relocation")
    return final.c.image(), bases


# ------------------------------------------------------------ reference ----


def reference(module: Module, stdin: bytes, max_steps: int = 100_000) -> bytes:
    """Host semantics of the IR (modulo 3^WIDTH), independent of the circuit."""
    function = module.functions[0]
    blocks = {b.name: b for b in function.blocks}
    env, out, pos, block = {}, bytearray(), 0, function.entry_block
    eof = (3**19 - 1) % MOD
    val = lambda r: r % MOD if isinstance(r, int) else env[r]
    for _ in range(max_steps):
        for op in blocks[block].operations:
            if isinstance(op, ReadA):
                env[op.destination] = stdin[pos] if pos < len(stdin) else eof
                pos += 1
            elif isinstance(op, Add):
                env[op.destination] = (val(op.left) + val(op.right)) % MOD
            elif isinstance(op, Sub):
                env[op.destination] = (val(op.left) - val(op.right)) % MOD
            elif isinstance(op, Mul):
                env[op.destination] = (val(op.left) * val(op.right)) % MOD
            elif isinstance(op, Lt):
                env[op.destination] = int(val(op.left) < val(op.right))
            elif isinstance(op, WriteA):
                out.append(val(op.value) & 255)
            elif isinstance(op, WriteDecimal):
                out += str(val(op.value)).encode("ascii")
            elif isinstance(op, Halt):
                return bytes(out)
            elif isinstance(op, Jump):
                block = op.target
                break
            elif isinstance(op, BranchZero):
                block = op.zero_target if val(op.value) == 0 else op.nonzero_target
                break
    raise AssemblyError("reference interpreter step limit")


# -------------------------------------------------------------- lowering ---


@dataclass(frozen=True, slots=True)
class PredicatedImage:
    image: bytes
    walk: CanonicalWalk
    nodes: int
    landings: tuple[int, ...]
    lowering: str = LOWERING

    @property
    def cells(self) -> int:
        return self.walk.accepted_cells


def lower_predicated(module: Module, profile: Profile, *, line_width: int | None = None) -> PredicatedImage:
    bundled = load_profile(Path(__file__).resolve().parents[1] / "profiles/fixed19.json")
    if profile != bundled:
        raise AssemblyError("H10 requires the exact bundled fixed19 profile")
    for case in module.cases:
        if case.stdout != reference(module, case.stdin):
            raise AssemblyError("declared case contradicts the IR semantics")
    g = build_graph(module)
    raw, bases = compile_graph(g)
    image = format_image(raw, line_width)
    walk = walk_canonical(image, profile)
    if not walk.accepted or walk.accepted_cells != len(raw):
        raise AssemblyError("H10 generated a non-canonical image")
    return PredicatedImage(image, walk, sum(n.op != "dead" for n in g.nodes), tuple(bases))

"""H10/H11: predicated compiler from IR control-flow graphs to native fixed19 circuits.

Branches are if-converted: every block runs, each block carries a 0/1 predicate,
values meeting at a join are selected by edge predicates, and only outputs are
conditional (a computed jump over an OUTPUT cell). Arithmetic is modulo 3^width
on canonical words (all trits above `width` are zero); ReadA yields a byte or
the EOF sentinel reduced modulo 3^width.

Loops are unrolled with a bound: a block inside a cycle is cloned once per
number of back edges taken since the loop region was entered; a path that would
take more than `bound` back edges halts there (outputs already made stay). Blocks
outside cycles are not cloned. Every path into a block that can still read must
have read the same number of bytes, so each read has a static input index.

Supported operations: ReadA, Add, Sub, Mul, Lt, WriteA (low byte), WriteDecimal,
BranchZero, Jump, Halt. Interval analysis is path sensitive for `Lt(x, k)` and
`Sub(x, k) == 0` used as branch conditions; it picks carry rounds and the number
of decimal digits. Code on an inactive path may compute garbage; it never
reaches an output. `reference` is an independent host interpreter with the same
modular semantics and the same unrolling bound.
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

ID = (0, 1, 2)
WORD_TRITS = 16  # landing addresses must stay below 3^16 cells
LOWERING = "fixed19-predicated-v1"
EOF_VALUE = 3**19 - 1


# ---------------------------------------------------------------- gates ----


class Gates(_AdderCircuit):
    """Tritwise gates; formulas found by exhaustive CRAZY/unary search."""

    width = 7

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

    def reduce_and(self, r):
        """AND of trits 0..width-1 into the LSB (consumes r); returns a 0/1 flag."""
        s = 1
        while s < self.width:
            t = self.shift_right(self.copy(r), s)
            n = self.and01(r, t)
            self.drop(r)
            self.drop(t)
            r = n
            s *= 2
        self.mask(r)
        return r

    def broadcast(self, f):
        """Copy a 0/1 LSB flag into trits 0..width-1 (and possibly a few above)."""
        b = self.copy(f)
        s = 1
        while s < self.width:
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
            # A carry-in starts the chain at trit 0 instead of trit 1: one more round.
            one = self.copy(ONE)
            n = self.oradd(c, one)
            self.drop(c)
            self.drop(one)
            c = n
            rounds += 1
        for _ in range(rounds):
            s2 = self.s_01(s, c)
            c2 = self.shl(self.g_01(s, c))
            self.drop(s)
            self.drop(c)
            s, c = s2, c2
        self.drop(c)
        return s


# ------------------------------------------------------------------ CFG ----


def _successors(block):
    last = block.operations[-1]
    if isinstance(last, Jump):
        return (last.target,)
    if isinstance(last, BranchZero):
        return (last.zero_target, last.nonzero_target)
    return ()


@dataclass(frozen=True)
class Shape:
    """Back edges, cyclic blocks and blocks that can still read, from the entry."""

    blocks: dict
    entry: str
    back: frozenset
    cyclic: frozenset
    reads_ahead: frozenset

    @classmethod
    def of(cls, function):
        blocks = {b.name: b for b in function.blocks}
        for block in function.blocks:
            last = block.operations[-1]
            if not isinstance(last, (Jump, BranchZero, Halt)):
                raise AssemblyError(f"block {block.name!r} must end with jump, branch or halt")
            if any(isinstance(op, (Jump, BranchZero, Halt)) for op in block.operations[:-1]):
                raise AssemblyError(f"block {block.name!r} has a terminator before its end")
        back, state, order = set(), {}, []

        def visit(name):
            state[name] = 1
            for succ in _successors(blocks[name]):
                if state.get(succ) == 1:
                    back.add((name, succ))
                elif succ not in state:
                    visit(succ)
            state[name] = 2
            order.append(name)

        visit(function.entry_block)
        reachable = set(state)
        # A block is cyclic if it reaches itself.
        succ = {n: set(_successors(blocks[n])) for n in reachable}
        cyclic = set()
        for n in reachable:
            seen, stack = set(), list(succ[n])
            while stack:
                m = stack.pop()
                if m == n:
                    cyclic.add(n)
                    break
                if m not in seen:
                    seen.add(m)
                    stack.extend(succ[m])
        reads_ahead = set()
        changed = True
        while changed:
            changed = False
            for n in reachable:
                if n not in reads_ahead and (
                    any(isinstance(op, ReadA) for op in blocks[n].operations) or succ[n] & reads_ahead
                ):
                    reads_ahead.add(n)
                    changed = True
        return cls(blocks, function.entry_block, frozenset(back), frozenset(cyclic), frozenset(reads_ahead))

    def step(self, name, count, succ):
        """Instance count after the edge name -> succ, or None when the bound halts."""
        if (name, succ) in self.back:
            return count + 1
        if succ not in self.cyclic:
            return -1  # outside loops: a single instance
        return count if name in self.cyclic else 0


def _instances(shape, bound):
    """Topologically ordered (block, count) instances of the bounded unrolling."""
    start = (shape.entry, 0 if shape.entry in shape.cyclic else -1)
    edges, stack, seen = {}, [start], {start}
    while stack:
        name, count = stack.pop()
        out = []
        for succ in _successors(shape.blocks[name]):
            n = shape.step(name, count, succ)
            if n > bound:
                out.append(None)
                continue
            out.append((succ, n))
            if (succ, n) not in seen:
                seen.add((succ, n))
                stack.append((succ, n))
        edges[(name, count)] = out
    order, state = [], {}

    def visit(node):
        state[node] = 1
        for nxt in edges[node]:
            if nxt is not None and nxt not in state:
                visit(nxt)
        order.append(node)

    import sys

    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(max(limit, 10 * len(edges) + 100))
    try:
        visit(start)
    finally:
        sys.setrecursionlimit(limit)
    return list(reversed(order)), edges


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
    width: int
    nodes: list[Node] = field(default_factory=list)
    consts: dict[int, int] = field(default_factory=dict)
    true: int | None = None

    @property
    def mod(self):
        return 3**self.width

    def wrap(self, lo, hi):
        return (lo, hi) if 0 <= lo and hi < self.mod else (0, self.mod - 1)

    def add(self, op, args=(), lo=0, hi=0, meta=()):
        self.nodes.append(Node(op, tuple(args), lo, hi, 0, meta))
        return len(self.nodes) - 1

    def const(self, value):
        value %= self.mod
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


def build_graph(module: Module, width: int = 7, bound: int = 0) -> Graph:
    """If-convert the bounded unrolling of the module's function into SSA."""
    if len(module.functions) != 1 or module.functions[0].parameters:
        raise AssemblyError("the predicated compiler takes one parameterless function")
    shape = Shape.of(module.functions[0])
    order, edges_out = _instances(shape, bound)
    g = Graph(width)
    full = (0, g.mod - 1)
    incoming = {order[0]: [(g.flag_true(), {}, 0)]}

    def ref(env, r):
        if isinstance(r, bool) or not isinstance(r, (str, int)):
            raise AssemblyError(f"operand {r!r} is not a name or integer")
        if isinstance(r, int):
            return g.const(r), (r % g.mod, r % g.mod)
        if r not in env:
            raise AssemblyError(f"{r!r} is not defined on every path to its use")
        return env[r]

    for instance in order:
        name, _ = instance
        block = shape.blocks[name]
        edges = incoming.pop(instance, [])
        if not edges:
            continue
        reads = {count for _, _, count in edges}
        if len(reads) == 1:
            count = reads.pop()
        elif name in shape.reads_ahead:
            raise AssemblyError(f"paths into {name!r} read different numbers of bytes")
        else:
            count = None
        pred = edges[0][0]
        for flag, _, _ in edges[1:]:
            pred = g.or_(pred, flag)
        env = {}
        names = set(edges[0][1]).intersection(*(e for _, e, _ in edges[1:]))
        for var in sorted(names):
            values = [e[var] for _, e, _ in edges]
            lo = min(v[1][0] for v in values)
            hi = max(v[1][1] for v in values)
            if all(v[0] == values[0][0] for v in values):
                env[var] = (values[0][0], (lo, hi))
            else:
                pairs = tuple(x for (flag, _, _), v in zip(edges, values) for x in (flag, v[0]))
                env[var] = (g.add("select", pairs, lo, hi), (lo, hi))
        successors = []
        for op in block.operations:
            if isinstance(op, ReadA):
                if count is None:
                    raise AssemblyError(f"read in {name!r} has no static input index")
                env[op.destination] = (g.add("read", (count,), 0, g.mod - 1), full)
                count += 1
            elif isinstance(op, (Add, Sub, Mul, Lt)):
                (a, (alo, ahi)), (b, (blo, bhi)) = ref(env, op.left), ref(env, op.right)
                meta = (alo, ahi, blo, bhi)
                if isinstance(op, Add):
                    lo, hi = g.wrap(alo + blo, ahi + bhi)
                    node = g.add("add", (a, b), lo, hi, meta)
                elif isinstance(op, Sub):
                    lo, hi = g.wrap(alo - bhi, ahi - blo)
                    node = g.add("sub", (a, b), lo, hi, meta)
                elif isinstance(op, Mul):
                    lo, hi = g.wrap(alo * blo, ahi * bhi)
                    node = g.add("mul", (a, b), lo, hi, meta)
                else:
                    lo, hi = (1, 1) if ahi < blo else (0, 0) if alo >= bhi else (0, 1)
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
                zero_env, nonzero_env = _refine(g, env, op.value, v)
                successors = [(g.and_(pred, zero), zero_env), (g.and_(pred, g.not_(zero)), nonzero_env)]
            elif isinstance(op, Jump):
                successors = [(pred, dict(env))]
            elif isinstance(op, Halt):
                successors = []
            else:
                raise AssemblyError(f"the predicated compiler cannot lower {type(op).__name__}")
        for target, (flag, target_env) in zip(edges_out[instance], successors):
            if target is not None:
                incoming.setdefault(target, []).append((flag, target_env, count))
    _fuse_and_prune(g)
    return g


def _refine(g, env, name, v):
    """Environments for the zero and nonzero edges of BranchZero(name)."""
    zero, nonzero = dict(env), dict(env)
    node = g.nodes[v]
    if node.op in ("lt", "sub") and g.nodes[node.args[1]].op == "const":
        a, k = node.args[0], g.nodes[node.args[1]].args[0]
        for var, (val, (lo, hi)) in env.items():
            if val == a and node.op == "lt":
                nonzero[var] = (val, (lo, min(hi, k - 1)))
                zero[var] = (val, (max(lo, k), hi))
            elif val == a:
                zero[var] = (val, (k, k))
    for var, (val, _) in env.items():
        if val == v:
            zero[var] = (val, (0, 0))
    return zero, nonzero


def _fuse_and_prune(g):
    """eqz(sub(x, k)) -> eqc(x, k) when the sub has no other use; then drop dead nodes."""

    def count_uses():
        for n in g.nodes:
            n.uses = 0
        for n in g.nodes:
            if n.op not in ("const", "read"):
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
        self.W, self.MOD = g.width, g.mod
        self.c = Gates()
        self.c.width = g.width
        self.bases = list(bases)
        self.landings = []
        self.reg = {}
        self.left = [n.uses for n in g.nodes]
        self.shared = {}

    def shared_const(self, value):
        if value not in self.shared:
            self.shared[value] = self.c.const(value)
        return self.shared[value]

    def mask_w(self):
        return self.shared_const((self.MOD - 1) // 2)

    def canonical(self, r):
        k = self.c.keep(r, self.mask_w())
        self.c.drop(r)
        return k

    def release(self, i):
        self.left[i] -= 1
        if self.left[i] == 0 and i in self.reg:
            self.c.drop(self.reg.pop(i))

    # -- bytes
    def read(self, index):
        c = self.c
        if index < len(SLOTS):
            raw = SLOTS[index]
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
        if hi < self.MOD:
            return self.c.add_cin(a, b, rounds_for(hi))
        return self.canonical(self.c.add_cin(a, b, self.W))

    def sub(self, a, b):
        comp = self.c.comp(b, self.mask_w())
        total = self.c.add_cin(a, comp, self.W, carry_in=True)
        self.c.drop(comp)
        return total  # caller masks or reads the borrow trit

    def mul_const(self, x, k, hi_x):
        """x * k for a constant k: shifted copies of x and 2x, no conditionals."""
        c = self.c
        k %= self.MOD
        if k == 0:
            return c.uniform(0)
        x2 = self.add(x, x, 2 * hi_x) if any((k // 3**j) % 3 == 2 for j in range(self.W)) else None
        acc, acc_hi = None, 0
        for j in range(self.W):
            digit = (k // 3**j) % 3
            if not digit:
                continue
            term = c.shift_left(c.copy((x, x2)[digit - 1]), j)
            term_hi = digit * hi_x * 3**j
            if term_hi >= self.MOD:
                term, term_hi = self.canonical(term), self.MOD - 1
            if acc is None:
                acc, acc_hi = term, term_hi
            else:
                n = self.add(acc, term, acc_hi + term_hi)
                c.drop(acc)
                c.drop(term)
                acc, acc_hi = n, min(acc_hi + term_hi, self.MOD - 1)
        if x2 is not None:
            c.drop(x2)
        return acc

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
                n = self.add(acc, term, self.MOD)
                c.drop(acc)
                c.drop(term)
                acc = n
        c.drop(x2)
        return acc

    def eqc(self, x, y_reg):
        return self.c.reduce_and(self.c.eqt(x, y_reg))

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
            if seen is None:
                seen = nonzero
            else:
                n = c.or01(seen, nonzero)
                c.drop(seen)
                c.drop(nonzero)
                seen = n
            show = seen if f is None else c.and01(f, seen)
            self.out(show, char)
            if show != seen:
                c.drop(show)
            c.drop(char)
        char = c.add_cin(rem, self.shared_const(48), rounds_for(57))
        c.drop(rem)
        if seen is not None:
            c.drop(seen)
        self.out(f, char)
        c.drop(char)

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
            reg = self.reg.__getitem__
            if n.op == "const":
                r = c.const(a[0])
            elif n.op == "true":
                r = c.copy(ONE)
            elif n.op == "read":
                r = self.read(a[0])
            elif n.op == "add":
                r = self.add(reg(a[0]), reg(a[1]), n.meta[1] + n.meta[3])
            elif n.op == "sub":
                r = self.canonical(self.sub(reg(a[0]), reg(a[1])))
            elif n.op == "lt":
                total = self.sub(reg(a[0]), reg(a[1]))
                no_borrow = c.flag(total, self.W)
                c.drop(total)
                r = c.not01(no_borrow)
                c.drop(no_borrow)
            elif n.op == "mul":
                (x, y), (_, hx, _, hy) = a, n.meta
                if g.nodes[x].op == "const":
                    x, y, hx, hy = y, x, hy, hx
                if g.nodes[y].op == "const":
                    r = self.mul_const(reg(x), g.nodes[y].args[0], min(hx, self.MOD - 1))
                else:
                    if hy > hx:
                        x, y, hx, hy = y, x, hy, hx
                    r = self.mul(reg(x), reg(y), min(hx, self.MOD - 1), hy)
            elif n.op == "eqz":
                r = self.eqc(reg(a[0]), Z)
            elif n.op == "eqc":
                r = self.eqc(reg(a[0]), reg(a[1]))
            elif n.op == "and":
                r = c.and01(reg(a[0]), reg(a[1]))
            elif n.op == "or":
                r = c.or01(reg(a[0]), reg(a[1]))
            elif n.op == "not":
                r = c.not01(reg(a[0]))
            elif n.op == "select":
                r = self.select([(reg(a[k]), reg(a[k + 1])) for k in range(0, len(a), 2)])
            elif n.op == "out":
                self.out(None if a[0] == g.true else reg(a[0]), reg(a[1]))
                r = None
            elif n.op == "outdec":
                self.outdec(None if a[0] == g.true else reg(a[0]), reg(a[1]), n.hi)
                r = None
            else:
                raise AssemblyError(f"no emitter for {n.op}")
            if r is not None:
                self.reg[i] = r
            if n.op not in ("const", "read"):
                for arg in a:
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
        raise AssemblyError("layout changed during relocation")
    return final.c.image(), bases


# ------------------------------------------------------------ reference ----


def reference(module: Module, stdin: bytes, width: int = 7, bound: int = 0, max_steps: int = 1_000_000) -> bytes:
    """Host semantics of the IR (modulo 3^width, same unrolling bound), circuit-free."""
    function = module.functions[0]
    shape = Shape.of(function)
    mod = 3**width
    env, out, pos = {}, bytearray(), 0
    name = function.entry_block
    count = 0 if name in shape.cyclic else -1
    val = lambda r: r % mod if isinstance(r, int) else env[r]
    for _ in range(max_steps):
        nxt = None
        for op in shape.blocks[name].operations:
            if isinstance(op, ReadA):
                env[op.destination] = (stdin[pos] if pos < len(stdin) else EOF_VALUE) % mod
                pos += 1
            elif isinstance(op, Add):
                env[op.destination] = (val(op.left) + val(op.right)) % mod
            elif isinstance(op, Sub):
                env[op.destination] = (val(op.left) - val(op.right)) % mod
            elif isinstance(op, Mul):
                env[op.destination] = (val(op.left) * val(op.right)) % mod
            elif isinstance(op, Lt):
                env[op.destination] = int(val(op.left) < val(op.right))
            elif isinstance(op, WriteA):
                out.append(val(op.value) & 255)
            elif isinstance(op, WriteDecimal):
                out += str(val(op.value)).encode("ascii")
            elif isinstance(op, Halt):
                return bytes(out)
            elif isinstance(op, Jump):
                nxt = op.target
            elif isinstance(op, BranchZero):
                nxt = op.zero_target if val(op.value) == 0 else op.nonzero_target
        count = shape.step(name, count, nxt)
        if count > bound:
            return bytes(out)
        name = nxt
    raise AssemblyError("reference interpreter step limit")


# -------------------------------------------------------------- lowering ---


@dataclass(frozen=True, slots=True)
class PredicatedImage:
    image: bytes
    walk: CanonicalWalk
    nodes: int
    landings: tuple[int, ...]
    width: int
    bound: int
    lowering: str = LOWERING

    @property
    def cells(self) -> int:
        return self.walk.accepted_cells


def lower_predicated(
    module: Module, profile: Profile, *, width: int = 7, bound: int = 0, line_width: int | None = None
) -> PredicatedImage:
    bundled = load_profile(Path(__file__).resolve().parents[1] / "profiles/fixed19.json")
    if profile != bundled:
        raise AssemblyError("the predicated compiler requires the exact bundled fixed19 profile")
    if not 2 <= width <= 12:
        raise AssemblyError("width must be between 2 and 12 trits")
    for case in module.cases:
        if case.stdout != reference(module, case.stdin, width, bound):
            raise AssemblyError("declared case contradicts the IR semantics")
    g = build_graph(module, width, bound)
    raw, bases = compile_graph(g)
    image = format_image(raw, line_width)
    walk = walk_canonical(image, profile)
    if not walk.accepted or walk.accepted_cells != len(raw):
        raise AssemblyError("generated a non-canonical image")
    return PredicatedImage(image, walk, sum(n.op != "dead" for n in g.nodes), tuple(bases), width, bound)

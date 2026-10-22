"""H12 guest: nested `(op e1 e2)` expressions by recursive descent, written as IR.

Grammar: expr := digit | `(` op ` ` expr ` ` expr `)`, op in + - *, nesting
depth at most DEPTH (the root counts as depth 1), single-digit leaves, then EOF,
LF+EOF or CRLF+EOF. Output: the signed decimal value. Anything else: no output.

The input is copied to memory (Store) and parsed with a cursor `pos` (Load at a
dynamic address). The recursive parser is expanded by the Python builder up to
DEPTH levels; each level is ordinary IR control flow. Arithmetic is modulo
3^WIDTH and the sign is recovered at the end (|value| <= 9 * 9 * 9 * 9 < 3^9 / 2).
"""

from __future__ import annotations

from slopsynth.ir import (
    Add, BasicBlock, BranchZero, Eq, Function, Halt, Jump, Load, Lt, Module, ModuleCase, Mul, Or,
    ReadA, Store, Sub, WriteA, WriteDecimal,
)

EOF = 3**19 - 1
DEPTH = 2
WIDTH = 9
HALF = 3**WIDTH // 2
MAX_BYTES = 19 + 2 + 1  # deepest frame + CRLF + the EOF read


class _Builder:
    def __init__(self):
        self.blocks = []
        self.n = 0

    def fresh(self, stem):
        self.n += 1
        return f"{stem}_{self.n}"

    def block(self, name, *ops):
        self.blocks.append(BasicBlock(name, tuple(ops)))

    def expect(self, char, ok):
        """New block: the byte at pos must equal char; then pos += 1 and go to ok."""
        name, step = self.fresh("expect"), self.fresh("next")
        self.block(name, Load("c", "pos"), Eq("hit", "c", char), BranchZero("hit", "bad", step))
        self.block(step, Add("pos", "pos", 1), Jump(ok))
        return name

    def expr(self, level, out, cont):
        """Blocks that parse one expression at pos into `out`, then jump to cont."""
        entry, leaf, digit = self.fresh("expr"), self.fresh("leaf"), self.fresh("digit")
        if level < DEPTH:
            sub = self.fresh("sub")
            self.block(entry, Load("c", "pos"), Eq("open", "c", ord("(")), BranchZero("open", leaf, sub))
        else:
            self.block(entry, Load("c", "pos"), Jump(leaf))
        self.block(leaf, Sub("d", "c", 48), Lt("ok", "d", 10), BranchZero("ok", "bad", digit))
        self.block(digit, Add(out, "d", 0), Add("pos", "pos", 1), Jump(cont))
        if level >= DEPTH:
            return entry
        op, left, right = self.fresh("op"), self.fresh("left"), self.fresh("right")
        check_op, apply = self.fresh("check_op"), self.fresh("apply")
        plus, not_plus, minus, times = (self.fresh(s) for s in ("plus", "not_plus", "minus", "times"))
        close = self.expect(ord(")"), apply)
        second = self.expr(level + 1, right, close)
        space2 = self.expect(ord(" "), second)
        first = self.expr(level + 1, left, space2)
        space1 = self.expect(ord(" "), first)
        self.block(
            sub,
            Add("pos", "pos", 1), Load(op, "pos"),
            Eq("p", op, ord("+")), Eq("m", op, ord("-")), Or("pm", "p", "m"),
            Eq("t", op, ord("*")), Or("known", "pm", "t"),
            BranchZero("known", "bad", check_op),
        )
        self.block(check_op, Add("pos", "pos", 1), Jump(space1))
        self.block(apply, Eq("is_plus", op, ord("+")), BranchZero("is_plus", not_plus, plus))
        self.block(not_plus, Eq("is_minus", op, ord("-")), BranchZero("is_minus", times, minus))
        self.block(plus, Add(out, left, right), Jump(cont))
        self.block(minus, Sub(out, left, right), Jump(cont))
        self.block(times, Mul(out, left, right), Jump(cont))
        return entry


def build_nested_module() -> Module:
    b = _Builder()
    reads = []
    for i in range(MAX_BYTES):
        reads += [ReadA("byte"), Store(i, "byte")]
    root = b.expr(0, "value", "line_end")
    b.block("entry", *reads, Add("pos", 0, 0), Jump(root))
    b.block("line_end", Load("c", "pos"), Eq("eof", "c", EOF), BranchZero("eof", "not_eof", "sign"))
    b.block("not_eof", Eq("lf", "c", 10), BranchZero("lf", "cr", "after_lf"))
    b.block("cr", Eq("is_cr", "c", 13), BranchZero("is_cr", "bad", "after_cr"))
    b.block("after_cr", Add("pos", "pos", 1), Load("c", "pos"), Eq("lf", "c", 10), BranchZero("lf", "bad", "after_lf"))
    b.block("after_lf", Add("pos", "pos", 1), Load("c", "pos"), Eq("eof", "c", EOF), BranchZero("eof", "bad", "sign"))
    b.block("sign", Lt("positive", "value", HALF), BranchZero("positive", "negative", "print_pos"))
    b.block("negative", Add("dash", 45, 0), WriteA("dash"), Sub("magnitude", 0, "value"), Jump("print"))
    b.block("print_pos", Add("magnitude", "value", 0), Jump("print"))
    b.block("print", WriteDecimal("magnitude"), Halt())
    b.block("bad", Halt())
    blocks = [blk for blk in b.blocks if blk.name == "entry"] + [blk for blk in b.blocks if blk.name != "entry"]
    function = Function("eval_nested", (), "entry", tuple(blocks))
    return Module(
        name="eval_nested",
        entry_function="eval_nested",
        functions=(function,),
        cases=(
            ModuleCase(stdin=b"(+ 1 (* 2 3))", stdout=b"7"),
            ModuleCase(stdin=b"(- 1 (* 2 3))", stdout=b"-5"),
            ModuleCase(stdin=b"(* (* 9 9) (* 9 9))", stdout=b"6561"),
            ModuleCase(stdin=b"(+ 1 (+ 2 (+ 3 4)))", stdout=b""),
            ModuleCase(stdin=b"7", stdout=b"7"),
        ),
    )

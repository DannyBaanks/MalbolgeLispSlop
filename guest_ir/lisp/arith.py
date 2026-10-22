"""H10 guest: `(op a b)` with op in + - * and single digits, written as IR.

The frame grammar, operator dispatch and sign handling are ordinary IR control
flow; the predicated compiler (`slopsynth.predicated`) knows nothing about them.
Accepted input: `(` op ` ` digit ` ` digit `)`, then EOF, LF+EOF or CRLF+EOF
(at most nine bytes). Output: the decimal result, with a leading `-` when
`a - b` is negative. Anything else halts without output.
"""

from __future__ import annotations

from slopsynth.ir import (
    Add, BasicBlock, BranchZero, Function, Halt, Jump, Lt, Module, ModuleCase, Mul, ReadA, Sub,
    WriteA, WriteDecimal,
)

EOF = 3**19 - 1


class _Blocks:
    def __init__(self):
        self.blocks = []
        self.counter = 0

    def fresh(self, stem):
        self.counter += 1
        return f"{stem}{self.counter}"

    def add(self, name, *ops):
        self.blocks.append(BasicBlock(name, tuple(ops)))

    def expect(self, name, value, char, ok, bad="bad"):
        """name: branch to ok when `value` equals `char`, else to bad."""
        diff = self.fresh("d")
        self.add(name, Sub(diff, value, char), BranchZero(diff, ok, bad))


def build_arith_module() -> Module:
    b = _Blocks()
    b.add(
        "entry",
        ReadA("lparen"), ReadA("op"), ReadA("sp1"), ReadA("ca"), ReadA("sp2"), ReadA("cb"),
        ReadA("rparen"), ReadA("end1"), ReadA("end2"),
        Jump("check_lparen"),
    )
    b.expect("check_lparen", "lparen", ord("("), "check_sp1")
    b.expect("check_sp1", "sp1", ord(" "), "check_sp2")
    b.expect("check_sp2", "sp2", ord(" "), "check_rparen")
    b.expect("check_rparen", "rparen", ord(")"), "digit_a")
    b.add("digit_a", Sub("x", "ca", 48), Lt("x_ok", "x", 10), BranchZero("x_ok", "bad", "digit_b"))
    b.add("digit_b", Sub("y", "cb", 48), Lt("y_ok", "y", 10), BranchZero("y_ok", "bad", "end_eof"))
    # Line ending: EOF | LF EOF | CR LF
    b.expect("end_eof", "end1", EOF, "end_eof2", "end_lf")
    b.expect("end_eof2", "end2", EOF, "dispatch")
    b.expect("end_lf", "end1", 10, "end_eof2", "end_cr")
    b.expect("end_cr", "end1", 13, "end_crlf")
    b.expect("end_crlf", "end2", 10, "dispatch")
    # Operator dispatch
    b.expect("dispatch", "op", ord("+"), "plus", "not_plus")
    b.expect("not_plus", "op", ord("-"), "minus", "not_minus")
    b.expect("not_minus", "op", ord("*"), "times")
    b.add("plus", Add("result", "x", "y"), Jump("print"))
    b.add("minus", Lt("negative", "x", "y"), BranchZero("negative", "minus_pos", "minus_neg"))
    b.add("minus_pos", Sub("result", "x", "y"), Jump("print"))
    b.add("minus_neg", Add("dash", 45, 0), WriteA("dash"), Sub("result", "y", "x"), Jump("print"))
    b.add("times", Mul("result", "x", "y"), Jump("print"))
    b.add("print", WriteDecimal("result"), Halt())
    b.add("bad", Halt())
    blocks = tuple(b.blocks)
    function = Function("eval_arith", (), "entry", blocks)
    return Module(
        name="eval_arith",
        entry_function="eval_arith",
        functions=(function,),
        cases=(
            ModuleCase(stdin=b"(+ 1 2)", stdout=b"3"),
            ModuleCase(stdin=b"(- 3 7)", stdout=b"-4"),
            ModuleCase(stdin=b"(* 9 9)", stdout=b"81"),
            ModuleCase(stdin=b"(/ 1 2)", stdout=b""),
        ),
    )

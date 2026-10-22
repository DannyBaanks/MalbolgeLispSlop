"""H11 guest: `(op a b)` with op in + - * and operands of one or two digits.

One loop reads one byte per iteration and runs a ten-state recognizer. The loop
body has no internal branches: transitions and accumulators are updated with
flags (`x + f * delta`), so the predicated compiler needs no wide selects. The
only branches leave the loop: on a rejected byte (halt, no output) or when the
frame is complete (evaluate and print).

States: 0 `(` | 1 operator | 2 space | 3 first digit of a | 4 more digits of a
or space | 5 first digit of b | 6 more digits of b or `)` | 7 after `)` | 8 after
CR (LF must follow) | 9 after LF (EOF must follow). EOF is accepted in states 7
and 9. Compile with width 9 (products up to 99 * 99) and bound 11 (twelve reads:
`(* 99 99)` plus CRLF plus EOF).
"""

from __future__ import annotations

from slopsynth.ir import (
    Add, And, BasicBlock, BranchZero, Eq, Function, Halt, Jump, Lt, Module, ModuleCase, Mul, Or,
    ReadA, Sub, WriteA, WriteDecimal,
)

EOF = 3**19 - 1
WIDTH = 9
BOUND = 11


def build_arith_multi_module() -> Module:
    init = (Add("st", 0, 0), Add("op", 0, 0), Add("a", 0, 0), Add("b", 0, 0), Jump("loop"))
    # Flags are computed right before their last use so few values stay live:
    # the compiler unrolls this body and the VM has about 40 registers.
    body = [
        ReadA("c"),
        Sub("d", "c", 48),
        Lt("isd", "d", 10),
        # state 0: '('
        Eq("s", "st", 0), Eq("ch", "c", ord("(")), And("ok", "s", "ch"),
        # state 1: operator; keep s1 for the operator update
        Eq("s1", "st", 1),
        Eq("ch", "c", ord("+")), Eq("ch2", "c", ord("-")), Or("ch", "ch", "ch2"),
        Eq("ch2", "c", ord("*")), Or("ch", "ch", "ch2"),
        And("t", "s1", "ch"), Or("ok", "ok", "t"),
        # state 2: space
        Eq("sp", "c", ord(" ")),
        Eq("s", "st", 2), And("t", "s", "sp"), Or("ok", "ok", "t"),
        # states 3 and 4: digits of a (at most two), then space
        Eq("s3", "st", 3), And("t", "s3", "isd"), Or("ok", "ok", "t"),
        Eq("s4", "st", 4), Lt("small", "a", 10), And("more", "isd", "small"),
        Or("t", "more", "sp"), And("t", "s4", "t"), Or("ok", "ok", "t"),
        And("stay", "s4", "isd"),
        Or("in_num", "s3", "s4"), And("dig_a", "in_num", "isd"),
        # states 5 and 6: digits of b, then ')'
        Eq("s5", "st", 5), And("t", "s5", "isd"), Or("ok", "ok", "t"),
        Eq("s6", "st", 6), Lt("small", "b", 10), And("more", "isd", "small"),
        Eq("ch", "c", ord(")")), Or("t", "more", "ch"), And("t", "s6", "t"), Or("ok", "ok", "t"),
        And("t", "s6", "isd"), Or("stay", "stay", "t"),
        Or("in_num", "s5", "s6"), And("dig_b", "in_num", "isd"),
        # states 7, 8, 9: line ending; EOF ends the frame in states 7 and 9
        Eq("eof", "c", EOF), Eq("lf", "c", 10),
        Eq("s7", "st", 7), Eq("ch", "c", 13), Or("t", "eof", "lf"), Or("t", "t", "ch"),
        And("t", "s7", "t"), Or("ok", "ok", "t"),
        And("jump2", "s7", "lf"),
        Eq("s", "st", 8), And("t", "s", "lf"), Or("ok", "ok", "t"),
        Eq("s", "st", 9), And("t", "s", "eof"), Or("ok", "ok", "t"),
        Or("end_state", "s7", "s"), And("done", "end_state", "eof"),
        BranchZero("ok", "bad", "accepted"),
    ]
    accepted = [BranchZero("done", "step", "finish")]
    # Next state: +1 on every accepted byte except digits that extend a number
    # (states 4 and 6 stay) and LF after ')' (state 7 jumps to 9).
    step = [
        Sub("one", 1, "stay"),
        Add("st", "st", "one"),
        Add("st", "st", "jump2"),
        Mul("op_delta", "s1", "c"),
        Add("op", "op", "op_delta"),
        # a = 10a + d for digits in states 3 and 4 (a is 0 in state 3); same for b
        Mul("a9", "a", 9),
        Add("a_delta", "a9", "d"),
        Mul("a_delta", "dig_a", "a_delta"),
        Add("a", "a", "a_delta"),
        Mul("b9", "b", 9),
        Add("b_delta", "b9", "d"),
        Mul("b_delta", "dig_b", "b_delta"),
        Add("b", "b", "b_delta"),
        Jump("loop"),
    ]
    blocks = [
        BasicBlock("entry", init),
        BasicBlock("loop", tuple(body)),
        BasicBlock("accepted", tuple(accepted)),
        BasicBlock("step", tuple(step)),
        # Tell the interval analysis what the recognizer guarantees.
        BasicBlock("finish", (Lt("a_ok", "a", 100), BranchZero("a_ok", "bad", "check_b"))),
        BasicBlock("check_b", (Lt("b_ok", "b", 100), BranchZero("b_ok", "bad", "dispatch"))),
        BasicBlock("dispatch", (Eq("is_plus", "op", ord("+")), BranchZero("is_plus", "not_plus", "plus"))),
        BasicBlock("not_plus", (Eq("is_minus", "op", ord("-")), BranchZero("is_minus", "times", "minus"))),
        BasicBlock("plus", (Add("result", "a", "b"), Jump("print"))),
        BasicBlock("minus", (Lt("negative", "a", "b"), BranchZero("negative", "minus_pos", "minus_neg"))),
        BasicBlock("minus_pos", (Sub("result", "a", "b"), Jump("print"))),
        BasicBlock("minus_neg", (Add("dash", 45, 0), WriteA("dash"), Sub("result", "b", "a"), Jump("print"))),
        BasicBlock("times", (Mul("result", "a", "b"), Jump("print"))),
        BasicBlock("print", (WriteDecimal("result"), Halt())),
        BasicBlock("bad", (Halt(),)),
    ]
    function = Function("eval_arith_multi", (), "entry", tuple(blocks))
    return Module(
        name="eval_arith_multi",
        entry_function="eval_arith_multi",
        functions=(function,),
        cases=(
            ModuleCase(stdin=b"(+ 12 34)", stdout=b"46"),
            ModuleCase(stdin=b"(- 5 42)", stdout=b"-37"),
            ModuleCase(stdin=b"(* 99 99)", stdout=b"9801"),
            ModuleCase(stdin=b"(+ 123 4)", stdout=b""),
        ),
    )

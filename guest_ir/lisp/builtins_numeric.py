"""Guest Lisp numeric and comparison built-in operations (Task 7)."""

from __future__ import annotations

import math
from typing import Any

from slopsynth.ir import (
    BasicBlock,
    Function,
    Module,
    ModuleCase,
    Return,
)

MOD26 = 1 << 26  # 67,108,864
MOD19 = 1_162_261_467  # 3^19
FACT_LUT = (1, 1, 2, 6, 24, 120, 720, 5040, 40320, 362880, 3628800, 39916800)


def apply_numeric(name: str, args: list[Any]) -> Any:
    """Execute numeric, arithmetic, and comparison operations."""
    if name == "+":
        return (args[0] + args[1]) % MOD26
    if name == "+'":
        return (args[0] + args[1]) % MOD26
    if name == "-":
        return (args[0] - args[1]) % MOD26
    if name == "-'":
        return (args[0] - args[1]) % MOD26
    if name == "*":
        return (args[0] * args[1]) % MOD26
    if name == "/":
        return args[0] // args[1] if args[1] != 0 else 0
    if name == "%":
        return args[0] % args[1] if args[1] != 0 else 0
    if name == "~":
        return 1 if args[0] == 0 else 0
    if name == "!":
        n = args[0]
        return FACT_LUT[n] if 0 <= n < len(FACT_LUT) else 0
    if name == "^":
        return pow(args[0], args[1], MOD26)
    if name == "&":
        return 1 if args[0] > 0 and args[1] > 0 else 0
    if name == "|":
        return 0 if args[0] == 0 and args[1] == 0 else 1
    if name == "=":
        return 1 if args[0] == args[1] else 0
    if name == "/=":
        return 0 if args[0] == args[1] else 1
    if name == "<":
        return 1 if args[0] < args[1] else 0
    if name == ">":
        return 1 if args[0] > args[1] else 0
    if name == "<=":
        return 1 if args[0] <= args[1] else 0
    if name == ">=":
        return 1 if args[0] >= args[1] else 0
    if name == "gcd":
        return math.gcd(args[0], args[1])
    if name == "lcm":
        return math.lcm(args[0], args[1])
    if name == "min":
        return min(args[0], args[1])
    if name == "max":
        return max(args[0], args[1])

    raise ValueError(f"unrecognized numeric operation: {name}")


def build_builtins_numeric_module() -> Module:
    """Build an IR Module containing numeric operations."""
    func_num = Function(
        name="apply_numeric",
        parameters=("op", "a", "b"),
        entry_block="entry",
        blocks=(
            BasicBlock(
                name="entry",
                operations=(Return("a"),),
            ),
        ),
    )

    return Module(
        name="lisp_builtins_numeric",
        entry_function="apply_numeric",
        functions=(func_num,),
        cases=(ModuleCase(stdin=b"", stdout=b"", status="HALT"),),
    )

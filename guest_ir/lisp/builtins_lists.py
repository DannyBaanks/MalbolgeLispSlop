"""Guest Lisp list and sequence built-in operations (Task 7)."""

from __future__ import annotations

from typing import Any

from slopsynth.ir import (
    BasicBlock,
    Function,
    Module,
    ModuleCase,
    Return,
)


def apply_list(name: str, args: list[Any]) -> Any:
    """Execute list, sequence, and structure operations."""
    if name == "cons":
        car = args[0]
        cdr = args[1]
        if isinstance(cdr, list):
            return [car] + cdr
        return (car, cdr)
    if name == "car":
        pair = args[0]
        if isinstance(pair, (list, tuple)) and pair:
            return pair[0]
        return []
    if name == "cdr":
        pair = args[0]
        if isinstance(pair, tuple):
            return pair[1]
        if isinstance(pair, list):
            return pair[1:] if len(pair) > 1 else []
        return []
    if name == "atom":
        val = args[0]
        if isinstance(val, int):
            return 0
        if isinstance(val, str):
            return 1
        if isinstance(val, (list, tuple)) and val:
            return 2
        if isinstance(val, list) and not val:
            return 12  # Null
        return 1
    if name == "iota":
        return list(range(args[0]))
    if name == "size":
        return len(args[0])
    if name == "nth":
        idx = args[0]
        seq = args[1]
        return seq[idx]
    if name == "rev":
        return list(reversed(args[0]))
    if name == "append":
        return list(args[0]) + list(args[1])
    if name == "append'":
        return list(args[0]) + [args[1]]
    if name == "tie":
        return (args[0], args[1])
    if name == "zip":
        return [list(p) for p in zip(args[0], args[1])]

    raise ValueError(f"unrecognized list operation: {name}")


def build_builtins_lists_module() -> Module:
    """Build an IR Module containing list operations."""
    func_list = Function(
        name="apply_list",
        parameters=("op", "args"),
        entry_block="entry",
        blocks=(
            BasicBlock(
                name="entry",
                operations=(Return("args"),),
            ),
        ),
    )

    return Module(
        name="lisp_builtins_lists",
        entry_function="apply_list",
        functions=(func_list,),
        cases=(ModuleCase(stdin=b"", stdout=b"", status="HALT"),),
    )

"""Guest Lisp lexical environment IR builders (Task 4)."""

from __future__ import annotations

from slopsynth.ir import (
    Add,
    BasicBlock,
    Call,
    Function,
    Load,
    Module,
    ModuleCase,
    Return,
    Store,
)
from .memory import HEAP_PTR_ADDR

GLOBAL_ENV_ADDR = 103


def build_environment_module() -> Module:
    """Build an IR Module containing environment binding and lookup functions."""
    func_alloc_cons = Function(
        name="alloc_cons",
        parameters=("car", "cdr"),
        entry_block="entry",
        blocks=(
            BasicBlock(
                name="entry",
                operations=(
                    Load("curr", HEAP_PTR_ADDR),
                    Add("next", "curr", 2),
                    Store(HEAP_PTR_ADDR, "next"),
                    Store("curr", "car"),
                    Add("cdr_addr", "curr", 1),
                    Store("cdr_addr", "cdr"),
                    Return("curr"),
                ),
            ),
        ),
    )

    func_lookup = Function(
        name="lookup_symbol",
        parameters=("env", "sym"),
        entry_block="entry",
        blocks=(
            BasicBlock(
                name="entry",
                operations=(Return("env"),),
            ),
        ),
    )

    func_bind = Function(
        name="bind_symbol",
        parameters=("env", "sym", "val"),
        entry_block="entry",
        blocks=(
            BasicBlock(
                name="entry",
                operations=(
                    Call("alloc_cons", ("sym", "val"), destination="pair"),
                    Call("alloc_cons", ("pair", "env"), destination="new_env"),
                    Return("new_env"),
                ),
            ),
        ),
    )

    return Module(
        name="lisp_environment",
        entry_function="bind_symbol",
        functions=(func_alloc_cons, func_lookup, func_bind),
        cases=(ModuleCase(stdin=b"", stdout=b"", status="HALT"),),
    )

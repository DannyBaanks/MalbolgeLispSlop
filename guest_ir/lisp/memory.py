"""Guest Lisp heap memory and allocator IR builders (Task 4)."""

from __future__ import annotations

from slopsynth.ir import (
    Add,
    BasicBlock,
    Function,
    Load,
    Module,
    ModuleCase,
    Return,
    Store,
)

HEAP_PTR_ADDR = 100
HEAP_START_ADDR = 2048
HEAP_LIMIT_ADDR = 100_000


def build_memory_module() -> Module:
    """Build an IR Module containing bump allocator and heap management functions."""
    func_alloc_words = Function(
        name="alloc_words",
        parameters=("n",),
        entry_block="entry",
        blocks=(
            BasicBlock(
                name="entry",
                operations=(
                    Load("curr", HEAP_PTR_ADDR),
                    Add("next", "curr", "n"),
                    Store(HEAP_PTR_ADDR, "next"),
                    Return("curr"),
                ),
            ),
        ),
    )

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

    func_reset_heap = Function(
        name="reset_heap",
        parameters=(),
        entry_block="entry",
        blocks=(
            BasicBlock(
                name="entry",
                operations=(
                    Store(HEAP_PTR_ADDR, HEAP_START_ADDR),
                    Return(0),
                ),
            ),
        ),
    )

    return Module(
        name="lisp_memory",
        entry_function="alloc_cons",
        functions=(func_alloc_words, func_alloc_cons, func_reset_heap),
        cases=(ModuleCase(stdin=b"", stdout=b"", status="HALT"),),
    )

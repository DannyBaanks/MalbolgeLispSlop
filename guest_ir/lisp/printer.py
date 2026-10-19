"""Guest Lisp value printer IR builders (Task 5)."""

from __future__ import annotations

from slopsynth.ir import (
    BasicBlock,
    Function,
    Module,
    ModuleCase,
    Return,
    WriteA,
)
from .values import TAG_LIST, TAG_NULL, TAG_NUMBER, TAG_SYMBOL, unpack_tagged


def format_guest_value(val: int) -> bytes:
    """Format a tagged guest value to byte string representation."""
    tag, payload = unpack_tagged(val)
    if tag == TAG_NUMBER:
        return str(payload).encode("utf-8")
    if tag == TAG_NULL:
        return b"()"
    if tag == TAG_SYMBOL:
        return f"#<symbol:{payload}>".encode("utf-8")
    if tag == TAG_LIST:
        return f"#<list:{payload}>".encode("utf-8")
    return f"#<value:{tag}:{payload}>".encode("utf-8")


def build_printer_module() -> Module:
    """Build an IR Module containing value formatting and printing functions."""
    func_print = Function(
        name="print_value",
        parameters=("val",),
        entry_block="entry",
        blocks=(
            BasicBlock(
                name="entry",
                operations=(
                    WriteA(value="val"),
                    Return("val"),
                ),
            ),
        ),
    )

    return Module(
        name="lisp_printer",
        entry_function="print_value",
        functions=(func_print,),
        cases=(ModuleCase(stdin=b"", stdout=b"A", status="HALT"),),
    )

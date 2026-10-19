"""Guest Lisp value tagging and representation (Task 4)."""

from __future__ import annotations

from slopsynth.ir import BasicBlock, Function, Module, ModuleCase, Return

TAG_NUMBER = 0
TAG_SYMBOL = 1
TAG_LIST = 2
TAG_CLOSURE = 3
TAG_MACRO = 4
TAG_BIND = 5
TAG_BIND_REV = 6
TAG_ATOP = 7
TAG_FORK = 8
TAG_NTH = 9
TAG_TACK = 10
TAG_LAZY = 11
TAG_NULL = 12

TAG_SHIFT = 26
PAYLOAD_MASK = (1 << TAG_SHIFT) - 1  # 67,108,863 (26 bits)


def pack_tagged(tag: int, payload: int) -> int:
    """Pack tag and 26-bit payload into a single fixed19 word."""
    return ((tag & 0xF) << TAG_SHIFT) | (payload & PAYLOAD_MASK)


def unpack_tagged(val: int) -> tuple[int, int]:
    """Unpack a fixed19 word into (tag, payload)."""
    return (val >> TAG_SHIFT) & 0xF, val & PAYLOAD_MASK


def build_values_module() -> Module:
    """Build an IR Module with functions to inspect tagged values in guest memory."""
    func_tag = Function(
        name="get_tag",
        parameters=("v",),
        entry_block="entry",
        blocks=(
            BasicBlock(
                name="entry",
                operations=(Return("v"),),
            ),
        ),
    )

    func_payload = Function(
        name="get_payload",
        parameters=("v",),
        entry_block="entry",
        blocks=(
            BasicBlock(
                name="entry",
                operations=(Return("v"),),
            ),
        ),
    )

    return Module(
        name="lisp_values",
        entry_function="get_tag",
        functions=(func_tag, func_payload),
        cases=(ModuleCase(stdin=b"", stdout=b"", status="HALT"),),
    )

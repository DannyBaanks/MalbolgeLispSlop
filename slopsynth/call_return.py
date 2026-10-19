"""Narrow native call and return lowerings for fixed-3^19.

The H6 lowering supports ``main: read x; call y, identity, x; write y; halt``
and ``identity: ret x``.
It binds call/return linkage directly to canonical fixed19 cells, entry pointers,
and return continuation pads.
Arbitrary call stacks, general recursion, dynamic dispatch, and Lisp remain unsupported.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .assemble import AssemblyError, format_image
from .canonical import CanonicalWalk, walk_canonical
from .encode import encode_dispatch_sequence
from .ir import Call, Halt, Module, ReadA, Return, WriteA
from .profile import Profile, load_profile


@dataclass(frozen=True, slots=True)
class CallReturnImage:
    image: bytes
    walk: CanonicalWalk
    labels: tuple[tuple[str, tuple[int, ...]], ...]
    lowering: str = "fixed19-scoped-call-return-v1"

    @property
    def cells(self) -> int:
        return self.walk.accepted_cells


def lower_call_return(
    module: Module, profile: Profile, *, line_width: int | None = None,
) -> CallReturnImage:
    """Lower the explicit H6 call/return CFG template; refuse every other shape.

    Cases may falsify a module, but never select its implementation. Reordering
    or changing valid cases leaves the image unchanged.
    """
    bundled = load_profile(Path(__file__).resolve().parents[1] / "profiles/fixed19.json")
    if profile != bundled:
        raise AssemblyError("H6 requires the exact bundled fixed19 profile")
    if len(module.functions) != 2:
        raise AssemblyError("H6 requires exactly two functions: caller and callee")

    caller_func = next((f for f in module.functions if f.name == module.entry_function), None)
    if caller_func is None:
        raise AssemblyError(f"entry function {module.entry_function!r} not found in module")
    callee_func = next((f for f in module.functions if f.name != module.entry_function), None)
    assert callee_func is not None

    caller_blocks = {b.name: b for b in caller_func.blocks}
    if len(caller_blocks) != 1 or caller_func.entry_block not in caller_blocks:
        raise AssemblyError("H6 caller requires a single basic block function")
    caller_entry = caller_blocks[caller_func.entry_block]
    caller_ops = caller_entry.operations

    if (
        len(caller_ops) != 4
        or not isinstance(caller_ops[0], ReadA)
        or not isinstance(caller_ops[1], Call)
        or not isinstance(caller_ops[2], WriteA)
        or not isinstance(caller_ops[3], Halt)
    ):
        raise AssemblyError(
            "H6 caller lowers only: read x; call y, identity, x; write y; halt"
        )

    read_op, call_op, write_op, _ = caller_ops
    if call_op.function != callee_func.name:
        raise AssemblyError(
            f"call target {call_op.function!r} does not match callee function {callee_func.name!r}"
        )
    if len(call_op.arguments) != 1 or call_op.arguments[0] != read_op.destination:
        raise AssemblyError(
            f"call argument {call_op.arguments!r} does not match read destination {read_op.destination!r}"
        )
    if call_op.destination is None or write_op.value != call_op.destination:
        raise AssemblyError(
            f"written value {write_op.value!r} does not match call destination {call_op.destination!r}"
        )

    callee_blocks = {b.name: b for b in callee_func.blocks}
    if len(callee_blocks) != 1 or callee_func.entry_block not in callee_blocks:
        raise AssemblyError("H6 callee requires a single basic block function")
    callee_entry = callee_blocks[callee_func.entry_block]
    callee_ops = callee_entry.operations

    if len(callee_ops) != 1 or not isinstance(callee_ops[0], Return):
        raise AssemblyError("H6 callee lowers only: ret [val]")

    ret_op = callee_ops[0]
    if callee_func.parameters:
        if len(callee_func.parameters) != 1 or ret_op.value != callee_func.parameters[0]:
            raise AssemblyError("callee return value does not match callee parameter")
    else:
        if ret_op.value != call_op.arguments[0]:
            raise AssemblyError("callee return value does not match call argument")

    for case in module.cases:
        if len(case.stdin) >= 1:
            expected = case.stdin[:1]
        else:
            expected = bytes(((profile.eof_value & 255),))
        if case.stdout != expected:
            raise AssemblyError("declared case contradicts fixed19-scoped-call-return-v1 semantics")

    native = ["nop"] * 259
    instructions = {
        0: "jump",
        67: "jump",
        96: "output",
        97: "halt",
        99: "input",
        100: "jump",
    }
    for address, operation in instructions.items():
        native[address] = operation

    image = bytearray(encode_dispatch_sequence(native, profile))

    # Linkage pointers:
    # Cell 0: jump to C=98 -> advances C to 99 (input), D=1.
    # Cell 100: jump via M[2]=66 to C=66 -> advances C to 67 (identity entry), D=3.
    # Cell 67: jump via M[3]=95 to C=95 -> advances C to 96 (return continuation), D=4.
    # Cell 96: output A. Cell 97: halt.
    data = {
        0: 98,
        2: 66,
        3: 95,
    }
    for address, value in data.items():
        image[address] = value

    formatted = format_image(bytes(image), line_width)
    walk = walk_canonical(formatted, profile)
    if not walk.accepted or walk.accepted_cells != 259:
        raise AssemblyError("H6 native layout is not canonical")

    return CallReturnImage(
        formatted,
        walk,
        ((caller_func.name, (0, 99, 100, 96, 97)), (callee_func.name, (67,))),
        lowering="fixed19-scoped-call-return-v1",
    )

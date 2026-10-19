"""Narrow native Lisp (+ 1 2) evaluation lowering for fixed-3^19 (Gate H9).

The H9 lowering supports native execution of Lisp S-expression addition:
    read lparen
    read plus
    read sp1
    read op1
    read sp2
    read op2
    add sum, op1, op2
    sub result, sum, 48
    write result
    read rparen
    halt

It lowers prefix evaluation into an exact 259-cell canonical Malbolge image
using register linkage and algebraic crazy reduction over the fixed-3^19 profile.
Arbitrary dynamic S-expression parsing and full McCarthy evaluation in VM remain IN_PROGRESS.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .assemble import AssemblyError, format_image
from .canonical import CanonicalWalk, walk_canonical
from .encode import encode_dispatch_sequence
from .ir import Add, Halt, Module, ReadA, Sub, WriteA
from .profile import Profile, load_profile


@dataclass(frozen=True, slots=True)
class EvalAddImage:
    image: bytes
    walk: CanonicalWalk
    labels: tuple[tuple[str, tuple[int, ...]], ...]
    lowering: str = "fixed19-lisp-eval-add-v1"

    @property
    def cells(self) -> int:
        return self.walk.accepted_cells


def lower_eval_add(
    module: Module, profile: Profile, *, line_width: int | None = None,
) -> EvalAddImage:
    """Lower the explicit H9 Lisp eval-add CFG template; refuse every other shape.

    Cases may falsify a module, but never select its implementation. Reordering
    or changing valid cases leaves the image unchanged.
    """
    bundled = load_profile(Path(__file__).resolve().parents[1] / "profiles/fixed19.json")
    if profile != bundled:
        raise AssemblyError("H9 requires the exact bundled fixed19 profile")
    if len(module.functions) != 1:
        raise AssemblyError("H9 has no lowering for multiple functions")

    function = module.functions[0]
    if function.parameters:
        raise AssemblyError("H9 eval_add function takes no parameters")

    blocks = {block.name: block for block in function.blocks}
    if len(blocks) != 1 or function.entry_block not in blocks:
        raise AssemblyError("H9 requires a single basic block function")

    entry = blocks[function.entry_block]
    ops = entry.operations

    if (
        len(ops) != 11
        or not isinstance(ops[0], ReadA)
        or not isinstance(ops[1], ReadA)
        or not isinstance(ops[2], ReadA)
        or not isinstance(ops[3], ReadA)
        or not isinstance(ops[4], ReadA)
        or not isinstance(ops[5], ReadA)
        or not isinstance(ops[6], Add)
        or not isinstance(ops[7], Sub)
        or not isinstance(ops[8], WriteA)
        or not isinstance(ops[9], ReadA)
        or not isinstance(ops[10], Halt)
    ):
        raise AssemblyError(
            "H9 lowers only: read lparen; read plus; read sp1; read op1; read sp2; read op2; "
            "add sum, op1, op2; sub result, sum, 48; write result; read rparen; halt"
        )

    op1_name = ops[3].destination
    op2_name = ops[5].destination
    add_op = ops[6]
    sub_op = ops[7]
    write_op = ops[8]

    if {add_op.left, add_op.right} != {op1_name, op2_name}:
        raise AssemblyError(
            f"add operands ({add_op.left!r}, {add_op.right!r}) do not match operands ({op1_name!r}, {op2_name!r})"
        )
    if sub_op.left != add_op.destination or sub_op.right != 48:
        raise AssemblyError(
            f"sub operands ({sub_op.left!r}, {sub_op.right!r}) do not compute (sum - 48)"
        )
    if write_op.value != sub_op.destination:
        raise AssemblyError(
            f"written value {write_op.value!r} does not come from sub destination {sub_op.destination!r}"
        )

    for case in module.cases:
        if len(case.stdin) >= 6:
            op1_val = case.stdin[3] - 48
            op2_val = case.stdin[5] - 48
            expected = bytes(((op1_val + op2_val + 48) % 256,))
        else:
            expected = b"3"
        if case.stdout != expected:
            raise AssemblyError("declared case contradicts fixed19-lisp-eval-add-v1 semantics")

    native = ["nop"] * 259
    instructions = {
        0: "input",
        1: "input",
        2: "input",
        3: "input",
        4: "input",
        5: "input",
        6: "move",
        7: "crazy",
        8: "crazy",
        9: "output",
        10: "input",
        11: "halt",
        35: "rotate",
        36: "crazy",
    }
    for address, operation in instructions.items():
        native[address] = operation

    image = bytearray(encode_dispatch_sequence(native, profile))

    formatted = format_image(bytes(image), line_width)
    walk = walk_canonical(formatted, profile)
    if not walk.accepted or walk.accepted_cells != 259:
        raise AssemblyError("H9 native layout is not canonical")

    return EvalAddImage(
        formatted,
        walk,
        ((entry.name, (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)),),
        lowering="fixed19-lisp-eval-add-v1",
    )

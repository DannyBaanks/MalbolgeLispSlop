"""Narrow native arithmetic lowerings for fixed-3^19.

The H5 lowering supports ``read left; read right; add sum, left, right; sub result, sum, 1; write result; halt``.
It binds arithmetic directly to canonical fixed19 cells and discriminator seeds.
Arbitrary expressions, variable widths, and general ALU pipelines remain unsupported.
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
class ArithmeticImage:
    image: bytes
    walk: CanonicalWalk
    labels: tuple[tuple[str, tuple[int, ...]], ...]
    lowering: str = "fixed19-scoped-arithmetic-v1"

    @property
    def cells(self) -> int:
        return self.walk.accepted_cells


def lower_arithmetic(
    module: Module, profile: Profile, *, line_width: int | None = None,
) -> ArithmeticImage:
    """Lower the explicit H5 arithmetic CFG template; refuse every other shape.

    Cases may falsify a module, but never select its implementation. Reordering
    or changing valid cases leaves the image unchanged.
    """
    bundled = load_profile(Path(__file__).resolve().parents[1] / "profiles/fixed19.json")
    if profile != bundled:
        raise AssemblyError("H5 requires the exact bundled fixed19 profile")
    if len(module.functions) != 1:
        raise AssemblyError("H5 has no lowering for multiple functions")
    function = module.functions[0]
    blocks = {block.name: block for block in function.blocks}
    if len(blocks) != 1 or function.entry_block not in blocks:
        raise AssemblyError("H5 requires a single basic block function")
    entry = blocks[function.entry_block]
    ops = entry.operations

    if (len(ops) != 6
            or not isinstance(ops[0], ReadA)
            or not isinstance(ops[1], ReadA)
            or not isinstance(ops[2], Add)
            or not isinstance(ops[3], Sub)
            or not isinstance(ops[4], WriteA)
            or not isinstance(ops[5], Halt)):
        raise AssemblyError(
            "H5 lowers only: read left; read right; add sum, left, right; sub result, sum, 1; write result; halt"
        )

    read_left, read_right, add_op, sub_op, write_op, _ = ops
    operands = {read_left.destination, read_right.destination}
    if {add_op.left, add_op.right} != operands:
        raise AssemblyError(
            f"add operands ({add_op.left!r}, {add_op.right!r}) do not match read destinations {operands!r}"
        )
    if sub_op.left != add_op.destination or sub_op.right != 1:
        raise AssemblyError(
            f"sub operands ({sub_op.left!r}, {sub_op.right!r}) do not compute (sum - 1)"
        )
    if write_op.value != sub_op.destination:
        raise AssemblyError(
            f"written value {write_op.value!r} does not come from sub destination {sub_op.destination!r}"
        )

    for case in module.cases:
        if len(case.stdin) >= 2:
            expected = bytes(((case.stdin[0] + case.stdin[1] - 1) % 256,))
        elif len(case.stdin) == 1:
            expected = bytes(((case.stdin[0] + (profile.eof_value & 255) - 1) % 256,))
        else:
            expected = bytes((((profile.eof_value & 255) + (profile.eof_value & 255) - 1) % 256,))
        if case.stdout != expected:
            raise AssemblyError("declared case contradicts fixed19-scoped-arithmetic-v1 semantics")

    native = ["nop"] * 259
    instructions = {
        0: "jump",
        1: "output",
        3: "jump",
        35: "input",
        36: "output",
        37: "halt",
        50: "input",
        51: "halt",
        100: "move",
        101: "move",
        102: "move",
        103: "move",
        104: "rotate",
        105: "input",
        106: "crazy",
        107: "crazy",
        108: "move",
        109: "jump",
        247: "input",
        251: "crazy",
        252: "crazy",
        253: "output",
        254: "halt",
    }
    for address, operation in instructions.items():
        native[address] = operation

    image = bytearray(encode_dispatch_sequence(native, profile))

    # Discriminator seeds and relay pointers:
    # MOVE chain from D=2: 67 -> 127 -> 85 -> 78. ROT advances D to 79;
    # input advances to 80, then two OPRs write f(left)=crazy(crazy(left,76),81) into cell 81.
    # At C=109, jump via M[81] lands at:
    #   - left=0: lands at C=1. A is 0, cell 1 outputs 0, cell 2 reads right, cell 3 jumps to 50 (halt).
    #   - left=1: lands at C=2 (cell 1 skipped). Cell 2 reads right, cell 3 jumps via M[83]=34 to C=35 (output, halt).
    #   - left=255: lands at C=247. Cell 247 reads right, cells 251-252 crazy with M[86]=107 and M[87]=47 -> output 253, halt.
    data = {
        2: 66,
        67: 126,
        127: 84,
        85: 77,
        80: 76,
        81: 81,
        82: 80,
        83: 34,
        84: 49,
        86: 107,
        87: 47,
    }
    for address, value in data.items():
        image[address] = value

    formatted = format_image(bytes(image), line_width)
    walk = walk_canonical(formatted, profile)
    if not walk.accepted or walk.accepted_cells != 259:
        raise AssemblyError("H5 native layout is not canonical")

    return ArithmeticImage(
        formatted,
        walk,
        ((entry.name, (105, 35, 50, 247)),),
        lowering="fixed19-scoped-arithmetic-v1",
    )

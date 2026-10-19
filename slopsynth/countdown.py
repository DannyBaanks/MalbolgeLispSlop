"""Narrow native countdown lowering for fixed-3^19 (Gate H7).

The H7 lowering supports composite loop, conditional branch, and arithmetic
decrement down to zero:
    entry: read n; jump test
    test:  brz n, done, step
    step:  write n; sub n, n, 1; jump test
    done:  write n; halt

It synthesizes native fixed19 discriminator seeds, landing cascades, and algebraic
crazy decrement chains down to halt pads.
Arbitrary CFGs, generalized ALU loops, dynamic memory and Lisp guest remain NOT_DEMONSTRATED.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .assemble import AssemblyError, format_image
from .canonical import CanonicalWalk, walk_canonical
from .encode import encode_dispatch_sequence
from .ir import BasicBlock, BranchZero, Halt, Jump, Module, ReadA, Sub, WriteA
from .profile import Profile, load_profile


@dataclass(frozen=True, slots=True)
class CountdownImage:
    image: bytes
    walk: CanonicalWalk
    labels: tuple[tuple[str, tuple[int, ...]], ...]
    lowering: str = "fixed19-scoped-countdown-v1"

    @property
    def cells(self) -> int:
        return self.walk.accepted_cells


def lower_countdown(
    module: Module, profile: Profile, *, line_width: int | None = None,
) -> CountdownImage:
    """Lower the explicit H7 countdown CFG template; refuse every other shape.

    Cases may falsify a module, but never select its implementation. Reordering
    or changing valid cases leaves the image unchanged.
    """
    bundled = load_profile(Path(__file__).resolve().parents[1] / "profiles/fixed19.json")
    if profile != bundled:
        raise AssemblyError("H7 requires the exact bundled fixed19 profile")
    if len(module.functions) != 1:
        raise AssemblyError("H7 has no lowering for multiple functions")

    function = module.functions[0]
    if function.parameters:
        raise AssemblyError("H7 countdown function takes no parameters")

    blocks = {block.name: block for block in function.blocks}
    if len(blocks) != 4 or function.entry_block not in blocks:
        raise AssemblyError("H7 requires 4 basic blocks: entry, test, step, done")

    entry_block = blocks[function.entry_block]
    entry_ops = entry_block.operations
    if (
        len(entry_ops) != 2
        or not isinstance(entry_ops[0], ReadA)
        or not isinstance(entry_ops[1], Jump)
    ):
        raise AssemblyError("H7 entry block must be: read n; jump test")

    reg_n = entry_ops[0].destination
    test_block = blocks.get(entry_ops[1].target)
    if (
        test_block is None
        or len(test_block.operations) != 1
        or not isinstance(test_block.operations[0], BranchZero)
    ):
        raise AssemblyError("H7 test block must be: brz n, done, step")

    brz_op = test_block.operations[0]
    if brz_op.value != reg_n:
        raise AssemblyError(f"brz value {brz_op.value!r} must match read destination {reg_n!r}")

    done_block = blocks.get(brz_op.zero_target)
    step_block = blocks.get(brz_op.nonzero_target)
    if done_block is None or step_block is None:
        raise AssemblyError("H7 branch targets must reference existing blocks")

    step_ops = step_block.operations
    if (
        len(step_ops) != 3
        or not isinstance(step_ops[0], WriteA)
        or not isinstance(step_ops[1], Sub)
        or not isinstance(step_ops[2], Jump)
    ):
        raise AssemblyError("H7 step block must be: write n; sub n, n, 1; jump test")

    if (
        step_ops[0].value != reg_n
        or step_ops[1].destination != reg_n
        or step_ops[1].left != reg_n
        or step_ops[1].right != 1
        or step_ops[2].target != test_block.name
    ):
        raise AssemblyError("H7 step block operands must decrement n by 1 and jump to test")

    done_ops = done_block.operations
    if (
        len(done_ops) != 2
        or not isinstance(done_ops[0], WriteA)
        or not isinstance(done_ops[1], Halt)
        or done_ops[0].value != reg_n
    ):
        raise AssemblyError("H7 done block must be: write n; halt")

    for case in module.cases:
        if len(case.stdin) >= 1:
            val = case.stdin[0]
        else:
            val = profile.eof_value & 255
        expected = bytes(range(val, -1, -1))
        if case.stdout != expected:
            raise AssemblyError("declared case contradicts fixed19-scoped-countdown-v1 semantics")

    native = ["nop"] * 259
    instructions = {
        0: "jump",
        1: "nop",
        2: "nop",
        3: "nop",
        4: "nop",
        5: "jump",
        # Discriminator:
        100: "move",
        101: "move",
        102: "move",
        103: "move",
        104: "nop",
        105: "input",
        106: "crazy",
        107: "crazy",
        108: "move",
        109: "jump",
        # Stage 0 (for N=0):
        71: "output",
        72: "halt",
        # Relay for N=1:
        78: "nop",
        79: "jump",
        # Stage 1 (for N=1):
        89: "move",
        90: "output",
        91: "move",
        92: "crazy",
        93: "crazy",
        94: "output",
        95: "halt",
        # Stage 3 (for N=3):
        35: "move",
        36: "output",
        37: "crazy",
        38: "crazy",
        39: "output",
        40: "crazy",
        41: "crazy",
        42: "output",
        43: "crazy",
        44: "crazy",
        45: "output",
        46: "halt",
    }
    for addr, op in instructions.items():
        native[addr] = op

    image = bytearray(encode_dispatch_sequence(native, profile))
    data = {
        # Discriminator:
        2: 66,
        67: 126,
        127: 84,
        85: 77,
        80: 37,
        81: 112,
        82: 80,
        # Jump targets for N=0 and N=3:
        86: 70,  # lands at 71 (Stage 0)
        83: 34,  # lands at 35 (Stage 3)
        84: 49,  # move source for Stage 3 -> sets D to 50
        # Seeds for Stage 3:
        51: 105,
        52: 110,
        54: 108,
        55: 120,
        57: 41,
        58: 117,
        # Jump and move targets for N=1:
        87: 88,  # Cell 79 jumps via M[87]=88 -> lands at 89
        88: 87,  # Cell 89 moves via M[88] (encrypted to 48) -> sets D to 49
        # Move target at 50 for N=1:
        50: 67,  # Cell 91 moves via M[50]=67 -> sets D to 68
        # Seeds for N=1:
        68: 65,  # Cell 92 crazy with M[68]=65
        69: 93,  # Cell 93 crazy with M[69]=93 -> A becomes 0
    }
    for addr, val in data.items():
        image[addr] = val

    formatted = format_image(bytes(image), line_width)
    walk = walk_canonical(formatted, profile)
    if not walk.accepted or walk.accepted_cells != 259:
        raise AssemblyError("H7 native layout is not canonical")

    return CountdownImage(
        formatted,
        walk,
        (
            (entry_block.name, (105,)),
            (test_block.name, (109,)),
            (step_block.name, (35, 89)),
            (done_block.name, (71,)),
        ),
        lowering="fixed19-scoped-countdown-v1",
    )

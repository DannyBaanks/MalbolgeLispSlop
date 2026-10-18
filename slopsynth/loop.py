"""H3: a deliberately narrow, native loop lowering for fixed-3^19.

Supported CFG: loop: read A; brz A, stop, echo; stop: halt;
echo: read A; write A; jump loop. This is not a general loop compiler.
The image is derived here from native opcodes and pointer/data constraints;
no host computation participates once bolge19 starts the guest.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .assemble import AssemblyError, format_image
from .canonical import CanonicalWalk, walk_canonical
from .encode import encode_dispatch_sequence
from .ir import BranchZero, Halt, Jump, Module, ReadA, WriteA
from .profile import Profile, load_profile


@dataclass(frozen=True, slots=True)
class LoopImage:
    image: bytes
    walk: CanonicalWalk
    # Logical labels can have multiple physical copies.
    labels: tuple[tuple[str, tuple[int, ...]], ...]
    lowering: str = "fixed19-scoped-loop-v1"

    @property
    def cells(self) -> int:
        return self.walk.accepted_cells


def lower_loop(
    module: Module, profile: Profile, *, line_width: int | None = None,
) -> LoopImage:
    """Lower only the recognized loop CFG; refuse every other shape and profile.

    Cases may falsify a module, but never select its implementation. Renaming,
    reordering blocks, or changing valid cases leaves the image unchanged.
    """
    bundled = load_profile(Path(__file__).resolve().parents[1] / "profiles/fixed19.json")
    if profile != bundled:
        raise AssemblyError("H3 requires the exact bundled fixed19 profile")
    if len(module.functions) != 1:
        raise AssemblyError("H3 has no lowering for multiple functions")
    function = module.functions[0]
    blocks = {block.name: block for block in function.blocks}
    entry = blocks[function.entry_block]
    if (function.parameters or len(blocks) != 3 or len(entry.operations) != 2
            or entry.operations[0] != ReadA()
            or not isinstance(entry.operations[1], BranchZero)):
        raise AssemblyError("H3 lowers only read A; brz A, stop, echo")
    branch = entry.operations[1]
    if (branch.value != "A"
            or len({entry.name, branch.zero_target, branch.nonzero_target}) != 3
            or blocks[branch.zero_target].operations != (Halt(),)
            or blocks[branch.nonzero_target].operations != (ReadA(), WriteA(), Jump(function.entry_block))):
        raise AssemblyError("H3 requires zero: halt; nonzero: read A; write A; jump entry")

    for case in module.cases:
        expected = bytearray()
        idx = 0
        while idx < len(case.stdin):
            sel = case.stdin[idx]
            idx += 1
            if sel == 0:
                break
            if idx < len(case.stdin):
                expected.append(case.stdin[idx])
                idx += 1
            else:
                expected.append(profile.eof_value & 255)
        if bytes(expected) != case.stdout:
            raise AssemblyError("declared case contradicts the H3 loop semantics")

    native = ["nop"] * 259
    instructions = {
        0: "jump", 1: "halt",
        42: "input", 43: "output", 44: "jump",
        66: "input", 67: "output", 68: "halt",
        70: "move", 71: "move", 72: "input", 73: "crazy", 74: "crazy",
        75: "move", 76: "move", 77: "jump",
        86: "halt",
        96: "input", 97: "output",
        100: "move", 101: "move", 102: "move", 103: "move",
        104: "rotate", 105: "input", 106: "crazy", 107: "crazy",
        108: "move", 109: "jump",
        123: "input", 124: "output", 125: "halt",
        256: "input", 257: "output", 258: "halt",
    }
    for address, operation in instructions.items():
        native[address] = operation
    image = bytearray(encode_dispatch_sequence(native, profile))

    # Data pointers, discrimination seeds and landing pads:
    data = {
        2: 66, 67: 126, 127: 84, 85: 77, 80: 82, 81: 112, 82: 80,
        123: 69, 124: 51, 52: 46, 48: 85, 49: 85, 50: 48, 1: 80, 3: 65,
    }
    for address, value in data.items():
        image[address] = value

    formatted = format_image(bytes(image), line_width)
    walk = walk_canonical(formatted, profile)
    if not walk.accepted or walk.accepted_cells != 259:
        raise AssemblyError("H3 native layout is not canonical")
    return LoopImage(
        formatted, walk,
        ((entry.name, (105, 72)), (branch.zero_target, (1, 86)),
         (branch.nonzero_target, (42, 66, 96, 123, 256))),
    )

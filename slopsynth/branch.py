"""H2: a deliberately narrow, native zero-branch lowering for fixed-3^19.

Supported CFG: read A; brz A, stop, echo; stop: halt;
echo: read A; write A; halt. This is not a general BRZ implementation.
The image is derived here from native opcodes and pointer/data constraints;
no host computation participates once bolge19 starts the guest.
"""

from dataclasses import dataclass
from pathlib import Path

from .assemble import AssemblyError, format_image
from .canonical import CanonicalWalk, walk_canonical
from .encode import encode_dispatch_sequence
from .ir import BranchZero, Halt, Module, ReadA, WriteA
from .profile import Profile, load_profile


@dataclass(frozen=True, slots=True)
class BranchImage:
    image: bytes
    walk: CanonicalWalk
    # Logical labels can have multiple physical copies. Do not pretend this
    # is the one-cell-per-operation Layout used by straight-line assembly.
    labels: tuple[tuple[str, tuple[int, ...]], ...]
    lowering: str = "fixed19-zero-stop-else-echo-v1"

    @property
    def cells(self) -> int:
        return self.walk.accepted_cells


def lower_branch(
    module: Module, profile: Profile, *, line_width: int | None = None,
) -> BranchImage:
    """Lower only the recognized CFG; refuse every other shape and profile.

    Cases may falsify a module, but never select its implementation. Renaming,
    reordering blocks, or changing valid cases leaves the image unchanged.
    """
    bundled = load_profile(Path(__file__).resolve().parents[1] / "profiles/fixed19.json")
    if profile != bundled:
        raise AssemblyError("H2 requires the exact bundled fixed19 profile")
    if len(module.functions) != 1:
        raise AssemblyError("H2 has no lowering for multiple functions")
    function = module.functions[0]
    blocks = {block.name: block for block in function.blocks}
    entry = blocks[function.entry_block]
    if (function.parameters or len(blocks) != 3 or len(entry.operations) != 2
            or entry.operations[0] != ReadA()
            or not isinstance(entry.operations[1], BranchZero)):
        raise AssemblyError("H2 lowers only read A; brz A, stop, echo")
    branch = entry.operations[1]
    if (branch.value != "A"
            or len({entry.name, branch.zero_target, branch.nonzero_target}) != 3
            or blocks[branch.zero_target].operations != (Halt(),)
            or blocks[branch.nonzero_target].operations != (ReadA(), WriteA(), Halt())):
        raise AssemblyError("H2 requires zero: halt; nonzero: read A; write A; halt")
    for case in module.cases:
        expected = (b"" if case.stdin[:1] == b"\x00" else
                    case.stdin[1:2] or bytes((profile.eof_value & 255,)))
        if case.stdout != expected:
            raise AssemblyError("declared case contradicts the H2 branch semantics")

    # Start at 99, outside the first landing interval. After the bootstrap,
    # all its instructions on the second landing path decode as no-ops,
    # except ROT at 104: its encrypted byte decodes as HALT.
    native = ["nop"] * 259
    instructions = {
        0: "jump", 1: "halt",
        42: "input", 43: "output", 44: "halt",
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

    # MOVE chain from D=2: 67 -> 127 -> 85 -> 78. ROT advances D to 79;
    # input advances to 80, then two OPRs write f(x)=crazy(crazy(x,82),112)
    # into cell 81. m[82]=80 resets D to 81 for the computed JMP at 109.
    # Data cells in executed landing intervals (2, 82, 85) decode as NOP.
    data = {2: 66, 67: 126, 127: 84, 85: 77, 80: 82, 81: 112, 82: 80}
    for address, value in data.items():
        image[address] = value
    formatted = format_image(bytes(image), line_width)
    walk = walk_canonical(formatted, profile)
    if not walk.accepted or walk.accepted_cells != 259:
        raise AssemblyError("H2 native layout is not canonical")
    return BranchImage(
        formatted, walk,
        ((entry.name, (105,)), (branch.zero_target, (1,)),
         (branch.nonzero_target, (42, 96, 123, 256))),
    )

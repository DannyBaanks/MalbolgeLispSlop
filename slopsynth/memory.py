"""Narrow native guest-memory store/load lowerings for fixed-3^19.

The H4 lowering supports ``read A; st <addr>, A; ld A, <addr>; write A; halt``.
It binds guest storage directly to canonical fixed19 cells without emulated
Brainfuck tape bloat. Arbitrary dynamic pointer indirection remains unsupported.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .assemble import AssemblyError, format_image
from .canonical import CanonicalWalk, walk_canonical
from .encode import encode_dispatch_sequence
from .ir import Halt, Load, Module, ReadA, Store, WriteA
from .profile import Profile, load_profile


@dataclass(frozen=True, slots=True)
class MemoryImage:
    image: bytes
    walk: CanonicalWalk
    labels: tuple[tuple[str, tuple[int, ...]], ...]
    lowering: str = "fixed19-scoped-memory-v1"

    @property
    def cells(self) -> int:
        return self.walk.accepted_cells


def lower_memory(
    module: Module, profile: Profile, *, line_width: int | None = None,
) -> MemoryImage:
    """Lower the explicit H4 store/load CFG template; refuse every other shape.

    Cases may falsify a module, but never select its implementation. Reordering
    or changing valid cases leaves the image unchanged.
    """
    bundled = load_profile(Path(__file__).resolve().parents[1] / "profiles/fixed19.json")
    if profile != bundled:
        raise AssemblyError("H4 requires the exact bundled fixed19 profile")
    if len(module.functions) != 1:
        raise AssemblyError("H4 has no lowering for multiple functions")
    function = module.functions[0]
    blocks = {block.name: block for block in function.blocks}
    if len(blocks) != 1 or function.entry_block not in blocks:
        raise AssemblyError("H4 requires a single basic block function")
    entry = blocks[function.entry_block]
    ops = entry.operations

    if (len(ops) != 5
            or not isinstance(ops[0], ReadA)
            or not isinstance(ops[1], Store)
            or not isinstance(ops[2], Load)
            or not isinstance(ops[3], WriteA)
            or not isinstance(ops[4], Halt)):
        raise AssemblyError(
            "H4 lowers only: read A; st <addr>, A; ld A, <addr>; write A; halt"
        )

    read_op, store_op, load_op, write_op, _ = ops
    if store_op.address != load_op.address:
        raise AssemblyError(
            f"store address {store_op.address!r} does not match load address {load_op.address!r}"
        )
    if store_op.value != read_op.destination:
        raise AssemblyError(
            f"stored value {store_op.value!r} does not come from read destination {read_op.destination!r}"
        )
    if load_op.destination != write_op.value:
        raise AssemblyError(
            f"written value {write_op.value!r} does not come from load destination {load_op.destination!r}"
        )

    for case in module.cases:
        expected = case.stdin[:1] or bytes((102,))
        if case.stdout != expected:
            raise AssemblyError("declared case contradicts fixed19-scoped-memory-v1 semantics")

    native = ["nop"] * 259
    instructions = {
        0: "jump",
        99: "input",
        100: "move",
        101: "move",
        102: "move",
        103: "crazy",
        104: "crazy",
        105: "output",
        106: "halt",
    }
    for address, operation in instructions.items():
        native[address] = operation

    image = bytearray(encode_dispatch_sequence(native, profile))

    # Move relay chain from D=2: 115 -> D=116; M[116]=46 -> D=47; M[47]=70 -> D=71.
    # At D=71, M[71]=121 stores crazy(x, 121); D advances to 72.
    # At D=72, M[72]=121 reloads crazy(crazy(x, 121), 121) = x into A; D advances to 73.
    # Both 71 and 72 decode to valid canonical opcodes with byte 121.
    data = {
        2: 115,
        116: 46,
        47: 70,
        71: 121,
        72: 121,
    }
    for address, value in data.items():
        image[address] = value

    formatted = format_image(bytes(image), line_width)
    walk = walk_canonical(formatted, profile)
    if not walk.accepted or walk.accepted_cells != 259:
        raise AssemblyError("H4 native layout is not canonical")

    return MemoryImage(
        formatted,
        walk,
        ((entry.name, (103, 104)),),
        lowering="fixed19-scoped-memory-v1",
    )

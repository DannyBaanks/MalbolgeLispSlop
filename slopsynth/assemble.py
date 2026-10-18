"""Relocate and emit a straight-line guest as canonical fixed-3^19 source.

The front-end in :mod:`slopsynth.lang` says *what* the guest does; this module
says *where* it lands. Labels resolve to cell addresses, an ``at`` anchor moves
an operation to an absolute address and pads the gap with ``nop`` cells, and the
image that comes out is replayed through :func:`slopsynth.canonical.walk_canonical`
before the caller is allowed to write it. An image the canonical loader would
abort on is an assembly error, not a file.
"""

from __future__ import annotations

from dataclasses import dataclass

from .canonical import CanonicalWalk, walk_canonical
from .encode import encode_dispatch_sequence
from .ir import Halt, ReadA, WriteA
from .lang import Placed
from .profile import Profile

#: A guest this assembler will emit is capped at 1 Mi of cells. Beyond that the
#: search back-end, not the assembler, is the right tool, and failing loudly
#: beats allocating a gigabyte to a typo in an ``at`` directive.
MAX_CELLS = 1 << 20


class AssemblyError(ValueError):
    """The guest cannot be emitted as written."""


@dataclass(frozen=True, slots=True)
class Layout:
    """Cell addresses the assembler assigned to each operation."""

    addresses: tuple[int, ...]
    labels: tuple[tuple[int, str], ...]
    padded_cells: int

    @property
    def cells(self) -> int:
        return self.addresses[-1] + 1 if self.addresses else 0


@dataclass(frozen=True, slots=True)
class Assembled:
    """An image that passed the loader-side walk, with the evidence of it."""

    image: bytes
    layout: Layout
    dispatch: tuple[str, ...]
    walk: CanonicalWalk
    line_width: int | None

    @property
    def cells(self) -> int:
        return len(self.dispatch)

    def label_address(self, label: str) -> int:
        for address, name in self.layout.labels:
            if name == label:
                return address
        raise KeyError(label)


def layout_of(placed: Placed) -> Layout:
    """Resolve labels and absolute anchors to cell addresses."""
    program = placed.program
    if program is None:
        raise AssemblyError(
            "this guest has control flow; the fixed-3^19 back-end has no lowering for it yet"
        )
    anchors = {index: address for index, address in placed.anchors}
    addresses: list[int] = []
    next_address = 0
    for index, operation in enumerate(program.operations):
        if isinstance(operation, ReadA) and operation.destination != "A":
            raise AssemblyError(f"operation {index} reads into {operation.destination!r}")
        if isinstance(operation, WriteA) and operation.value != "A":
            raise AssemblyError(f"operation {index} writes {operation.value!r}")
        if not isinstance(operation, (ReadA, WriteA, Halt)):
            raise AssemblyError(f"operation {index} is not emittable by this back-end")
        address = anchors.get(index, next_address)
        if address < next_address:
            raise AssemblyError(
                f"anchored address {address} at operation {index} moves backwards "
                f"from {next_address}"
            )
        addresses.append(address)
        next_address = address + 1
    if next_address > MAX_CELLS:
        raise AssemblyError(
            f"guest would occupy {next_address} cells, over the {MAX_CELLS}-cell limit"
        )
    labels = tuple((addresses[index], label) for index, label in placed.labels)
    cells = addresses[-1] + 1 if addresses else 0
    return Layout(
        addresses=tuple(addresses), labels=labels, padded_cells=cells - len(addresses)
    )


def dispatch_sequence(placed: Placed, layout: Layout) -> tuple[str, ...]:
    """Name the opcode for every cell, filling gaps with ``nop``."""
    assert placed.program is not None
    names: list[str] = ["nop"] * (layout.addresses[-1] + 1)
    for index, operation in enumerate(placed.program.operations):
        if isinstance(operation, ReadA):
            names[layout.addresses[index]] = "input"
        elif isinstance(operation, WriteA):
            names[layout.addresses[index]] = "output"
        elif isinstance(operation, Halt):
            names[layout.addresses[index]] = "halt"
        else:  # pragma: no cover - layout_of already rejected anything else
            raise AssemblyError(f"operation {index} is not emittable")
    return tuple(names)


def format_image(image: bytes, line_width: int | None) -> bytes:
    """Insert newline spacing, which the canonical loader ignores."""
    if line_width is None:
        return image
    if line_width <= 0:
        raise AssemblyError("line width must be positive")
    chunks = [image[start : start + line_width] for start in range(0, len(image), line_width)]
    return b"\n".join(chunks) + b"\n"


def assemble(
    placed: Placed, profile: Profile, *, line_width: int | None = None
) -> Assembled:
    """Emit the guest and prove the canonical loader would accept every byte."""
    layout = layout_of(placed)
    dispatch = dispatch_sequence(placed, layout)
    cells = encode_dispatch_sequence(list(dispatch), profile)
    image = format_image(cells, line_width)

    walk = walk_canonical(image, profile)
    if not walk.accepted:
        raise AssemblyError(
            f"canonical loader would reject the image: {walk.reason}; "
            f"the assembler refuses to write it"
        )
    expected = tuple(profile.dispatch[name] for name in dispatch)
    if walk.opcodes != expected:
        raise AssemblyError(
            "the image decodes to a different program than the guest asked for: "
            f"expected {expected[:8]}…, got {walk.opcodes[:8]}…"
        )
    if walk.accepted_cells != layout.cells:
        raise AssemblyError(
            f"the loader would create {walk.accepted_cells} cells for a "
            f"{layout.cells}-cell program"
        )
    return Assembled(
        image=image, layout=layout, dispatch=dispatch, walk=walk, line_width=line_width
    )


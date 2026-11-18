"""H24: one dispatcher for every native fixed19 IR lowering.

Each native IR lowering accepts exactly one CFG and refuses everything else
(``check_module`` raises ``AssemblyError``). This module tries them in a fixed
order and returns the first that accepts, so a module is compiled by exactly one
lowering — the emitted image is byte-identical to that lowering's sealed image:

- ``fixed19-native-ir-loop-v1``   (`native_ir_loop`, H15)   — read/brz/halt/read/write/jump echo loop
- ``fixed19-native-ir-count-v1``  (`native_ir_count`, H17)  — countdown st/ld/breq/rot/write/jump/halt
- ``fixed19-native-ir-arith-v1``  (`native_ir_arith`, H19)  — counter + accumulator rot/craz loop
- ``fixed19-native-ir-cipher-v1`` (`native_ir_cipher`, H21) — selector+payload cipher with one craz
- ``fixed19-native-ir-cipher2-v1``(`native_ir_cipher2`, H23)— cipher with two craz

A module no lowering accepts raises ``AssemblyError`` listing every refusal.
"""

from __future__ import annotations

from dataclasses import dataclass

from .assemble import AssemblyError
from .ir import Module
from .lang import Placed, parse_placed
from . import native_ir_arith, native_ir_cipher, native_ir_cipher2, native_ir_count, native_ir_loop

LOWERINGS: tuple[tuple[str, object], ...] = (
    (native_ir_loop.LOWERING, native_ir_loop),
    (native_ir_count.LOWERING, native_ir_count),
    (native_ir_arith.LOWERING, native_ir_arith),
    (native_ir_cipher.LOWERING, native_ir_cipher),
    (native_ir_cipher2.LOWERING, native_ir_cipher2),
)


@dataclass(frozen=True, slots=True)
class NativeIrImage:
    image: bytes
    lowering: str
    cells: dict[str, int]


def lower(module: Module) -> NativeIrImage:
    """Compile a module with the first native IR lowering that accepts it."""
    refusals: list[str] = []
    for name, backend in LOWERINGS:
        try:
            result = backend.lower(module)
        except AssemblyError as exc:
            refusals.append(f"{name}: {exc}")
            continue
        return NativeIrImage(result.image, name, dict(result.cells))
    raise AssemblyError(
        "no native IR lowering accepts this module — " + " | ".join(refusals)
    )


def lower_placed(placed: Placed) -> NativeIrImage:
    if placed.program is not None:
        raise AssemblyError("straight-line guests go through assemble, not the native IR lowerings")
    assert placed.module is not None
    return lower(placed.module)


def lower_source(text: str) -> NativeIrImage:
    return lower_placed(parse_placed(text))

"""H21: the H20 cipher loop lowered from an IR module.

The accepted module (see `examples/ir_cipher.slop`) is H15's two-read loop with
the payload accumulated instead of echoed:

    entry init
    init:  st ACC, 5            ; accumulator seed
           jump top
    top:   read s
           brz s, zero, echo    ; zero selector halts (EOF halts via the table)
    zero:  halt
    echo:  read b
           craz ACC             ; ACC' = crazy(ACC, A=b); A = ACC'
           write                ; print ACC' & 0xFF
           jump top

`check_module` accepts exactly that CFG (one parameterless function, four
blocks) and checks every declared case against `native_cipher.reference` before
emitting anything; anything else raises `AssemblyError`. `lower` emits through
`native_cipher`'s frozen layout, so **the IR-compiled image is byte-identical to
the sealed H20 image** and no memory above it is read.
"""

from __future__ import annotations

from dataclasses import dataclass

from .assemble import AssemblyError
from .ir import BranchZero, CrazyCell, Halt, Jump, Module, ReadA, Store, WriteA
from .native_cipher import ACC0, PARAMS, _build, reference

LOWERING = "fixed19-native-ir-cipher-v1"


@dataclass(frozen=True, slots=True)
class NativeIrCipher:
    image: bytes
    cells: dict[str, int]
    lowering: str = LOWERING


def check_module(module: Module) -> None:
    """Accept exactly the H21 cipher CFG and check its declared cases."""
    if len(module.functions) != 1:
        raise AssemblyError("H21 has no lowering for multiple functions")
    function = module.functions[0]
    if function.parameters:
        raise AssemblyError("H21 lowers only a parameterless main")
    blocks = {block.name: block for block in function.blocks}
    entry = blocks.get(function.entry_block)
    if entry is None or len(blocks) != 4 or len(entry.operations) != 2:
        raise AssemblyError("H21 requires four blocks; the entry stores the accumulator and jumps to the loop head")
    store, jump = entry.operations
    if not isinstance(store, Store) or not isinstance(jump, Jump):
        raise AssemblyError("H21 entry must be: st <ACC>, ACC0; jump <top>")
    if not isinstance(store.address, str) or not store.address or store.value != ACC0:
        raise AssemblyError(f"H21 stores the accumulator as: st <cell>, {ACC0}")
    acc_cell = store.address
    top_name = jump.target
    top = blocks.get(top_name)
    if top is None or len(top.operations) != 2:
        raise AssemblyError("H21 loop head must have exactly two operations")
    read_s, branch = top.operations
    if not isinstance(read_s, ReadA) or not isinstance(read_s.destination, str) or not read_s.destination:
        raise AssemblyError("H21 loop head must start with: read <s>")
    if not isinstance(branch, BranchZero) or branch.value != read_s.destination:
        raise AssemblyError("H21 dispatches with: brz <s>, <zero>, <echo>")
    zero, echo = blocks.get(branch.zero_target), blocks.get(branch.nonzero_target)
    if zero is None or echo is None:
        raise AssemblyError("H21 branch targets must name blocks")
    if zero.operations != (Halt(),):
        raise AssemblyError("H21 stop block must be only: halt")
    if len(echo.operations) != 4:
        raise AssemblyError("H21 payload block must have exactly four operations")
    read_b, craz, write, jump_back = echo.operations
    if (not isinstance(read_b, ReadA) or not isinstance(read_b.destination, str) or not read_b.destination
            or not isinstance(craz, CrazyCell) or craz.address != acc_cell
            or not isinstance(write, WriteA) or write.value != "A"
            or not isinstance(jump_back, Jump) or jump_back.target != top_name):
        raise AssemblyError("H21 payload block must be: read <b>; craz <ACC>; write; jump <top>")
    for case in module.cases:
        if reference(case.stdin) != case.stdout:
            raise AssemblyError("declared case contradicts the H21 cipher semantics")


def lower(module: Module) -> NativeIrCipher:
    """Emit the native image for an accepted module (or refuse the module)."""
    check_module(module)
    loop = _build(PARAMS)
    return NativeIrCipher(loop.image, dict(loop.cells), LOWERING)

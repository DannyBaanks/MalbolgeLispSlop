"""H23: the H22 two-accumulator cipher loop lowered from an IR module.

The accepted module (see `examples/ir_cipher2.slop`) is H21's cipher module with
a second `craz` in the payload block:

    entry init
    init:  st ACC, 5
           st ACC2, 7
           jump top
    top:   read s
           brz s, zero, echo
    zero:  halt
    echo:  read b
           craz ACC         ; ACC1' = crazy(ACC, A=b); A = ACC1'
           craz ACC2        ; ACC2' = crazy(ACC2, A=ACC1'); A = ACC2'
           write            ; print ACC2' & 0xFF
           jump top

`check_module` accepts exactly that CFG (one parameterless function, four
blocks) and checks every declared case against `native_cipher2.reference`
before emitting; anything else raises `AssemblyError`. `lower` emits through
`native_cipher2`'s frozen layout, so **the IR-compiled image is byte-identical
to the sealed H22 image** and no memory above it is read.
"""

from __future__ import annotations

from dataclasses import dataclass

from .assemble import AssemblyError
from .ir import BranchZero, CrazyCell, Halt, Jump, Module, ReadA, Store, WriteA
from .native_cipher2 import ACC10, ACC20, PARAMS, _build, reference

LOWERING = "fixed19-native-ir-cipher2-v1"


@dataclass(frozen=True, slots=True)
class NativeIrCipher2:
    image: bytes
    cells: dict[str, int]
    lowering: str = LOWERING


def check_module(module: Module) -> None:
    """Accept exactly the H23 two-accumulator cipher CFG and check its cases."""
    if len(module.functions) != 1:
        raise AssemblyError("H23 has no lowering for multiple functions")
    function = module.functions[0]
    if function.parameters:
        raise AssemblyError("H23 lowers only a parameterless main")
    blocks = {block.name: block for block in function.blocks}
    entry = blocks.get(function.entry_block)
    if entry is None or len(blocks) != 4 or len(entry.operations) != 3:
        raise AssemblyError("H23 requires four blocks; the entry stores both accumulators and jumps to the loop head")
    store1, store2, jump = entry.operations
    if not isinstance(store1, Store) or not isinstance(store2, Store) or not isinstance(jump, Jump):
        raise AssemblyError("H23 entry must be: st <ACC>, ACC10; st <ACC2>, ACC20; jump <top>")
    if not isinstance(store1.address, str) or not store1.address or store1.value != ACC10:
        raise AssemblyError(f"H23 stores the first accumulator as: st <cell>, {ACC10}")
    if (not isinstance(store2.address, str) or not store2.address or store2.value != ACC20
            or store2.address == store1.address):
        raise AssemblyError(f"H23 stores the second accumulator as: st <cell>, {ACC20} on a different cell")
    acc1, acc2 = store1.address, store2.address
    top_name = jump.target
    top = blocks.get(top_name)
    if top is None or len(top.operations) != 2:
        raise AssemblyError("H23 loop head must have exactly two operations")
    read_s, branch = top.operations
    if not isinstance(read_s, ReadA) or not isinstance(read_s.destination, str) or not read_s.destination:
        raise AssemblyError("H23 loop head must start with: read <s>")
    if not isinstance(branch, BranchZero) or branch.value != read_s.destination:
        raise AssemblyError("H23 dispatches with: brz <s>, <zero>, <echo>")
    zero, echo = blocks.get(branch.zero_target), blocks.get(branch.nonzero_target)
    if zero is None or echo is None:
        raise AssemblyError("H23 branch targets must name blocks")
    if zero.operations != (Halt(),):
        raise AssemblyError("H23 stop block must be only: halt")
    if len(echo.operations) != 5:
        raise AssemblyError("H23 payload block must have exactly five operations")
    read_b, craz1, craz2, write, jump_back = echo.operations
    if (not isinstance(read_b, ReadA) or not isinstance(read_b.destination, str) or not read_b.destination
            or not isinstance(craz1, CrazyCell) or craz1.address != acc1
            or not isinstance(craz2, CrazyCell) or craz2.address != acc2
            or not isinstance(write, WriteA) or write.value != "A"
            or not isinstance(jump_back, Jump) or jump_back.target != top_name):
        raise AssemblyError("H23 payload block must be: read <b>; craz <ACC>; craz <ACC2>; write; jump <top>")
    for case in module.cases:
        if reference(case.stdin) != case.stdout:
            raise AssemblyError("declared case contradicts the H23 two-accumulator cipher semantics")


def lower(module: Module) -> NativeIrCipher2:
    """Emit the native image for an accepted module (or refuse the module)."""
    check_module(module)
    loop = _build(PARAMS)
    return NativeIrCipher2(loop.image, dict(loop.cells), LOWERING)

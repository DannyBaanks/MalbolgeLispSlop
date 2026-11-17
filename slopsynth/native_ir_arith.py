"""H19: the H18 arithmetic loop lowered from an IR module.

The IR gains `CrazyCell` (`craz <cell>`): `mem[cell] = crazy(mem[cell], A)`
tritwise, mask in A; `A = result`. With it the H18 loop is an ordinary module
(`examples/ir_arith.slop`, n = 4):

    entry init
    init:  st Z, 81            ; counter = 3^4
           st ACC, 5           ; accumulator seed
           jump top
    top:   ld v, Z
           breq v, 1, done, body
    body:  rot Z              ; Z' = rotate(Z), A = Z'
           write              ; print Z'
           craz ACC           ; ACC' = crazy(ACC, A=Z'); A = ACC'
           write              ; print ACC'
           jump top
    done:  halt

`check_module` accepts exactly that CFG (one parameterless function, four
blocks) and checks every declared case against `native_arith_loop.reference`
before emitting; anything else raises `AssemblyError`. `lower` emits through
`native_arith_loop`'s frozen layouts keyed by the module's `n`, so the
IR-compiled image is byte-identical to the sealed H18 image and no memory above
it is read. The program reads no input; every case's stdin is ignored.
"""

from __future__ import annotations

from dataclasses import dataclass

from .assemble import AssemblyError
from .ir import BranchEq, CrazyCell, Halt, Jump, Load, Module, Rotate, Store, WriteA
from .native_arith_loop import ACC0, MAX_COUNT, FROZEN, _build, reference

LOWERING = "fixed19-native-ir-arith-v1"


@dataclass(frozen=True, slots=True)
class NativeIrArith:
    image: bytes
    count: int
    cells: dict[str, int]
    lowering: str = LOWERING


def module_source(n: int) -> str:
    """The canonical H19 module source for counter 3^n and accumulator ACC0."""
    return (
        f"name ir_arith_{n}\n"
        f"case ,{reference(n).hex()}\n"
        f"entry init\n"
        f"init:\n"
        f"    st Z, {3**n}\n"
        f"    st ACC, {ACC0}\n"
        f"    jump top\n"
        f"top:\n"
        f"    ld v, Z\n"
        f"    breq v, 1, done, body\n"
        f"body:\n"
        f"    rot Z\n"
        f"    write\n"
        f"    craz ACC\n"
        f"    write\n"
        f"    jump top\n"
        f"done:\n"
        f"    halt\n"
    )


def _log3(value: int) -> int | None:
    n = 0
    while value > 1 and value % 3 == 0:
        value //= 3
        n += 1
    return n if value == 1 else None


def check_module(module: Module) -> int:
    """Accept exactly the H19 arithmetic-loop CFG; return its count n."""
    if len(module.functions) != 1:
        raise AssemblyError("H19 has no lowering for multiple functions")
    function = module.functions[0]
    if function.parameters:
        raise AssemblyError("H19 lowers only a parameterless main")
    blocks = {block.name: block for block in function.blocks}
    entry = blocks.get(function.entry_block)
    if entry is None or len(blocks) != 4 or len(entry.operations) != 3:
        raise AssemblyError("H19 requires four blocks; the entry stores counter and accumulator and jumps to the loop head")
    store_z, store_acc, jump = entry.operations
    if not isinstance(store_z, Store) or not isinstance(store_acc, Store) or not isinstance(jump, Jump):
        raise AssemblyError("H19 entry must be: st <Z>, 3^n; st <ACC>, ACC0; jump <top>")
    if not isinstance(store_z.address, str) or not store_z.address or not isinstance(store_z.value, int):
        raise AssemblyError("H19 stores the counter as: st <cell>, <integer 3^n>")
    if not isinstance(store_acc.address, str) or not store_acc.address or store_acc.value != ACC0:
        raise AssemblyError(f"H19 stores the accumulator as: st <cell>, {ACC0}")
    if store_z.address == store_acc.address:
        raise AssemblyError("H19 needs two different cells for counter and accumulator")
    n = _log3(store_z.value)
    if n is None or not 0 <= n <= MAX_COUNT:
        raise AssemblyError(f"H19 lowers only counters 3^0..3^{MAX_COUNT}, got {store_z.value}")
    cell_z, cell_acc = store_z.address, store_acc.address
    top_name = jump.target
    top = blocks.get(top_name)
    if top is None or len(top.operations) != 2:
        raise AssemblyError("H19 loop head must have exactly two operations")
    load, branch = top.operations
    if not isinstance(load, Load) or load.address != cell_z or not isinstance(load.destination, str) or not load.destination:
        raise AssemblyError("H19 loop head must start with: ld <v>, <Z>")
    if not isinstance(branch, BranchEq) or branch.value != load.destination or branch.rhs != 1:
        raise AssemblyError("H19 dispatches with: breq <v>, 1, <done>, <body>")
    body, done = blocks.get(branch.ne_target), blocks.get(branch.eq_target)
    if body is None or done is None:
        raise AssemblyError("H19 branch targets must name blocks")
    if body.operations != (Rotate(cell_z), WriteA("A"), CrazyCell(cell_acc), WriteA("A"), Jump(top_name)):
        raise AssemblyError("H19 body must be: rot <Z>; write; craz <ACC>; write; jump <top>")
    if done.operations != (Halt(),):
        raise AssemblyError("H19 stop block must be only: halt")
    for case in module.cases:
        if reference(n) != case.stdout:
            raise AssemblyError("declared case contradicts the H19 arithmetic-loop semantics")
    return n


def lower(module: Module) -> NativeIrArith:
    """Emit the native image for an accepted module (or refuse the module)."""
    n = check_module(module)
    params, acc = FROZEN[n]
    loop = _build(n, params, acc)
    return NativeIrArith(loop.image, n, dict(loop.cells), LOWERING)

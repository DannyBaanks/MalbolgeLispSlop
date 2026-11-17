"""H17: the H16 countdown lowered from an IR module.

The IR gains two operations (see `ir.py`): `Rotate` (`A = rotate(mem[addr])`,
`mem[addr] = A`) and `BranchEq` (branch on `value == rhs`). With them the
countdown is an ordinary module:

    entry init
    init:  st Z, 3^n        ; the counter cell starts at 3^n
           jump top
    top:   ld v, Z          ; v = counter
           breq v, 1, done, body
    body:  rot Z            ; counter /= 3, A = new value
           write            ; print A
           jump top
    done:  halt

`check_module` accepts exactly that CFG (one parameterless function, four
blocks) and checks every declared case against the reference before emitting
anything; everything else raises `AssemblyError`. The dispatch on `v == 1`
lowers to H16's native table: the `move` reads the counter cell, the `jump`
reads the cell `v + 5 + slack_a`, and the entry for `v == 1` is the in-image
`halt`. `lower` emits the H16 image for the module's `n` through
`native_count_in`'s frozen layouts, so the IR-compiled image is byte-identical
to the sealed H16 image and no memory above it is read.

The program reads no input: every case's stdin is ignored, and its stdout must
be the countdown bytes 3^(n-1), ..., 9, 3, 1.
"""

from __future__ import annotations

from dataclasses import dataclass

from .assemble import AssemblyError
from .ir import BranchEq, Halt, Jump, Load, Module, Rotate, Store, WriteA
from .native_count_in import MAX_COUNT, build_count_in, counter_values

LOWERING = "fixed19-native-ir-count-v1"


@dataclass(frozen=True, slots=True)
class NativeIrCount:
    image: bytes
    count: int
    steps_per_pass: tuple[int, int]
    cells: dict[str, int]
    lowering: str = LOWERING


def reference(n: int) -> bytes:
    """Output of the H17 countdown module with counter 3^n (input is ignored)."""
    return bytes(v & 255 for v in counter_values(n))


def module_source(n: int) -> str:
    """The canonical H17 module source for a counter of 3^n."""
    out = reference(n).hex()
    return (
        f"name ir_count_{n}\n"
        f"case ,{out}\n"
        f"entry init\n"
        f"init:\n"
        f"    st Z, {3**n}\n"
        f"    jump top\n"
        f"top:\n"
        f"    ld v, Z\n"
        f"    breq v, 1, done, body\n"
        f"body:\n"
        f"    rot Z\n"
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
    """Accept exactly the H17 countdown CFG; return its count n. Check cases first."""
    if len(module.functions) != 1:
        raise AssemblyError("H17 has no lowering for multiple functions")
    function = module.functions[0]
    if function.parameters:
        raise AssemblyError("H17 lowers only a parameterless main")
    blocks = {block.name: block for block in function.blocks}
    entry = blocks.get(function.entry_block)
    if entry is None or len(blocks) != 4 or len(entry.operations) != 2:
        raise AssemblyError("H17 requires four blocks; the entry stores the counter and jumps to the loop head")
    store, jump = entry.operations
    if not isinstance(store, Store) or not isinstance(jump, Jump):
        raise AssemblyError("H17 entry must be: st <cell>, 3^n; jump <top>")
    if not isinstance(store.address, str) or not store.address or not isinstance(store.value, int):
        raise AssemblyError("H17 stores the counter as: st <cell>, <integer 3^n>")
    n = _log3(store.value)
    if n is None or not 0 <= n <= MAX_COUNT:
        raise AssemblyError(f"H17 lowers only counters 3^0..3^{MAX_COUNT}, got {store.value}")
    cell = store.address
    top_name = jump.target
    top = blocks.get(top_name)
    if top is None or len(top.operations) != 2:
        raise AssemblyError("H17 loop head must have exactly two operations")
    load, branch = top.operations
    if not isinstance(load, Load) or load.address != cell or not isinstance(load.destination, str) or not load.destination:
        raise AssemblyError("H17 loop head must start with: ld <v>, <cell>")
    if not isinstance(branch, BranchEq) or branch.value != load.destination or branch.rhs != 1:
        raise AssemblyError("H17 dispatches with: breq <v>, 1, <done>, <body>")
    body, done = blocks.get(branch.ne_target), blocks.get(branch.eq_target)
    if body is None or done is None:
        raise AssemblyError("H17 branch targets must name blocks")
    if body.operations != (Rotate(cell), WriteA("A"), Jump(top_name)):
        raise AssemblyError("H17 body must be: rot <cell>; write; jump <top>")
    if done.operations != (Halt(),):
        raise AssemblyError("H17 stop block must be only: halt")
    for case in module.cases:
        if reference(n) != case.stdout:
            raise AssemblyError("declared case contradicts the H17 countdown semantics")
    return n


def lower(module: Module) -> NativeIrCount:
    """Emit the native image for an accepted module (or refuse the module)."""
    n = check_module(module)
    loop = build_count_in(n)
    return NativeIrCount(loop.image, n, loop.steps_per_pass, dict(loop.cells), LOWERING)

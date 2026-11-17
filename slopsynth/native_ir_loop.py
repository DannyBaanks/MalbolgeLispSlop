"""H15: the first native fixed19 loop emitted from an IR module.

The IR shape is H3's loop, unchanged:

    loop: A = read()
          if A == 0: halt
          A = read()
          write(A)
          jump loop

H3 lowered it to a hand-assembled 259-cell image whose loop does not iterate
(the audit in `evidence/h3_h7_loop_audit_v1/`). H15 lowers the same module to a
*lapped* body (see `native_asm.Laps` and `cycles.py`) that re-executes the same
cells on every pass, like H13a/H13b/H14, and ends at an in-image `halt`.

The selector is tested with H13b's two-`crazy` identity; the dispatch table maps
byte 0 and the EOF word to a halt pointer and every other byte to the resume
path; the payload is read only on the resume path. Nothing above the image is
read, so the exit does not depend on the VM's memory fill (the hole H14
documents). On truncated input the loop halts at EOF, which is observably the
same as H3's host loop for every finite byte input: H3 stops at end of input and
H15 stops at the EOF word.

The compiler refuses every other CFG and checks each declared case against the
reference below before emitting anything.
"""

from __future__ import annotations

from dataclasses import dataclass

from .assemble import AssemblyError
from .cycles import PAIR_GAP, jump_cell, padding, pair_cell, pair_residue
from .ir import BranchZero, Halt, Jump, Module, ReadA, WriteA
from .native_asm import FAR, LAP, STEP, Conflict, Laps, Memory, bootstrap, once, seed as byte_seed
from .native_loop import EOF_BYTE

LOWERING = "fixed19-native-ir-loop-v1"
TABLE_LAPS = 4  # laps between the dispatch move and the table move
EOF_WORD = 1700  # value of W after reading EOF (H13b)

# Addresses found by `search()`; the build checks every claim, so a bad set fails loudly.
PARAMS = {
    "Y": 60, "W": 112, "U": 51, "V": 75, "table": 58,
    "eof": 63, "halt": 98, "slack": 7, "budget": 550, "P": 84,
}


@dataclass(frozen=True, slots=True)
class NativeLoop:
    image: bytes
    loop_head: int
    loop_end: int
    steps_per_pass: int
    cells: dict[str, int]
    lowering: str = LOWERING


def reference(stdin: bytes) -> bytes:
    """Output the H3 loop produces on `stdin`, stopping at 0 or end of input."""
    out = bytearray()
    idx = 0
    while idx < len(stdin):
        selector = stdin[idx]
        idx += 1
        if selector == 0:
            break
        if idx < len(stdin):
            out.append(stdin[idx])
            idx += 1
        else:
            out.append(EOF_BYTE)
    return bytes(out)


def check_module(module: Module) -> None:
    """Accept exactly H3's loop CFG and prove every declared case against `reference`."""
    if len(module.functions) != 1:
        raise AssemblyError("H15 has no lowering for multiple functions")
    function = module.functions[0]
    blocks = {block.name: block for block in function.blocks}
    entry = blocks.get(function.entry_block)
    if (function.parameters or len(blocks) != 3 or entry is None
            or len(entry.operations) != 2
            or entry.operations[0] != ReadA()
            or not isinstance(entry.operations[1], BranchZero)):
        raise AssemblyError("H15 lowers only: read A; brz A, stop, echo")
    branch = entry.operations[1]
    if (branch.value != "A"
            or len({entry.name, branch.zero_target, branch.nonzero_target}) != 3
            or blocks[branch.zero_target].operations != (Halt(),)
            or blocks[branch.nonzero_target].operations != (ReadA(), WriteA(), Jump(function.entry_block))):
        raise AssemblyError("H15 requires zero: halt; nonzero: read A; write A; jump entry")
    for case in module.cases:
        if reference(case.stdin) != case.stdout:
            raise AssemblyError("declared case contradicts the H15 loop semantics")


def lower(module: Module, params: dict[str, int] | None = None) -> NativeLoop:
    """Emit the native loop for an accepted module (or refuse the module)."""
    check_module(module)
    return _build(PARAMS if params is None else params)


def _build(p: dict[str, int]) -> NativeLoop:
    memory = Memory()
    y, w, u, v = p["Y"], p["W"], p["U"], p["V"]
    for name, seed in (("Y", 0), ("W", 0), ("V", 0), ("U", 2)):
        memory.claim(p[name], seed, name)

    # ---- loop, in the timeline of an even pass: D = off + C between moves
    landing = FAR + p["budget"]
    landing += -landing % STEP  # the loop-back jump lands here
    base = (landing - pair_residue("input")) // LAP * LAP + LAP  # first lap whose input pair is past the landing
    laps = Laps(memory, base)
    pairs = laps.pairs
    constants: list[tuple[int, int]] = []
    pair, move, crazy, access = laps.pair, laps.move, laps.crazy, laps.access
    position = laps.position

    def put(name: str, after: int) -> int:
        """Place `name` at the first lap whose cell is past `after`."""
        at = position(laps.lap, name)
        while at <= after:
            laps.lap += 1
            at = position(laps.lap, name)
        return pair(name)

    pair("input", 0)  # head: read the selector
    first_move = move(y - 22)
    crazy(y)
    access(w)
    move(w - LAP, exact=True)  # next lap's move finds D at W
    laps.lap += 1
    dispatch = pair("move", laps.lap)  # D = b, or EOF_WORD
    laps.lap += TABLE_LAPS
    table_move = pair("move", laps.lap)  # D = the pointer stored at table + b
    table = table_move - dispatch
    for byte in range(1, 256):
        memory.claim(table + byte, p["table"])
    memory.claim(table, p["eof"])  # selector 0 takes the halt path
    memory.claim(table + EOF_WORD, p["eof"])  # EOF takes the halt path too
    jump_a = table_move + PAIR_GAP + 1
    resume = jump_a + 1 + (-(jump_a + 1) % STEP)  # continue after this cell
    for lag in (0, PAIR_GAP):
        constants.append((p["table"] + 5 - lag, resume))
        memory.claim(p["eof"] + 5 - lag, p["halt"])
    halt_at = p["halt"] + 1
    memory.claim(halt_at, once("halt", halt_at), "halt")

    # ---- resume path: restore Y and W while A still holds the selector byte
    laps.off = p["table"] + 5 - resume
    laps.lap = (resume - base) // LAP
    if position(laps.lap, "output") <= resume:
        laps.lap += 1
    access(w)
    access(y)
    access(y)
    rotate_lap = laps.lap
    while True:  # rotate Z sits one step before the next move
        zero = laps.off + position(rotate_lap, "rotate")
        pointer_free = memory.fits(zero + 1, y - 22)
        if pointer_free and (memory.free(zero) or memory.cells[zero] == (0, "zero")):
            break
        rotate_lap += 1
        if rotate_lap > laps.lap + 3:
            raise Conflict("no room for the zero cell")
    memory.cells[zero] = (0, "zero")
    pair("rotate", rotate_lap)
    laps.lap = rotate_lap
    access(y)
    access(u)
    access(v)
    move(w - 22)
    crazy(w)
    last = position(laps.lap - 1, "crazy")

    payload = put("input", last)  # read the payload
    printed = put("output", payload)  # print it
    back = move(p["P"])  # pointer the loop-back jump reads
    jump_b = back + 22 + PAIR_GAP + 1 + p["slack"]
    for lag in (0, PAIR_GAP):
        constants.append((laps.off + jump_b - lag, landing))
    entry = laps.off + jump_b - landing + first_move
    for lag in (-PAIR_GAP, PAIR_GAP):
        memory.claim(entry + lag, y - 22)
    for address, value in constants:
        memory.claim(address, byte_seed(value)[0], "seed")

    # ---- one-shot code: bootstrap at 0, prologue at FAR
    def scratch(seed: int) -> int:
        for address in range(33, 127):
            if all(memory.free(address + i) for i in range(4)):
                memory.claim(address, seed, "scratch")
                return address
        raise Conflict("no room for a prologue cell")

    code = bootstrap(memory)
    for address, value in constants:
        code.at(address, "rotate", byte_seed(value)[1])
    s1, c125, c121, temp, zero_p = (scratch(seed) for seed in (26, 125, 121, 0, 0))
    code.at(u, "rotate", 12)  # U = 2 * 3^6
    code.at(s1, "rotate", 16)  # A = 234
    code.at(c125, "crazy")  # 2s in trits 0..4, 1s above
    code.at(c121, "crazy")  # A = 242
    code.at(temp, "crazy")  # A = ones - 121
    code.at(u, "crazy")  # U = 1579
    code.at(zero_p, "rotate")  # A = 0
    code.at(c125, "crazy")  # reload, unchanged
    code.at(u, "crazy")  # U = 1700
    code.at(v, "crazy")  # V = ones - 850
    code.at(w, "crazy")  # W = 850
    code.at(zero_p, "rotate")
    code.at(y, "crazy")  # Y = ones
    # enter the loop as an even pass does
    for _ in range(200):
        pointer = entry - PAIR_GAP - (first_move - code.c)
        if code.c >= landing:
            raise Conflict("prologue is longer than its budget")
        if 0 <= pointer < 128 and memory.fits(code.d, pointer):
            code.emit("move")
            break
        code.nop()
    else:
        raise Conflict("no entry pointer")

    end = jump_b
    cells: list[int | None] = [None] * (end + 1)
    for address, (value, _) in memory.cells.items():
        if address > end:
            raise Conflict("data beyond the code")
        cells[address] = value
    for name, at in pairs:
        for offset, first in ((0, True), (PAIR_GAP, False)):
            if cells[at + offset] is not None:
                raise Conflict("loop cells overlap")
            cells[at + offset] = pair_cell(name, at + offset, first)
    for at in (jump_a, jump_b):
        if cells[at] is not None:
            raise Conflict("jump overlaps")
        cells[at] = jump_cell(at)
    image = bytes((padding(i) if i >= FAR else 0) if value is None else value for i, value in enumerate(cells))
    names = {"Y": y, "W": w, "U": u, "V": v, "Z": zero, "table": table,
             "zero_cell": table, "eof_cell": table + EOF_WORD, "halt": halt_at,
             "prologue": FAR + 1, "landing": landing, "resume": resume, "P": p["P"]}
    return NativeLoop(image, landing, end, (jump_a - landing) + (jump_b - resume), names)

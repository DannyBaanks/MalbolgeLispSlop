"""H26: Universal non-destructive LOAD, RESET, and STORE in a re-executable fixed19 loop.

Refutes the H23 hypothesis that a re-executable fixed19 loop cannot overwrite a
memory cell with a newly computed/read value independent of its old state:

1. `C2` is initialized in the one-shot prologue with `2`s in trits 0..7 and `1`s
   in trits 8..18 (`crazy(0, C2)` leaves `C2` invariant).
2. Non-destructive `LOAD(X -> A)` for any byte `X`:
       zero_and_access(C2); access(X); zero_and_access(C2); access(X)
   Because `CRZ[x][2]` swaps trits 1 <-> 2 and keeps 0 -> 0, applying it twice
   restores `X` to its original value and leaves `A == X`.
3. Universal `RESET(X -> ALL_1)` from any prior value in `{0, 1, 2}^19`:
       zero_and_access(Y); access(X); zero_and_access(C2); access(X);
       zero_and_access(Y); access(X); zero_and_access(X)
4. Universal `STORE(X <- A)` once `T == ALL_1` and `X == ALL_1`:
       access(T); access(X)
   Because `CRZ[1][a]` swaps 0 <-> 1 and keeps 2 -> 2, two `ALL_1` cells copy `A`
   into `X` and leave `A` unchanged.

The H26 image implements a 1-step delayed shift register: on each `(selector, b)`
pass (stopping at `selector == 0` or EOF), it loads and prints the previous byte
in `MEM` (initially `MEM0 = 42`, `'*'`), then resets `MEM` and `T` and stores the
new byte `b` into `MEM`.
"""

from __future__ import annotations

from dataclasses import dataclass

from .cycles import PAIR_GAP, jump_cell, padding, pair_cell, pair_residue
from .native_asm import LAP, STEP, Conflict, Laps, Memory, bootstrap, once, seed as byte_seed
from .native_ir_loop import EOF_WORD, TABLE_LAPS

LOWERING = "fixed19-native-store-v1"
MEM0 = 42  # initial byte '*' in MEM
_PAD = tuple(padding(i) for i in range(94))

PARAMS = {
    "Y": 82, "W": 114, "U": 115, "V": 45, "C2": 125, "MEM": 43, "T": 44,
    "table": 60, "eof": 51, "halt": 59, "slack": 3, "budget": 420, "P": 68,
    "far": 36 * STEP,
}


def reference(stdin: bytes, initial: int = MEM0) -> bytes:
    """Expected stdout of the H26 shift-register loop on `stdin`."""
    out = bytearray()
    mem = initial
    idx = 0
    while idx < len(stdin):
        selector = stdin[idx]
        idx += 1
        if selector == 0:
            break
        out.append(mem & 0xFF)
        if idx < len(stdin):
            mem = stdin[idx]
            idx += 1
        else:
            break
    return bytes(out)


@dataclass(frozen=True, slots=True)
class StoreLoop:
    image: bytes
    cells: dict[str, int]
    lowering: str = LOWERING


def build_store_loop(params: dict[str, int] | None = None) -> StoreLoop:
    p = PARAMS if params is None else params
    memory = Memory()
    y, w, u, v = p["Y"], p["W"], p["U"], p["V"]
    c2, mem_cell, t_cell = p["C2"], p["MEM"], p["T"]
    for name, s in (("Y", 0), ("W", 0), ("V", 0), ("U", 2), ("C2", 0), ("MEM", MEM0), ("T", 0)):
        memory.claim(p[name], s, name)

    far = p["far"]
    landing = far + p["budget"]
    landing += -landing % STEP
    base = (landing - pair_residue("input")) // LAP * LAP + LAP
    laps = Laps(memory, base)
    pairs = laps.pairs
    pair, move, crazy, access = laps.pair, laps.move, laps.crazy, laps.access
    position = laps.position
    constants: list[tuple[int, int]] = []

    def put(name: str, after: int) -> int:
        at = position(laps.lap, name)
        while at <= after:
            laps.lap += 1
            at = position(laps.lap, name)
        return pair(name)

    def move_any(pointer: int) -> int:
        lap = laps.lap
        while True:
            at = position(lap, "move")
            if laps.off is None or memory.fits(laps.off + at, pointer):
                break
            lap += 1
            if lap > laps.lap + 40:
                raise Conflict(f"no room for pointer {pointer}")
        pair("move", lap)
        laps.off = pointer - at
        laps.lap = lap
        return at

    def access_any(cell: int) -> None:
        move_any(cell - 22)
        crazy(cell)

    def zero_and_access(target_cell: int) -> None:
        rot_lap = laps.lap
        while True:
            z = laps.off + position(rot_lap, "rotate")
            if (memory.free(z) or memory.cells.get(z) == (0, "zero")) and memory.fits(z + 1, target_cell - 22):
                break
            rot_lap += 1
            if rot_lap > laps.lap + 40:
                raise Conflict("no room for zero cell")
        memory.cells[z] = (0, "zero")
        pair("rotate", rot_lap)
        laps.lap = rot_lap
        at = position(rot_lap, "move")
        pair("move", rot_lap)
        laps.off = (target_cell - 22) - at
        crazy(target_cell)

    pair("input", 0)
    first_move = move(y - 22)
    crazy(y)
    access(w)
    move(w - LAP, exact=True)
    laps.lap += 1
    dispatch = pair("move", laps.lap)
    laps.lap += TABLE_LAPS
    table_move = pair("move", laps.lap)
    table = table_move - dispatch
    for byte in range(1, 256):
        memory.claim(table + byte, p["table"])
    memory.claim(table, p["eof"])
    memory.claim(table + EOF_WORD, p["eof"])
    jump_a = table_move + PAIR_GAP + 1
    resume = jump_a + 1 + (-(jump_a + 1) % STEP)
    for lag in (0, PAIR_GAP):
        constants.append((p["table"] + 5 - lag, resume))
        memory.claim(p["eof"] + 5 - lag, p["halt"])
    halt_at = p["halt"] + 1
    memory.claim(halt_at, once("halt", halt_at), "halt")

    laps.off = p["table"] + 5 - resume
    laps.lap = (resume - base) // LAP
    if position(laps.lap, "output") <= resume:
        laps.lap += 1
    access_any(w)
    access_any(y)
    access_any(y)
    zero_and_access(y)
    access_any(u)
    access_any(v)
    access_any(w)

    # 1. LOAD(MEM -> A) and output old MEM
    zero_and_access(c2)
    access_any(mem_cell)
    zero_and_access(c2)
    access_any(mem_cell)
    last = position(laps.lap - 1, "crazy")
    put("output", last)

    # 2. RESET(MEM -> ALL_1) and RESET(T -> ALL_1)
    for cell in (mem_cell, t_cell):
        zero_and_access(y)
        access_any(cell)
        zero_and_access(c2)
        access_any(cell)
        zero_and_access(y)
        access_any(cell)
        zero_and_access(cell)

    # 3. Read new payload b and STORE(MEM <- b)
    last = position(laps.lap - 1, "crazy")
    put("input", last)
    access_any(t_cell)
    access_any(mem_cell)

    back = move_any(p["P"])
    jump_b = back + 22 + PAIR_GAP + 1 + p["slack"]
    for lag in (0, PAIR_GAP):
        constants.append((laps.off + jump_b - lag, landing))
    entry = laps.off + jump_b - landing + first_move
    for lag in (-PAIR_GAP, PAIR_GAP):
        memory.claim(entry + lag, y - 22)
    for address, value in constants:
        memory.claim(address, byte_seed(value)[0], "seed")

    def scratch(s: int) -> int:
        for address in range(33, 127):
            if all(memory.free(address + i) for i in range(4)):
                memory.claim(address, s, "scratch")
                return address
        raise Conflict("no room for a prologue cell")

    code = bootstrap(memory, far=far)
    for address, value in constants:
        code.at(address, "rotate", byte_seed(value)[1])
    s1, c125, c121, temp, zero_p, s80 = (scratch(s) for s in (26, 125, 121, 0, 0, 80))
    code.at(u, "rotate", 12)
    code.at(s1, "rotate", 16)
    code.at(c125, "crazy")
    code.at(c121, "crazy")
    code.at(temp, "crazy")
    code.at(u, "crazy")
    code.at(zero_p, "rotate")
    code.at(c125, "crazy")
    code.at(u, "crazy")
    code.at(v, "crazy")
    code.at(w, "crazy")
    code.at(zero_p, "rotate")
    code.at(y, "crazy")
    code.at(zero_p, "rotate")
    code.at(c2, "crazy")
    code.at(s80, "rotate", 14)
    code.at(c2, "crazy")
    code.at(s80, "rotate", 4)
    code.at(c2, "crazy")

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
    image = bytes((_PAD[i % 94] if i >= far else 0) if value is None else value for i, value in enumerate(cells))
    return StoreLoop(image, {"MEM": mem_cell, "T": t_cell, "C2": c2, "halt": halt_at, "landing": landing})

"""H18: lap-safe `crazy` arithmetic on a data cell inside the re-executing loop.

H16's countdown rewrites the counter with `rotate` every pass. H18 adds a second
data cell, the accumulator `ACC`, which a `crazy` rewrites **every pass** with
the mask in A: the resume path runs `rotate Z` (A = Z'), `output`, then
`access(ACC)` so that `ACC <- TBL[ACC][Z']` tritwise, then `output` prints ACC'.
The same cells run on every pass, the dispatch table on `v = Z` (read before
rotating, as in H16) sends `v == 1` to the in-image `halt` at cell 244, and no
memory above the image is read (the model runs with `max_address = len(image)-1`).

So each non-final pass prints two bytes: `Z' mod 256` and `ACC' mod 256`. For a
counter `3^n` and accumulator seed `ACC0` the reference is:

    Z = 3^n; ACC = ACC0
    while Z != 1:
        Z   = rotate(Z)              # A = Z
        ACC = crazy(ACC, A=Z)        # tritwise TBL[ACC][Z]; A = ACC
        emit Z & 0xFF; emit ACC & 0xFF
    halt

Why not a real decrement (`sub 1`): fixed19 has no store opcode (`move` only
sets D = mem[D]; stores happen through `crazy`/`rotate`), and `crazy` is tritwise,
so carry-based arithmetic is not a single `crazy` — H7 lowered `sub n, n, 1`
straight-line via landing cascades. A borrow decrement *inside a re-executing
loop* is NOT_DEMONSTRATED here; H18 demonstrates the lap-safe `crazy` cell update
(the primitive such a loop would need) plus the in-image exit.

The image loads only with the raw loader (inert cells, as H13a..H17).
"""

from __future__ import annotations

from dataclasses import dataclass

from .cycles import PAIR_GAP, jump_cell, padding, pair_cell, pair_residue
from .model import _crazy, _rotate
from .native_asm import FAR, LAP, STEP, Conflict, Laps, Memory, bootstrap, once, seed
from .native_count_in import MAX_COUNT, dispatch_values

LOWERING = "fixed19-native-arith-loop-v1"
END = 3 ** 19
RESIDUE_MOVE = pair_residue("move")
ACC0 = 5  # accumulator seed (an image byte)
MAX_PROLOGUE_NOP = 20_000


def reference(n: int) -> bytes:
    """Output of the H18 loop with counter 3^n and accumulator seed ACC0."""
    z = 3 ** n
    acc = ACC0
    out = bytearray()
    while z != 1:
        z = _rotate(z, END)
        acc = _crazy(z, acc, 19)  # crazy with D=ACC, A=z  ->  TBL[acc][z] per trit
        out.append(z & 0xFF)
        out.append(acc & 0xFF)
    return bytes(out)


@dataclass(frozen=True, slots=True)
class ArithLoop:
    image: bytes
    count: int
    cells: dict[str, int]
    lowering: str = LOWERING


def _layout(n: int, p: dict[str, int], acc: int):
    memory = Memory()
    z = p["Z"]
    slack_a, slack_b, pointer, budget = p["slack_a"], p["slack_b"], p["P"], p["budget"]
    if not 94 <= z < 127:
        raise Conflict("counter cell must be in 94..126")
    if not 94 <= acc < 127 or acc == z:
        raise Conflict("accumulator cell must be in 94..126 and differ from Z")
    vals = dispatch_values(n)
    constants: list[tuple[int, int]] = [(z, 3**n), (acc, ACC0)]
    memory.claim(z, seed(3**n)[0], "seed")
    memory.claim(acc, ACC0, "seed")

    table_lo = min(vals, default=1) + 5 + slack_a
    far = max(FAR, -(-(table_lo + 900) // STEP) * STEP)
    landing = far + budget
    landing += -landing % STEP
    base = (landing - 60) // LAP * LAP + LAP
    laps = Laps(memory, base)

    first = laps.move(z - 94)
    laps.lap = 1
    dispatch = laps.pair("move")
    if laps.off + dispatch != z:
        raise AssertionError("dispatch move would not read the counter")
    jump_a = dispatch + 5 + slack_a
    delta = jump_a - dispatch

    halt = p["halt"]
    memory.claim(halt, once("halt", halt), "halt")
    candidates = []
    for k in range(12, 3, -1):
        for b in range(1, 128):
            if b % 3 == 0:
                continue
            value = b * 3**k
            if value % LAP == RESIDUE_MOVE - 4 and value >= jump_a + 1 and value < 200_000:
                candidates.append((18 - k, value))
    if not candidates:
        raise Conflict("no seedable resume address")
    rotations, resume = min(candidates)
    if seed(resume)[1] != rotations:
        raise AssertionError("resume rotation count drifted")
    move_pos = resume + 4

    halt_entry = None
    for k, v in enumerate(vals, start=1):
        lag = 0 if k % 2 else PAIR_GAP
        address = v + delta - lag
        target = (halt - 1) if v == 1 else resume
        memory.claim(address, seed(target)[0], "seed")
        constants.append((address, target))
        if v == 1:
            halt_entry = address
        else:
            for extra in (4, 8):
                memory.claim(address + extra, z - 93, "pointer")
    if halt_entry is None:
        raise AssertionError("no halt entry")

    laps.lap = (move_pos - base) // LAP
    resume_move = laps.pair("move")
    if resume_move != move_pos:
        raise AssertionError(f"resume move at {resume_move} != {move_pos}")
    laps.off = (z - 93) - move_pos
    rotate_lap = laps.lap + 1
    rotate = laps.position(rotate_lap, "rotate")
    if laps.off + rotate != z:
        raise AssertionError("rotate would miss the counter")
    laps.pair("rotate", rotate_lap)
    laps.lap = rotate_lap + 1
    laps.pair("output")   # prints Z' (A after the rotate)
    laps.access(acc)       # ACC' = crazy(ACC, A=Z'); A = ACC'
    laps.pair("output")    # prints ACC'
    back = laps.pair("move")
    d_at_back = laps.off + back
    for extra in (0, PAIR_GAP):
        memory.claim(d_at_back + extra, pointer, "pointer")
    laps.off = pointer - back
    jump_b = back + 5 + slack_b
    for lag in (0, PAIR_GAP):
        address = laps.off + jump_b - lag
        memory.claim(address, seed(landing)[0], "seed")
        constants.append((address, landing))
    entry = laps.off + jump_b - landing + first
    for lag in (-PAIR_GAP, 0):
        memory.claim(entry + lag, z - 94, "pointer")
    return memory, laps, constants, dict(first=first, jump_a=jump_a, jump_b=jump_b, resume=resume,
                                         landing=landing, far=far, entry=entry, Z=z, delta=delta,
                                         halt=halt, halt_entry=halt_entry, acc=acc)


def _build(n: int, p: dict[str, int], acc: int) -> ArithLoop:
    memory, laps, constants, at = _layout(n, p, acc)
    code = bootstrap(memory, at["far"])
    for address, value in constants:
        times = seed(value)[1]
        if times:
            code.at(address, "rotate", times)
    for _ in range(MAX_PROLOGUE_NOP):
        pointer = at["entry"] - PAIR_GAP - (at["first"] - code.c)
        if code.c >= at["landing"]:
            raise Conflict("prologue is longer than its budget")
        if 0 <= pointer < 128 and memory.fits(code.d, pointer):
            code.emit("move")
            break
        code.nop()
    else:
        raise Conflict("no entry pointer")
    end = max(at["jump_b"], max(memory.cells))
    cells: list[int | None] = [None] * (end + 1)
    for address, (value, _) in memory.cells.items():
        cells[address] = value
    for name, where in laps.pairs:
        for offset, first_cell in ((0, True), (PAIR_GAP, False)):
            if cells[where + offset] is not None:
                raise Conflict(f"loop cell overlap at {where + offset} ({name})")
            cells[where + offset] = pair_cell(name, where + offset, first_cell)
    for where in (at["jump_a"], at["jump_b"]):
        if cells[where] is not None:
            raise Conflict("jump overlaps")
        cells[where] = jump_cell(where)
    image = bytes((padding(i) if i >= at["far"] else 0) if v is None else v for i, v in enumerate(cells))
    names = {"Z": at["Z"], "acc": at["acc"], "resume": at["resume"], "halt": at["halt"],
             "halt_entry": at["halt_entry"], "landing": at["landing"], "first": at["first"],
             "entry": at["entry"], "jump_a": at["jump_a"], "jump_b": at["jump_b"],
             "delta": at["delta"], "far": at["far"]}
    return ArithLoop(image, n, names)


# Layouts found by a seeded search (H16's frozen parameters plus the accumulator
# cell per count). The build checks every claim, so a bad set fails loudly.
FROZEN: dict[int, tuple[dict[str, int], int]] = {
    0: ({"Z": 94, "slack_a": 125, "slack_b": 30, "P": 42, "budget": 2200, "halt": 244}, 100),
    1: ({"Z": 94, "slack_a": 125, "slack_b": 30, "P": 42, "budget": 2200, "halt": 244}, 100),
    2: ({"Z": 94, "slack_a": 60, "slack_b": 30, "P": 42, "budget": 2200, "halt": 244}, 100),
    3: ({"Z": 94, "slack_a": 60, "slack_b": 30, "P": 42, "budget": 2200, "halt": 244}, 95),
    4: ({"Z": 94, "slack_a": 60, "slack_b": 30, "P": 42, "budget": 2200, "halt": 244}, 100),
    5: ({"Z": 94, "slack_a": 70, "slack_b": 30, "P": 42, "budget": 3000, "halt": 244}, 100),
    6: ({"Z": 94, "slack_a": 60, "slack_b": 30, "P": 42, "budget": 6000, "halt": 244}, 100),
}


def build_arith_loop(n: int) -> ArithLoop:
    """The image that prints the H18 two-bytes-per-pass countdown and halts in-image (0 <= n <= MAX_COUNT)."""
    if not 0 <= n <= MAX_COUNT:
        raise ValueError(f"count must be in 0..{MAX_COUNT}")
    params, acc = FROZEN[n]
    return _build(n, params, acc)

"""H16: the H14 countdown with the exit decided inside the image.

H14 (`native_count.py`) dispatches *after* rotating the counter, so the last
dispatch reads the cell `3^17 + delta`, which lies above the image; the exit
there depends on the VM's fill of memory above the image (the last two image
bytes). H16 dispatches *before* rotating, on the current counter value `v`:

    pass k   move      reads the counter cell Z: D = v, the value 3^(n+1-k)
             jump      reads the table cell v + 5 + slack_a
                      v == 1 -> the in-image halt cell, otherwise `resume`
    resume   move      D back to Z - 93 so the next lap's rotate sees D = Z
             rotate Z  A = v / 3, written back into Z
             output    prints v / 3
             move+jump back to the loop head

The table has one entry per dispatched value, {3^n, ..., 3, 1}; every cell
`v + delta` is small and inside the image, and the entry for `v == 1` holds
`halt - 1`, so the loop stops without ever reading above the image. The model
run with `max_address = len(image) - 1` would return MODEL_BOUND on any such
read; none is attempted.

`build_count_in(n)` prints the n bytes 3^(n-1), ..., 9, 3, 1 and halts, for
0 <= n <= MAX_COUNT, exactly like H14. The layouts are per-n, found by a seeded
search and frozen in `FROZEN`; the build checks every cell claim, so a bad
parameter set raises `Conflict` instead of emitting a wrong image. The image
loads only with the raw loader (it contains inert cells, as H13a/H13b/H14 do).
"""

from __future__ import annotations

from dataclasses import dataclass

from .cycles import PAIR_GAP, jump_cell, padding, pair_cell, pair_residue
from .native_asm import FAR, LAP, STEP, Conflict, Laps, Memory, bootstrap, once, seed

LOWERING = "fixed19-native-count-in-v1"
MAX_COUNT = 6
RESIDUE_MOVE = pair_residue("move")  # 60
MAX_PROLOGUE_NOP = 20_000  # the entry fill may walk a long way when the table is low


def counter_values(n: int) -> list[int]:
    """Values printed by `count_in(n)`, in order."""
    return [3 ** (n - 1 - k) for k in range(n)]


def dispatch_values(n: int) -> list[int]:
    """Counter values the dispatch sees, in order: 3^n down to 1."""
    return [3 ** k for k in range(n, -1, -1)]


@dataclass(frozen=True, slots=True)
class CountIn:
    image: bytes
    count: int
    steps_per_pass: tuple[int, int]
    cells: dict[str, int]
    lowering: str = LOWERING


def _layout(n: int, p: dict[str, int]):
    memory = Memory()
    z = p["Z"]
    slack_a, slack_b, pointer, budget = p["slack_a"], p["slack_b"], p["P"], p["budget"]
    if not 94 <= z < 127:
        raise Conflict("counter cell must be in 94..126")
    vals = dispatch_values(n)
    constants: list[tuple[int, int]] = [(z, 3**n)]
    memory.claim(z, seed(3**n)[0], "seed")

    table_lo = min(vals, default=1) + 5 + slack_a
    far = max(FAR, -(-(table_lo + 900) // STEP) * STEP)
    landing = far + budget
    landing += -landing % STEP
    base = (landing - 60) // LAP * LAP + LAP
    laps = Laps(memory, base)

    # head: D after the move is z-93; the dispatch move 94 positions later has D=z
    first = laps.move(z - 94)
    laps.lap = 1
    dispatch = laps.pair("move")
    if laps.off + dispatch != z:
        raise AssertionError("dispatch move would not read the counter")
    jump_a = dispatch + 5 + slack_a
    delta = jump_a - dispatch

    halt = p["halt"]
    memory.claim(halt, once("halt", halt), "halt")
    # the resume address must be a byte seed rotated up, and resume+4 a lap move
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
    move_pos = resume + 4  # four inert cells, then the lap move at residue 60

    # table: one entry per dispatched value; pass k is even for odd k, so an even
    # pass reads the cell four before v + delta
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
    output = laps.pair("output")
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
                                         rotate=rotate, output=output, back=back, landing=landing,
                                         far=far, entry=entry, Z=z, delta=delta, halt=halt,
                                         halt_entry=halt_entry, d_at_back=d_at_back)


def _build(n: int, p: dict[str, int]) -> CountIn:
    memory, laps, constants, at = _layout(n, p)
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
    names = {"Z": at["Z"], "resume": at["resume"], "halt": at["halt"], "halt_entry": at["halt_entry"],
             "landing": at["landing"], "first": at["first"], "entry": at["entry"],
             "jump_a": at["jump_a"], "jump_b": at["jump_b"], "delta": at["delta"], "far": at["far"]}
    return CountIn(image, n, (at["jump_a"] - at["landing"], at["jump_b"] - at["resume"]), names)


# Layouts found by a seeded search over the parameter space (one per count).
# The build checks every claim, so a wrong set fails loudly instead of emitting.
FROZEN: dict[int, dict[str, int]] = {
    0: {"Z": 94, "slack_a": 125, "slack_b": 30, "P": 42, "budget": 2200, "halt": 244},
    1: {"Z": 94, "slack_a": 125, "slack_b": 30, "P": 42, "budget": 2200, "halt": 244},
    2: {"Z": 94, "slack_a": 60, "slack_b": 30, "P": 42, "budget": 2200, "halt": 244},
    3: {"Z": 94, "slack_a": 60, "slack_b": 30, "P": 42, "budget": 2200, "halt": 244},
    4: {"Z": 94, "slack_a": 60, "slack_b": 30, "P": 42, "budget": 2200, "halt": 244},
    5: {"Z": 94, "slack_a": 70, "slack_b": 30, "P": 42, "budget": 3000, "halt": 244},
    6: {"Z": 94, "slack_a": 60, "slack_b": 30, "P": 42, "budget": 6000, "halt": 244},
}


def build_count_in(n: int) -> CountIn:
    """The image that prints 3^(n-1), ..., 3, 1 and halts inside the image (0 <= n <= MAX_COUNT)."""
    if not 0 <= n <= MAX_COUNT:
        raise ValueError(f"count must be in 0..{MAX_COUNT}")
    return _build(n, FROZEN[n])

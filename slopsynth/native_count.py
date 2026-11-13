"""H14: a native fixed19 loop whose state changes on every pass.

`build_countdown(n)` prints the n bytes 3^(n-1), ..., 9, 3, 1 and halts. The
counter is a memory cell holding 3^n; each pass `rotate` divides it by 3 in
place, `output` prints it, and the loop leaves when the rotated value is no
longer small. Nothing is unrolled: the same cells run on every pass.

Pass, in laps of 94 cells (see `native_asm.Laps`):

    lap 0   move        D -> Z - 93           (so that the next lap's rotate sees D = Z)
    lap 1   rotate Z    A = Z = Z / 3         (3^0 rotates to 3^17: huge)
            move        D -> Z - 94, read from cell Z + 1
    lap 2   move        reads Z itself: D = v, the new counter value
            jump        reads the cell v + 5 + slack; it holds the far address `resume`
    resume  output      prints v
            move        D -> P, read from the cell v + K + c  (one cell per v)
            jump        back to the loop head, read from the cell P + ...

The counter value is the address the dispatch `move` sends D to, so the table
the jump reads is spread over the cells v + 5 + slack, one per counter value.
After the last rotation v = 3^17: D lands in the zero-extended pattern memory
above the image (cells filled from the image's last two bytes, see
`slopsynth/model.py`). The jump there reads a pattern value p; the builder
chooses the last two image bytes so that p is a small address whose next cell
holds `halt`.

Limits: n <= 6. Counter values are table addresses, so the table spreads over
the low image, where it competes for cells with the bootstrap and the prologue
(whose far pointers are built by rotation, because a byte pointer reaches only
cells below 128); a seeded search found no layout for 8 (20 000 tries) and was stopped for 7. The loop body is
this one, and the image loads only with the raw loader.
"""

from __future__ import annotations

from dataclasses import dataclass
import itertools
import random

from .cycles import PAIR_GAP, jump_cell, padding, pair_cell
from .model import _CRAZY_TABLE
from .native_asm import FAR, LAP, STEP, Conflict, Laps, Memory, bootstrap, once, seed
from .profile import load_profile
from pathlib import Path

LOWERING = "fixed19-native-countdown-v1"
END = 3**19
FAR_VALUE = 3**17  # what rotating 3^0 gives
MAX_COUNT = 6
_PROFILE = load_profile(Path(__file__).resolve().parents[1] / "profiles/fixed19.json")
PAGE = 65536


def counter_values(n: int) -> list[int]:
    """Values printed by `countdown(n)`, in order."""
    return [3 ** (n - 1 - k) for k in range(n)]


def pattern_values(image_length: int, last_two: tuple[int, int]) -> tuple[int, ...]:
    """The six values of the periodic memory above an image of this length
    (same recurrence as `model._Memory`), without running the chain cell by cell."""
    zone = -(-image_length // PAGE) * PAGE
    steps = zone - image_length  # chain cells before the first pattern value
    older, newer = last_two
    trits = []
    for place in range(19):
        state = ((older // 3**place) % 3, (newer // 3**place) % 3)
        seen: dict[tuple[int, int], int] = {}
        order: list[tuple[int, int]] = []
        while state not in seen:  # each trit pair walks a short cycle
            seen[state] = len(order)
            order.append(state)
            state = (state[1], _CRAZY_TABLE[state[0]][state[1]])
        head, period = seen[state], len(order) - seen[state]
        state = order[steps if steps < head else head + (steps - head) % period]
        out = []
        for _ in range(6):
            state = (state[1], _CRAZY_TABLE[state[0]][state[1]])
            out.append(state[1])
        trits.append(out)
    return tuple(sum(trits[place][k] * 3**place for place in range(19)) for k in range(6))


@dataclass(frozen=True, slots=True)
class Countdown:
    image: bytes
    count: int
    steps_per_pass: tuple[int, int]
    cells: dict[str, int]
    lowering: str = LOWERING


def _layout(n: int, p: dict[str, int]):
    memory = Memory()
    z, slack_a, slack_b, pointer = p["Z"], p["slack_a"], p["slack_b"], p["P"]
    if not 94 <= z < 127:
        raise Conflict("counter cell must be in 94..126")
    memory.claim(z + 1, z - 94)
    values = counter_values(n)
    constants: list[tuple[int, int]] = [(z, 3**n)]
    memory.claim(z, seed(3**n)[0], "seed")

    table_end = max(values, default=0) + PAIR_GAP + 1 + slack_a
    far = max(FAR, -(-(table_end + 320) // STEP) * STEP)  # the prologue starts above every table cell
    landing = far + p["budget"]
    landing += -landing % STEP
    base = (landing - 60) // LAP * LAP + LAP
    laps = Laps(memory, base)
    first = laps.move(z - 93)
    laps.lap = 1
    rotate = laps.pair("rotate")
    if laps.off + rotate != z:
        raise AssertionError("rotate would miss the counter")
    laps.move(z - 94, exact=True)
    laps.lap = 2
    dispatch = laps.pair("move")
    if laps.off + dispatch != z:
        raise AssertionError("dispatch move would miss the counter")
    jump_a = dispatch + PAIR_GAP + 1 + slack_a
    resume = jump_a + 1 + (-(jump_a + 1) % STEP)
    delta = jump_a - dispatch
    # pass k (1-based) is even for odd k: an even pass reads v + delta, an odd one v + delta - 4
    for k, v in enumerate(values, start=1):
        constants.append((v + delta - (0 if k % 2 else PAIR_GAP), resume))
    exit_parity_odd = (n + 1) % 2 == 0
    exit_cell = FAR_VALUE + delta - (PAIR_GAP if exit_parity_odd else 0)

    laps.lap = (resume - base) // LAP
    if laps.position(laps.lap, "output") <= resume:
        laps.lap += 1
    laps.pair("output")
    k_off = delta - resume  # D = v + k_off + c between resume and the next move
    back = laps.position(laps.lap, "move")
    for k, v in enumerate(values, start=1):
        memory.claim(v + k_off + back, pointer)
    laps.pair("move")
    laps.off = pointer - back
    jump_b = back + PAIR_GAP + 1 + slack_b
    for lag in (0, PAIR_GAP):
        constants.append((laps.off + jump_b - lag, landing))
    entry = laps.off + jump_b - landing + first
    for lag in (-PAIR_GAP, PAIR_GAP):
        memory.claim(entry + lag, z - 93)
    for address, value in constants:
        if address != z:
            memory.claim(address, seed(value)[0], "seed")
    return memory, laps, constants, dict(first=first, jump_a=jump_a, jump_b=jump_b, resume=resume,
                                         landing=landing, far=far, exit_cell=exit_cell, entry=entry, Z=z, delta=delta)


@dataclass(slots=True)
class _Prepared:
    memory: Memory
    laps: Laps
    at: dict[str, int]
    end: int


def _prepare(n: int, p: dict[str, int]) -> _Prepared:
    """Everything that does not depend on the last two image bytes."""
    if not 0 <= n <= MAX_COUNT:
        raise ValueError(f"count must be in 0..{MAX_COUNT}")
    memory, laps, constants, at = _layout(n, p)
    first, landing = at["first"], at["landing"]
    code = bootstrap(memory, at["far"])
    for address, value in constants:
        code.at(address, "rotate", seed(value)[1])
    for _ in range(250):
        pointer = at["entry"] - PAIR_GAP - (first - code.c)
        if code.c >= landing:
            raise Conflict("prologue is longer than its budget")
        if 0 <= pointer < 128 and memory.fits(code.d, pointer):
            code.emit("move")
            break
        code.nop()
    else:
        raise Conflict("no entry pointer")
    return _Prepared(memory, laps, at, max(at["jump_b"], max(memory.cells)))


def exit_target(prep: _Prepared, tail: tuple[int, int]) -> int | None:
    """Address the exit jump reads from pattern memory, if it can be made to halt."""
    pattern = pattern_values(prep.end + 1 + len(tail), tail)
    target = pattern[_phase(prep.at["exit_cell"])]
    if 0 <= target < 127 and prep.memory.free(target + 1):
        return target
    return None


def _finish(n: int, prep: _Prepared, tail: tuple[int, int]) -> Countdown:
    memory, laps, at, end = prep.memory, prep.laps, prep.at, prep.end
    target = exit_target(prep, tail)
    if target is None:
        raise Conflict("the exit cell does not read a small address with a free cell after it")
    cells: list[int | None] = [None] * (end + 1)
    for address, (value, _) in memory.cells.items():
        cells[address] = value
    cells[target + 1] = once("halt", target + 1)
    for name, where in laps.pairs:
        for offset, first_cell in ((0, True), (PAIR_GAP, False)):
            if cells[where + offset] is not None:
                raise Conflict("loop cells overlap")
            cells[where + offset] = pair_cell(name, where + offset, first_cell)
    for where in (at["jump_a"], at["jump_b"]):
        if cells[where] is not None:
            raise Conflict("jump overlaps")
        cells[where] = jump_cell(where)
    body = bytes((padding(i) if i >= at["far"] else 0) if v is None else v for i, v in enumerate(cells))
    names = {"Z": at["Z"], "landing": at["landing"], "resume": at["resume"], "exit_cell": at["exit_cell"],
             "halt": target + 1, "delta": at["delta"], "jump_a": at["jump_a"], "jump_b": at["jump_b"]}
    return Countdown(body + bytes(tail), n, (at["jump_b"] - at["landing"],) * 2, names)


def _build(n: int, p: dict[str, int], tail: tuple[int, int]) -> Countdown:
    return _finish(n, _prepare(n, p), tail)


def _phase(address: int) -> int:
    page = address & ~(PAGE - 1)
    return (page % (END // 3) + address - page) % 6


FROZEN: dict[int, tuple[dict[str, int], tuple[int, int]]] = {
    0: ({'Z': 94, 'slack_a': 24, 'slack_b': 13, 'P': 108, 'budget': 380}, (0, 29)),
    1: ({'Z': 115, 'slack_a': 32, 'slack_b': 27, 'P': 48, 'budget': 340}, (0, 29)),
    2: ({'Z': 94, 'slack_a': 28, 'slack_b': 17, 'P': 58, 'budget': 280}, (0, 32)),
    3: ({'Z': 95, 'slack_a': 33, 'slack_b': 14, 'P': 112, 'budget': 780}, (0, 29)),
    4: ({'Z': 125, 'slack_a': 35, 'slack_b': 14, 'P': 88, 'budget': 440}, (0, 29)),
    5: ({'Z': 114, 'slack_a': 31, 'slack_b': 6, 'P': 47, 'budget': 260}, (0, 29)),
    6: ({'Z': 97, 'slack_a': 30, 'slack_b': 23, 'P': 51, 'budget': 1440}, (0, 29)),
}


def build_countdown(n: int) -> Countdown:
    """The image that prints 3^(n-1), ..., 3, 1 and halts (0 <= n <= MAX_COUNT)."""
    if n not in FROZEN:
        raise ValueError(f"count must be in 0..{MAX_COUNT}")
    params, tail = FROZEN[n]
    return _build(n, params, tail)


def search(n: int = 3, seed_value: int = 1) -> tuple[dict[str, int], tuple[int, int]]:
    """Layout parameters and the last two image bytes that make `countdown(n)` halt."""
    rng = random.Random(seed_value)
    for _ in range(20_000):
        p = {"Z": rng.randrange(94, 127), "slack_a": rng.randrange(0, 40), "slack_b": rng.randrange(0, 40),
             "P": rng.randrange(0, 128), "budget": rng.randrange(150, 400 + 250 * n, 10)}
        try:
            prep = _prepare(n, p)
        except Conflict:
            continue
        for tail in itertools.product(range(128), repeat=2):
            if exit_target(prep, tail) is not None:
                return p, tail
    raise RuntimeError("no layout found")

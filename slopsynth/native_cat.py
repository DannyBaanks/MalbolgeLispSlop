"""H13b: a native fixed19 `cat` that halts at end of input.

The loop of H13a is extended with an end-of-input test. Every pass reads one
byte, decides between "byte" and "EOF" with two `crazy` cells and a `move`
through the result, prints the byte and puts the two cells back.

The test (trits, least significant first; EOF is the word of nineteen 2s):

    in            A = b
    crazy Y       Y = ones         ->  b with 0 and 1 swapped below, 1s above
    crazy W       W = 850          ->  b for a byte, 1700 for EOF; A = W
    move (D at W) D = b + 1  or  1701
    move          table of 256 equal pointers for bytes, one other cell for EOF
    jump          continue  or  land next to a `halt`

W = 850 has 1s in trits 0..4 and 6. Trit 6 is what separates EOF from byte
242, which shares its low five trits. Afterwards A still holds b, so `out`
prints it, and seven more `crazy` plus one `rotate` restore Y and W:

    crazy W, crazy Y, crazy Y    both cells now hold words over {0, 1}
    rotate Z                     A = 0
    crazy Y                      Y = ones, A = ones
    crazy U                      U = 1700 is unchanged, A = 1700
    crazy V                      V = ones - 850 is unchanged, A = V
    crazy W                      W = 850

Layout. Image bytes must stay below 128 (upstream `fast20.c` loads them as
signed chars), so every D pointer is below 128 and all data lives in low
memory. The loop is far above it, and its two jump targets and the words 850,
1700, ones - 850 and ones do not fit in a byte. A one-shot prologue makes them
from byte seeds with `rotate` (18 - k rotations multiply by 3^k) and `crazy`.

    0..        bootstrap: rotates one seed into the prologue address, jumps
    41..       data: seeds, Y W U V Z, pointer cells, halt stub
    376..631   byte table           2076  EOF table cell
    far        prologue, then the loop (straight laps of 94 cells)

Loop cells are the alternating pairs of `cycles.py`. Within a pass the second
cell of a pair runs four steps after the first would, so on odd passes D lags
by four; each jump therefore has two operand cells four apart, and the first
`move` of a pass has two, eight apart.

Limits: the image loads only with the raw loader (inert cells are not valid
opcodes). The body is fixed: this is `cat`, not a compiler for loops.
"""

from __future__ import annotations

from dataclasses import dataclass

from .cycles import PAIR_GAP, jump_cell, padding, pair_cell, pair_residue
from .native_asm import FAR, LAP, STEP, BOOT_CELL, bootstrap, Conflict, Laps, Memory, Once, once, seed as byte_seed

LOWERING = "fixed19-native-cat-v1"
TABLE_LAPS = 4            # laps between the dispatch move and the table move
EOF_WORD = 1700           # value of W after reading EOF
# Addresses found by `search()`; the build checks every claim, so a bad set fails loudly.
PARAMS = {"Y": 68, "W": 111, "U": 113, "V": 72, "table": 94, "eof": 65, "halt": 45, "slack": 9, "budget": 470}


@dataclass(frozen=True, slots=True)
class Cat:
    image: bytes
    loop_head: int
    loop_end: int
    steps_per_byte: int
    cells: dict[str, int]
    lowering: str = LOWERING


def _build(p: dict[str, int]) -> Cat:
    memory = Memory()
    y, w, u, v = p["Y"], p["W"], p["U"], p["V"]
    for name, seed in (("Y", 0), ("W", 0), ("V", 0), ("U", 2)):
        memory.claim(p[name], seed, name)

    # ---- loop, in the timeline of an even pass: D = off + C between moves
    landing = FAR + p["budget"]
    landing += -landing % STEP                    # the loop-back jump lands here
    base = (landing - pair_residue("input")) // LAP * LAP + LAP  # first lap whose input pair is past the landing
    laps = Laps(memory, base)
    pairs = laps.pairs
    constants: list[tuple[int, int]] = []
    pair, move, crazy, access = laps.pair, laps.move, laps.crazy, laps.access
    position = laps.position
    pair("input", 0)
    first_move = move(y - 22)                     # its two pointer cells are claimed at the end
    crazy(y)
    access(w)
    move(w - LAP, exact=True)                     # next lap's move finds D at W
    laps.lap += 1
    dispatch = pair("move", laps.lap)         # D = W + 1: b + 1, or 1701
    laps.lap += TABLE_LAPS
    table_move = pair("move", laps.lap)
    table = table_move - dispatch
    for byte in range(256):
        memory.claim(table + byte, p["table"])
    memory.claim(table + EOF_WORD, p["eof"])
    jump_a = table_move + PAIR_GAP + 1
    resume = jump_a + 1 + (-(jump_a + 1) % STEP)  # continue after this cell
    for lag in (0, PAIR_GAP):
        constants.append((p["table"] + 5 - lag, resume))
        memory.claim(p["eof"] + 5 - lag, p["halt"])
    halt_at = p["halt"] + 1
    memory.claim(halt_at, once("halt", halt_at), "halt")
    laps.off = p["table"] + 5 - resume
    laps.lap = (resume - base) // LAP
    if position(laps.lap, "output") <= resume:
        laps.lap += 1
    pair("output", laps.lap)
    access(w)
    access(y)
    access(y)
    rotate_lap = laps.lap
    while True:                                    # rotate Z sits one step before the next move
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
    last = move(w - 22)
    crazy(w)
    jump_b = last + 22 + PAIR_GAP + 1 + p["slack"]
    for lag in (0, PAIR_GAP):
        constants.append((laps.off + jump_b - lag, landing))
    entry = laps.off + jump_b - landing + first_move
    for lag in (-PAIR_GAP, PAIR_GAP):
        memory.claim(entry + lag, y - 22)
    for address, value in constants:
        memory.claim(address, byte_seed(value)[0], "seed")

    # ---- one-shot code: bootstrap at 0, prologue at FAR
    def scratch(seed):
        for address in range(33, 127):
            if all(memory.free(address + i) for i in range(4)):
                memory.claim(address, seed, "scratch")
                return address
        raise Conflict("no room for a prologue cell")

    code = bootstrap(memory)
    for address, value in constants:
        code.at(address, "rotate", byte_seed(value)[1])
    s1, c125, c121, temp, zero_p = (scratch(seed) for seed in (26, 125, 121, 0, 0))
    code.at(u, "rotate", 12)                       # U = 2 * 3^6
    code.at(s1, "rotate", 16)                      # A = 234
    code.at(c125, "crazy")                         # 2s in trits 0..4, 1s above
    code.at(c121, "crazy")                         # A = 242
    code.at(temp, "crazy")                         # A = ones - 121
    code.at(u, "crazy")                            # U = 1579
    code.at(zero_p, "rotate")                      # A = 0
    code.at(c125, "crazy")                         # reload, unchanged
    code.at(u, "crazy")                            # U = 1700
    code.at(v, "crazy")                            # V = ones - 850
    code.at(w, "crazy")                            # W = 850
    code.at(zero_p, "rotate")
    code.at(y, "crazy")                            # Y = ones
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
    names = {"Y": y, "W": w, "U": u, "V": v, "Z": zero, "table": table, "eof_cell": table + EOF_WORD,
             "halt": halt_at, "prologue": FAR + 1, "landing": landing, "resume": resume}
    return Cat(image, landing, end, (jump_a - landing) + (jump_b - resume), names)


def build_cat() -> Cat:
    return _build(PARAMS)


def search(seed: int = 1, tries: int = 200_000) -> dict[str, int]:
    """Find a set of addresses for which every claim is consistent."""
    import random
    rng = random.Random(seed)
    for _ in range(tries):
        p = {"Y": rng.randrange(43, 128), "W": rng.randrange(94, 124), "U": rng.randrange(43, 128),
             "V": rng.randrange(43, 128), "table": rng.randrange(43, 122), "eof": rng.randrange(0, 123),
             "halt": rng.randrange(1, 127), "slack": rng.randrange(0, 12), "budget": rng.randrange(250, 700, 10)}
        try:
            _build(p)
        except Conflict:
            continue
        return p
    raise RuntimeError("no layout found")

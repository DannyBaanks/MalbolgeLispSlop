"""H22: chained two-accumulator cipher — a composition of two lap-safe `crazy`
updates per pass, input-driven.

Built on H20's two-read loop (selector + payload, H13b EOF identity, in-image
`halt`). In the resume path, after reading the payload `b` (A = b):

    access(ACC1)   ACC1' = crazy(ACC1, A=b)    tritwise TBL[ACC1][b]; A = ACC1'
    access(ACC2)   ACC2' = crazy(ACC2, A=ACC1') tritwise TBL[ACC2][ACC1']; A = ACC2'
    output         print ACC2' & 0xFF

So each pass rewrites **two** data cells with `crazy`, the second one's mask being
the first one's fresh result (the chain flows through A, so no mask needs
restoring). The loop halts inside the image at a zero selector or EOF; the same
cells run every pass and no memory above the image is read (model bound
`max_address = len(image)-1`).

`reference(stdin)` computes the expected bytes from the op order alone with the
model primitive `_crazy`. The image is 4 979 cells, largest byte below 128, raw
loader only. Addresses: H20's frozen layout plus `ACC2 = 43`; the build checks
every cell claim.
"""

from __future__ import annotations

from dataclasses import dataclass

from .cycles import PAIR_GAP, jump_cell, padding, pair_cell, pair_residue
from .model import _crazy
from .native_asm import FAR, LAP, STEP, Conflict, Laps, Memory, bootstrap, once, seed as byte_seed
from .native_cipher import ACC0
from .native_ir_loop import EOF_WORD, TABLE_LAPS
from .profile import load_profile
from pathlib import Path

LOWERING = "fixed19-native-cipher2-v1"
ACC10 = ACC0   # first accumulator seed
ACC20 = 7      # second accumulator seed
_PROFILE = load_profile(Path(__file__).resolve().parents[1] / "profiles/fixed19.json")
EOF_VALUE = _PROFILE.eof_value


def reference(stdin: bytes) -> bytes:
    """Output of the H22 loop on `stdin`: ACC2' & 0xFF per (selector, payload) pass."""
    out = bytearray()
    acc1, acc2 = ACC10, ACC20
    idx = 0
    while idx < len(stdin):
        s = stdin[idx]
        idx += 1
        if s == 0:
            break
        b = stdin[idx] if idx < len(stdin) else EOF_VALUE
        if idx < len(stdin):
            idx += 1
        acc1 = _crazy(b, acc1, 19)        # D=ACC1, A=b
        acc2 = _crazy(acc1, acc2, 19)     # D=ACC2, A=ACC1'
        out.append(acc2 & 0xFF)
    return bytes(out)


def chains(stdin: bytes) -> tuple[list[int], list[int]]:
    """Full per-pass values of both accumulators (for write traces)."""
    a1, a2 = ACC10, ACC20
    c1, c2 = [], []
    idx = 0
    while idx < len(stdin):
        s = stdin[idx]
        idx += 1
        if s == 0:
            break
        b = stdin[idx] if idx < len(stdin) else EOF_VALUE
        if idx < len(stdin):
            idx += 1
        a1 = _crazy(b, a1, 19)
        a2 = _crazy(a1, a2, 19)
        c1.append(a1)
        c2.append(a2)
    return c1, c2


@dataclass(frozen=True, slots=True)
class Cipher2:
    image: bytes
    cells: dict[str, int]
    lowering: str = LOWERING


def _build(p: dict[str, int]) -> Cipher2:
    memory = Memory()
    y, w, u, v, acc, acc2 = p["Y"], p["W"], p["U"], p["V"], p["ACC"], p["ACC2"]
    for name, s in (("Y", 0), ("W", 0), ("V", 0), ("U", 2), ("ACC", ACC10), ("ACC2", ACC20)):
        memory.claim(p[name], s, name)
    landing = FAR + p["budget"]
    landing += -landing % STEP
    base = (landing - pair_residue("input")) // LAP * LAP + LAP
    laps = Laps(memory, base)
    pairs = laps.pairs
    pair, move, crazy, access = laps.pair, laps.move, laps.crazy, laps.access
    position = laps.position
    constants: list[tuple[int, int]] = []

    def put(name, after):
        at = position(laps.lap, name)
        while at <= after:
            laps.lap += 1
            at = position(laps.lap, name)
        return pair(name)

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
    access(w)
    access(y)
    access(y)
    rotate_lap = laps.lap
    while True:
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
    payload = put("input", last)      # A = b
    access(acc)                        # ACC1' = crazy(ACC1, A=b); A = ACC1'
    access(acc2)                       # ACC2' = crazy(ACC2, A=ACC1'); A = ACC2'
    printed = put("output", payload)   # print ACC2'
    back = move(p["P"])
    jump_b = back + 22 + PAIR_GAP + 1 + p["slack"]
    for lag in (0, PAIR_GAP):
        constants.append((laps.off + jump_b - lag, landing))
    entry = laps.off + jump_b - landing + first_move
    for lag in (-PAIR_GAP, PAIR_GAP):
        memory.claim(entry + lag, y - 22)
    for address, value in constants:
        memory.claim(address, byte_seed(value)[0], "seed")

    def scratch(s):
        for address in range(33, 127):
            if all(memory.free(address + i) for i in range(4)):
                memory.claim(address, s, "scratch")
                return address
        raise Conflict("no room for a prologue cell")

    code = bootstrap(memory)
    for address, value in constants:
        code.at(address, "rotate", byte_seed(value)[1])
    s1, c125, c121, temp, zero_p = (scratch(s) for s in (26, 125, 121, 0, 0))
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
    names = {"Y": y, "W": w, "U": u, "V": v, "ACC": acc, "ACC2": acc2, "table": table,
             "eof_cell": table + EOF_WORD, "halt": halt_at, "landing": landing,
             "resume": resume, "jump_a": jump_a, "jump_b": jump_b, "P": p["P"]}
    return Cipher2(image, names)


# H20's frozen layout plus the second accumulator cell. The build checks every
# claim, so a bad set fails loudly.
PARAMS = {"Y": 82, "W": 114, "U": 115, "V": 45, "ACC": 125, "ACC2": 43, "table": 60,
          "eof": 51, "halt": 59, "slack": 3, "budget": 280, "P": 68}


def build_cipher2() -> Cipher2:
    """The image that chains two `crazy` accumulators per payload byte and halts in-image at 0/EOF."""
    return _build(PARAMS)

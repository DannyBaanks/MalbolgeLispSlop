"""H20: an input-driven native loop with lap-safe `crazy` arithmetic.

Built on H15's two-read loop (selector + payload, H13b's EOF identity, in-image
`halt`). Each pass:

    read selector s          (EOF word or a byte)
    identity (two `crazy`)   byte s -> s, EOF -> 1700
    dispatch table on s      s == 0 or EOF -> the in-image halt; else resume
    restore Y and W          (A still holds the selector, as in H15)
    read payload b           A = b (or the EOF word on truncated input)
    access(ACC)              ACC' = crazy(ACC, A=b)  tritwise TBL[ACC][b]; A = ACC'
    output                   print ACC' & 0xFF
    move+jump                back to the head

So the accumulator cell `ACC` is rewritten by a `crazy` whose mask is the *input
byte* on every pass — input-driven lap-safe arithmetic — and the loop halts
inside the image at a zero selector or EOF. The same cells run every pass; no
memory above the image is read (the model runs with `max_address = len(image)-1`).

`reference(stdin)` mirrors `native_ir_loop.reference` but accumulates: it reads
(selector, payload) pairs, stops at a zero selector, and appends
`ACC' & 0xFF` after each payload (the EOF word if the payload is truncated).

The image loads only with the raw loader (inert cells, as H13a..H19).
"""

from __future__ import annotations

from dataclasses import dataclass

from .cycles import PAIR_GAP, jump_cell, padding, pair_cell, pair_residue
from .model import _crazy
from .native_asm import FAR, LAP, STEP, Conflict, Laps, Memory, bootstrap, once, seed as byte_seed
from .native_ir_loop import EOF_WORD, TABLE_LAPS
from .profile import load_profile
from pathlib import Path

LOWERING = "fixed19-native-cipher-v1"
ACC0 = 5  # accumulator seed (an image byte)
_PROFILE = load_profile(Path(__file__).resolve().parents[1] / "profiles/fixed19.json")
EOF_VALUE = _PROFILE.eof_value


def reference(stdin: bytes) -> bytes:
    """Output of the H20 loop on `stdin`: ACC' & 0xFF per (selector, payload) pass."""
    out = bytearray()
    acc = ACC0
    idx = 0
    while idx < len(stdin):
        selector = stdin[idx]
        idx += 1
        if selector == 0:
            break
        payload = stdin[idx] if idx < len(stdin) else EOF_VALUE
        if idx < len(stdin):
            idx += 1
        acc = _crazy(payload, acc, 19)  # D=ACC, A=payload -> TBL[acc][payload]
        out.append(acc & 0xFF)
    return bytes(out)


def acc_chain(stdin: bytes) -> list[int]:
    """The full accumulator values after each pass (for write traces)."""
    acc = ACC0
    chain = []
    idx = 0
    while idx < len(stdin):
        s = stdin[idx]
        idx += 1
        if s == 0:
            break
        b = stdin[idx] if idx < len(stdin) else EOF_VALUE
        if idx < len(stdin):
            idx += 1
        acc = _crazy(b, acc, 19)
        chain.append(acc)
    return chain


@dataclass(frozen=True, slots=True)
class Cipher:
    image: bytes
    cells: dict[str, int]
    lowering: str = LOWERING


def _build(p: dict[str, int]) -> Cipher:
    memory = Memory()
    y, w, u, v, acc = p["Y"], p["W"], p["U"], p["V"], p["ACC"]
    for name, s in (("Y", 0), ("W", 0), ("V", 0), ("U", 2), ("ACC", ACC0)):
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

    # resume path: restore Y and W while A still holds the selector byte
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
    payload = put("input", last)      # A = b (payload byte or the EOF word)
    access(acc)                        # ACC' = crazy(ACC, A=b); A = ACC'  (the H20 arithmetic)
    printed = put("output", payload)   # print ACC'
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
    names = {"Y": y, "W": w, "U": u, "V": v, "ACC": acc, "table": table, "eof_cell": table + EOF_WORD,
             "halt": halt_at, "landing": landing, "resume": resume, "jump_a": jump_a, "jump_b": jump_b, "P": p["P"]}
    return Cipher(image, names)


# Addresses found by `search()`; the build checks every claim, so a bad set fails loudly.
PARAMS = {"Y": 82, "W": 114, "U": 115, "V": 45, "ACC": 125, "table": 60,
          "eof": 51, "halt": 59, "slack": 3, "budget": 280, "P": 68}


def build_cipher() -> Cipher:
    """The image that accumulates each payload byte with `crazy` and halts in-image at 0/EOF."""
    return _build(PARAMS)

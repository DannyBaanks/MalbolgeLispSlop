"""H32: Re-executable fixed19 nested Lisp S-expression evaluator loop.

Evaluates a stream of 13-byte depth-2 nested binary S-expressions of both
tree shapes in a single native re-executable loop, halting in-image on `0` or
EOF:

* Right-nested: `(op1 a (op2 b c))` — e.g. `(+ 2 (- 9 4))` -> `'7'`
* Left-nested:  `(op1 (op2 a b) c)` — e.g. `(- (+ 3 6) 4)` -> `'5'`

where `op1, op2 in {'+', '-'}` and `a, b, c in '0'..'9'`.

Architecture:
1. Byte 5 (`t5_reg`) is `'('` (`40 = [1, 1, 1, 1]_3`, trit 2 == 1) in
   right-nested expressions and `' '` (`32 = [2, 1, 0, 1]_3`, trit 2 == 0) in
   left-nested expressions. Extracting trit 2 with `keep(t5_reg, k9)` and
   broadcasting to trits 0..3 yields Complementary 4-trit masks `m_right` and
   `m_left`.
2. A 2-frame evaluation stack normalizes and evaluates the inner sub-expression
   `inner_res = eval_op(op_in, x_in, y_in)` first, then substitutes `inner_res`
   into the outer frame `(op1, x_out, y_out)` to produce and output `outer_res`.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._native_eval_add import UNARY
from .cycles import PAIR_GAP, jump_cell, padding, pair_cell, pair_residue
from .native_asm import LAP, STEP, Conflict, Laps, Memory, bootstrap, once, seed as byte_seed
from .native_ir_loop import EOF_WORD, TABLE_LAPS

LOWERING = "fixed19-native-lisp-nested-v1"
_PAD = tuple(padding(i) for i in range(94))

PARAMS = {
    "Y": 82, "W": 114, "U": 115, "V": 45, "C2": 125, "M80": 126,
    "table": 60, "eof": 51, "halt": 59, "slack": 3, "budget": 1000, "P": 68,
    "far": 80 * STEP,
}


def _eval_bin(op: int, a_ascii: int, b_ascii: int) -> int:
    if op == ord("+"):
        return (a_ascii + (b_ascii - 48)) % 81
    return (a_ascii - (b_ascii - 48)) % 81


def reference(stdin: bytes) -> bytes:
    """Expected stdout of the H32 nested S-expression loop on 13-byte frames."""
    out = bytearray()
    idx = 0
    while idx < len(stdin):
        if stdin[idx] == 0:
            break
        if idx + 13 > len(stdin):
            break
        frame = stdin[idx : idx + 13]
        op1 = frame[1]
        if frame[5] == ord("("):
            # Right-nested: (op1 a (op2 b c))
            a = frame[3]
            op2 = frame[6]
            b = frame[8]
            c = frame[10]
            inner = _eval_bin(op2, b, c)
            outer = _eval_bin(op1, a, inner)
        else:
            # Left-nested: (op1 (op2 a b) c)
            op2 = frame[4]
            a = frame[6]
            b = frame[8]
            c = frame[11]
            inner = _eval_bin(op2, a, b)
            outer = _eval_bin(op1, inner, c)
        out.append(outer & 0xFF)
        idx += 13
    return bytes(out)


@dataclass(frozen=True, slots=True)
class LispNestedRepl:
    image: bytes
    cells: dict[str, int]
    lowering: str = LOWERING


def build_lisp_nested(rounds: int = 3, params: dict[str, int] | None = None) -> LispNestedRepl:
    p = PARAMS if params is None else params
    memory = Memory()
    y, w, u, v, c2, m80 = p["Y"], p["W"], p["U"], p["V"], p["C2"], p["M80"]
    for name, s in (("Y", 0), ("W", 0), ("V", 0), ("U", 2), ("C2", 0), ("M80", 0)):
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
            if lap > laps.lap + 240:
                raise Conflict(f"no room for pointer {pointer}")
        pair("move", lap)
        laps.off = pointer - at
        laps.lap = lap
        return at

    def access_any(cell: int) -> None:
        move_any(cell - 22)
        crazy(cell)

    def rotate_reg(cell: int) -> None:
        move_any(cell - 93)
        laps.lap += 1
        pair("rotate", laps.lap)

    def zero_and_access(target_cell: int) -> None:
        rot_lap = laps.lap
        while True:
            z = laps.off + position(rot_lap, "rotate")
            if (memory.free(z) or memory.cells.get(z) == (0, "zero")) and memory.fits(z + 1, target_cell - 22):
                break
            rot_lap += 1
            if rot_lap > laps.lap + 240:
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
    jb_d = p["P"] + 22 + PAIR_GAP + 1 + p["slack"]
    for lag in (0, PAIR_GAP):
        constants.append((jb_d - lag, landing))
    entry = jb_d - landing + first_move
    for lag in (-PAIR_GAP, PAIR_GAP):
        memory.claim(entry + lag, y - 22)

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
    for address, value in constants:
        memory.claim(address, byte_seed(value)[0], "seed")

    reg_pool = [r for r in range(128, 150) if memory.free(r)]
    k9 = reg_pool.pop(0)
    k33 = reg_pool.pop(0)
    k36 = reg_pool.pop(0)
    k49 = reg_pool.pop(0)
    tmp_copy = reg_pool.pop(0)
    memory.claim(k9, 9, "k9")
    memory.claim(k33, 33, "k33")
    memory.claim(k36, 36, "k36")
    memory.claim(k49, 49, "k49")
    memory.claim(tmp_copy, 0, "tmp_copy")
    for r in reg_pool:
        memory.claim(r, 0, f"reg_{r}")
    free_regs = list(reg_pool)

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

    def alloc() -> int:
        return free_regs.pop(0)

    def drop(r: int) -> None:
        free_regs.append(r)

    def ctrl(k: int, r: int) -> None:
        if k == 0:
            zero_and_access(r)
        elif k == 1:
            zero_and_access(y)
            access_any(r)
        elif k == 2:
            zero_and_access(c2)
            access_any(r)

    def reset(r: int, k: int = 1) -> None:
        ctrl(1, r)
        ctrl(2, r)
        ctrl(0, r)
        if k == 0:
            ctrl(1, r)
        elif k == 2:
            ctrl(2, r)

    def load(r: int) -> None:
        ctrl(2, r)
        ctrl(2, r)

    def mask_low4(r: int) -> int:
        zero_and_access(m80)
        access_any(r)
        zero_and_access(m80)
        access_any(r)
        return r

    def copy(src: int, dst: int | None = None) -> int:
        if dst is None:
            dst = alloc()
        reset(tmp_copy, 1)
        reset(dst, 1)
        load(src)
        access_any(tmp_copy)
        access_any(dst)
        return dst

    def uniform(k: int) -> int:
        r = alloc()
        reset(r, k)
        return r

    def unary_ip(r: int, tbl: tuple[int, int, int]) -> int:
        for kind, k in UNARY[tbl]:
            if kind == "ctrl":
                ctrl(k, r)
            else:
                dst = uniform(k)
                load(r)
                access_any(dst)
                drop(r)
                r = dst
        return r

    def un(src: int, tbl: tuple[int, int, int]) -> int:
        return unary_ip(copy(src), tbl)

    def cz_consume(a_reg: int, b_r: int) -> int:
        load(a_reg)
        access_any(b_r)
        drop(a_reg)
        return b_r

    def shl(r: int) -> int:
        for _ in range(17):
            rotate_reg(r)
        return r

    def s_full(x: int, y_r: int) -> int:
        left = cz_consume(copy(x), un(y_r, (0, 2, 1)))
        left = unary_ip(left, (2, 1, 0))
        right = cz_consume(un(x, (0, 2, 1)), un(y_r, (2, 2, 0)))
        right = unary_ip(right, (0, 2, 1))
        return cz_consume(left, right)

    def g_full(x: int, y_r: int) -> int:
        g = cz_consume(un(x, (0, 2, 1)), un(y_r, (2, 1, 0)))
        return unary_ip(g, (1, 0, 0))

    def s_01(s: int, c: int) -> int:
        left = cz_consume(copy(s), un(c, (0, 2, 1)))
        right = cz_consume(copy(s), un(s, (0, 2, 0)))
        return unary_ip(cz_consume(left, right), (0, 2, 1))

    def g_01(s: int, c: int) -> int:
        return unary_ip(cz_consume(copy(s), copy(c)), (0, 0, 1))

    def keep(v_r: int, m_r: int) -> int:
        left = cz_consume(copy(v_r), un(v_r, (0, 2, 1)))
        right = cz_consume(un(v_r, (1, 1, 2)), un(m_r, (0, 2, 1)))
        right = unary_ip(right, (0, 2, 1))
        return unary_ip(cz_consume(left, right), (0, 2, 1))

    def oradd(x: int, y_r: int) -> int:
        return unary_ip(cz_consume(un(x, (2, 1, 0)), un(y_r, (1, 0, 2))), (1, 2, 0))

    def add_in_loop(x: int, y_r: int, rnds: int) -> int:
        s = s_full(x, y_r)
        c = shl(g_full(x, y_r))
        for _ in range(rnds):
            s2 = s_01(s, c)
            c2_r = shl(g_01(s, c))
            drop(s)
            drop(c)
            s, c = s2, c2_r
        drop(c)
        return s

    def read_into(skip_before: int = 0) -> int:
        dst = alloc()
        reset(tmp_copy, 1)
        reset(dst, 1)
        after = position(laps.lap - 1, "crazy")
        for _ in range(skip_before + 1):
            after = put("input", after)
        access_any(tmp_copy)
        access_any(dst)
        return dst

    def eval_op(op_r: int, a_r: int, b_r: int) -> int:
        op_rel = mask_low4(add_in_loop(op_r, k36, rounds))
        drop(op_r)
        m_plus = mask_low4(unary_ip(op_rel, (0, 1, 1)))
        m_minus = mask_low4(un(m_plus, (1, 0, 0)))

        y_plus = mask_low4(add_in_loop(b_r, k33, rounds))
        b_comp = mask_low4(un(b_r, (2, 1, 0)))
        drop(b_r)
        y_minus = mask_low4(add_in_loop(b_comp, k49, rounds))
        drop(b_comp)

        kp = keep(y_plus, m_plus)
        km = keep(y_minus, m_minus)
        drop(y_plus)
        drop(y_minus)
        drop(m_plus)
        drop(m_minus)
        y_sel = oradd(kp, km)
        drop(kp)
        drop(km)

        res = mask_low4(add_in_loop(a_r, y_sel, rounds))
        drop(a_r)
        drop(y_sel)
        return res

    # Read 13-byte nested frame (byte 0 '(' already read at loop head):
    # idx 1: op1
    op1_reg = read_into(skip_before=0)
    # idx 2: ' ', idx 3: t3
    t3_reg = read_into(skip_before=1)
    # idx 4: t4
    t4_reg = read_into(skip_before=0)
    # idx 5: t5 ('(' = 40 in right-nested, ' ' = 32 in left-nested)
    t5_reg = read_into(skip_before=0)
    # idx 6: t6
    t6_reg = read_into(skip_before=0)
    # idx 7: ' ', idx 8: b
    b_reg = read_into(skip_before=1)
    # idx 9: ' ' or ')', idx 10: t10
    t10_reg = read_into(skip_before=1)
    # idx 11: t11
    t11_reg = read_into(skip_before=0)
    # idx 12: ')'
    last = position(laps.lap - 1, "crazy")
    put("input", last)

    # Compute tree-shape masks m_right and m_left from trit 2 of t5_reg:
    b2 = keep(t5_reg, k9)
    drop(t5_reg)
    b1 = copy(b2)
    rotate_reg(b1)
    b21 = oradd(b2, b1)
    drop(b2)
    drop(b1)
    b32 = shl(copy(b21))
    b10 = copy(b21)
    rotate_reg(b10)
    drop(b21)
    m_right = mask_low4(oradd(b32, b10))
    drop(b32)
    drop(b10)
    m_left = mask_low4(un(m_right, (1, 0, 0)))

    def mux(r_right: int, r_left: int) -> int:
        kr = keep(r_right, m_right)
        kl = keep(r_left, m_left)
        out_r = oradd(kr, kl)
        drop(kr)
        drop(kl)
        return out_r

    # Inner frame: right=(t6, b, t10), left=(t4, t6, b)
    op_in = mux(t6_reg, t4_reg)
    drop(t4_reg)
    x_in = mux(b_reg, t6_reg)
    drop(t6_reg)
    y_in = mux(t10_reg, b_reg)
    drop(b_reg)
    drop(t10_reg)

    inner_res = eval_op(op_in, x_in, y_in)

    # Outer frame: right=(op1, t3, inner_res), left=(op1, inner_res, t11)
    x_out = mux(t3_reg, inner_res)
    drop(t3_reg)
    y_out = mux(inner_res, t11_reg)
    drop(inner_res)
    drop(t11_reg)
    drop(m_right)
    drop(m_left)

    outer_res = eval_op(op1_reg, x_out, y_out)
    load(outer_res)
    drop(outer_res)
    last = position(laps.lap - 1, "crazy")
    put("output", last)

    back = move_any(p["P"])
    jump_b = back + 22 + PAIR_GAP + 1 + p["slack"]

    def scratch(s: int) -> int:
        for address in range(33, 127):
            if all(memory.free(address + i) for i in range(4)):
                memory.claim(address, s, "scratch")
                return address
        raise Conflict("no room for a prologue cell")

    code = bootstrap(memory, far=far)
    for address, value in constants:
        code.at(address, "rotate", byte_seed(value)[1])
    s1, c125, c121, temp, zero_p, s26, s80 = (scratch(s) for s in (26, 125, 121, 0, 0, 26, 80))
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
    for _ in range(6):
        code.at(s26, "rotate", 15)
        code.at(c2, "crazy")
    code.at(zero_p, "rotate")
    code.at(m80, "crazy")
    code.at(s80, "rotate", 18)
    code.at(m80, "crazy")

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
    return LispNestedRepl(image, {"K9": k9, "K33": k33, "K36": k36, "K49": k49, "C2": c2, "M80": m80, "halt": halt_at, "landing": landing})

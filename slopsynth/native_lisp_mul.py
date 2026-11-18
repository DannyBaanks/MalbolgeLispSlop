"""H35: Re-executable fixed19 Lisp REPL loop for `(+ a b)`, `(- a b)`, and `(* a b)`.

Evaluates a stream of 7-byte S-expressions (`a, b in '0'..'9'`) in a native
re-executable `fixed19` loop, halting in-image on `0` or EOF, and emitting
2-digit decimal ASCII results (`00..81`):

    (+ 8 7) -> 15
    (- 9 2) -> 07
    (* 9 9) -> 81

Architecture:
1. `(op + 39) mod 81` maps `'*'` (42) -> `0`, `'+'` (43) -> `1`, `'-'` (45) -> `3`,
   yielding orthogonal 6-trit masks `m_plus` (trit 0), `m_minus` (trit 1), and
   `m_mul` (neither).
2. Base-3 shift-and-add multiplication in 6 trits (`rounds=5`, mod `729`)
   computes `a * b = a*b0 + (3*a)*b1 + (9*a)*b2` using `shl` for `x3` and
   in-loop carry addition for `x2` and accumulation.
3. Converts `res in 0..81` to 2 decimal digits via `sub_ge` (`80, 40, 20, 10`).
"""

from __future__ import annotations

from dataclasses import dataclass

from ._native_eval_add import UNARY
from .cycles import PAIR_GAP, jump_cell, padding, pair_cell, pair_residue
from .native_asm import LAP, STEP, Conflict, Laps, Memory, bootstrap, once, seed as byte_seed
from .native_ir_loop import EOF_WORD, TABLE_LAPS

LOWERING = "fixed19-native-lisp-mul-v1"
_PAD = tuple(padding(i) for i in range(94))

PARAMS = {
    "Y": 82, "W": 114, "U": 115, "V": 45, "C2": 125, "M80": 126, "M728": 124,
    "table": 60, "eof": 51, "halt": 59, "slack": 3, "budget": 2600, "P": 68,
    "far": 80 * STEP,
}


def reference(stdin: bytes) -> bytes:
    """Expected stdout of the H35 (+ / - / *) REPL loop on 7-byte frames."""
    out = bytearray()
    idx = 0
    while idx < len(stdin):
        if stdin[idx] == 0:
            break
        if idx + 7 > len(stdin):
            break
        op = stdin[idx + 1]
        a = stdin[idx + 3] - 48
        b = stdin[idx + 5] - 48
        if op == ord("+"):
            val = (a + b) % 729
        elif op == ord("-"):
            val = (a - b) % 729
        else:
            val = (a * b) % 729
        out.extend((48 + (val // 10), 48 + (val % 10)))
        idx += 7
    return bytes(out)


@dataclass(frozen=True, slots=True)
class LispMulRepl:
    image: bytes
    cells: dict[str, int]
    lowering: str = LOWERING


def build_lisp_mul(rounds: int = 5, params: dict[str, int] | None = None) -> LispMulRepl:
    p = PARAMS if params is None else params
    memory = Memory()
    y, w, u, v, c2, m80, m728 = p["Y"], p["W"], p["U"], p["V"], p["C2"], p["M80"], p["M728"]
    for name, s in (("Y", 0), ("W", 0), ("V", 0), ("U", 2), ("C2", 0), ("M80", 0), ("M728", 0)):
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
            if lap > laps.lap + 260:
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
            if rot_lap > laps.lap + 260:
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

    def claim_const(val: int, name: str) -> int:
        for addr in range(46, 124):
            if memory.free(addr) and addr not in (entry - PAIR_GAP, entry, entry + PAIR_GAP):
                memory.claim(addr, val, name)
                return addr
        raise Conflict(f"no room for constant {name}")

    k1 = claim_const(1, "k1")
    k2 = claim_const(2, "k2")
    k4 = claim_const(4, "k4")
    k8 = claim_const(8, "k8")
    k10 = claim_const(10, "k10")
    k20 = claim_const(20, "k20")
    k33 = claim_const(33, "k33")
    k39 = claim_const(39, "k39")
    k40 = claim_const(40, "k40")
    k48 = claim_const(48, "k48")
    k80 = claim_const(80, "k80")

    reg_pool = [r for r in range(128, 150) if memory.free(r)]
    k243 = reg_pool.pop(0)
    tmp_copy = reg_pool.pop(0)
    memory.claim(k243, 27, "k243")
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

    def mask_low6(r: int) -> int:
        zero_and_access(m728)
        access_any(r)
        zero_and_access(m728)
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

    def broadcast_t0_to6(r: int) -> int:
        b0 = keep(r, k1)
        b0_s1 = shl(copy(b0))
        b01 = oradd(b0, b0_s1)
        drop(b0)
        drop(b0_s1)
        b23 = shl(shl(copy(b01)))
        b0123 = oradd(b01, b23)
        drop(b01)
        drop(b23)
        b45 = shl(shl(copy(b0123)))
        out_r = mask_low6(oradd(b0123, b45))
        drop(b0123)
        drop(b45)
        return out_r

    def broadcast_t5(r: int) -> int:
        t5 = unary_ip(keep(r, k243), (0, 1, 1))
        t4 = copy(t5)
        rotate_reg(t4)
        t45 = oradd(t5, t4)
        drop(t5)
        drop(t4)
        t23 = copy(t45)
        rotate_reg(t23)
        rotate_reg(t23)
        t2345 = oradd(t45, t23)
        drop(t45)
        drop(t23)
        t01 = copy(t2345)
        rotate_reg(t01)
        rotate_reg(t01)
        out_r = mask_low6(oradd(t2345, t01))
        drop(t2345)
        drop(t01)
        return out_r

    def sub_ge(x: int, c_const: int) -> tuple[int, int]:
        c_neg = mask_low6(add_in_loop(un(c_const, (2, 1, 0)), k1, rounds))
        d = mask_low6(add_in_loop(x, c_neg, rounds))
        drop(c_neg)
        m_lt = broadcast_t5(d)
        m_ge = mask_low6(un(m_lt, (1, 0, 0)))
        kd = keep(d, m_ge)
        kx = keep(x, m_lt)
        drop(d)
        drop(m_lt)
        x_next = oradd(kd, kx)
        drop(kd)
        drop(kx)
        return x_next, m_ge

    def mul_0_to_9(a_r: int, b_r: int) -> int:
        prod = uniform(0)
        a_scaled = copy(a_r)
        b_cur = copy(b_r)
        for step in range(3):
            t0 = keep(b_cur, k1)
            eq1_b0 = un(t0, (0, 1, 0))
            eq2_b0 = un(t0, (0, 0, 1))
            drop(t0)
            m1 = broadcast_t0_to6(eq1_b0)
            m2 = broadcast_t0_to6(eq2_b0)
            drop(eq1_b0)
            drop(eq2_b0)
            a_x2 = mask_low6(add_in_loop(a_scaled, a_scaled, rounds))
            k_1 = keep(a_scaled, m1)
            k_2 = keep(a_x2, m2)
            drop(m1)
            drop(m2)
            drop(a_x2)
            term = oradd(k_1, k_2)
            drop(k_1)
            drop(k_2)
            new_prod = mask_low6(add_in_loop(prod, term, rounds))
            drop(prod)
            drop(term)
            prod = new_prod
            if step < 2:
                shl(a_scaled)
                rotate_reg(b_cur)
        drop(a_scaled)
        drop(b_cur)
        return prod

    # Read 7-byte frame `(op a b)`:
    op_reg = read_into(skip_before=0)
    a_raw = read_into(skip_before=1)
    b_raw = read_into(skip_before=1)
    last = position(laps.lap - 1, "crazy")
    put("input", last)

    val_a = mask_low4(add_in_loop(a_raw, k33, 3))
    drop(a_raw)
    val_b = mask_low4(add_in_loop(b_raw, k33, 3))
    drop(b_raw)

    # op_rel = (op + 39) mod 81: '*'->0, '+'->1, '-'->3
    op_rel = mask_low4(add_in_loop(op_reg, k39, 3))
    drop(op_reg)
    m_plus = broadcast_t0_to6(op_rel)
    op_r1 = copy(op_rel)
    rotate_reg(op_r1)
    drop(op_rel)
    m_minus = broadcast_t0_to6(op_r1)
    drop(op_r1)
    m_pm = oradd(m_plus, m_minus)
    m_mul = mask_low6(un(m_pm, (1, 0, 0)))
    drop(m_pm)

    res_add = mask_low6(add_in_loop(val_a, val_b, rounds))
    val_b_neg = mask_low6(add_in_loop(un(val_b, (2, 1, 0)), k1, rounds))
    res_sub = mask_low6(add_in_loop(val_a, val_b_neg, rounds))
    drop(val_b_neg)
    res_mul = mul_0_to_9(val_a, val_b)
    drop(val_a)
    drop(val_b)

    ka = keep(res_add, m_plus)
    ks = keep(res_sub, m_minus)
    km = keep(res_mul, m_mul)
    drop(res_add)
    drop(res_sub)
    drop(res_mul)
    drop(m_plus)
    drop(m_minus)
    drop(m_mul)
    kas = oradd(ka, ks)
    drop(ka)
    drop(ks)
    res = oradd(kas, km)
    drop(kas)
    drop(km)

    # Convert res (0..81) to 2 decimal digits (d1, d0):
    rem2, ge80 = sub_ge(res, k80)
    drop(res)
    rem3, ge40 = sub_ge(rem2, k40)
    drop(rem2)
    rem4, ge20 = sub_ge(rem3, k20)
    drop(rem3)
    rem5, ge10 = sub_ge(rem4, k10)
    drop(rem4)

    d1_8 = keep(k8, ge80)
    d1_4 = keep(k4, ge40)
    drop(ge80)
    drop(ge40)
    d1_84 = mask_low4(add_in_loop(d1_8, d1_4, 3))
    drop(d1_8)
    drop(d1_4)

    d1_2 = keep(k2, ge20)
    d1_1 = keep(k1, ge10)
    drop(ge20)
    drop(ge10)
    d1_21 = mask_low4(add_in_loop(d1_2, d1_1, 3))
    drop(d1_2)
    drop(d1_1)

    d1_val = mask_low4(add_in_loop(d1_84, d1_21, 3))
    drop(d1_84)
    drop(d1_21)
    d1_ascii = mask_low4(add_in_loop(d1_val, k48, 3))
    drop(d1_val)
    load(d1_ascii)
    drop(d1_ascii)
    last = position(laps.lap - 1, "crazy")
    put("output", last)

    d0_ascii = mask_low4(add_in_loop(rem5, k48, 3))
    drop(rem5)
    load(d0_ascii)
    drop(d0_ascii)
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
    s1, c125, c121, temp, zero_p, s26, s80, s8 = (
        scratch(s) for s in (26, 125, 121, 0, 0, 26, 80, 8)
    )
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
    code.at(zero_p, "rotate")
    code.at(m728, "crazy")
    code.at(s80, "rotate", 18)
    code.at(m728, "crazy")
    code.at(s8, "rotate", 14)
    code.at(m728, "crazy")
    code.at(k243, "rotate", 16)

    for _ in range(2500):
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
    return LispMulRepl(image, {"K243": k243, "C2": c2, "M80": m80, "M728": m728, "halt": halt_at, "landing": landing})

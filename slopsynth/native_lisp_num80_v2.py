"""H57: Re-executable fixed19 full 2-digit (`00..80`) Mini-Lisp REPL v2 (`+`, `-`, `*`, `=`, `<`, `>`, `?`, `!!`).

Operates on 9-byte frames `(op ab cd)` (halting on `0` or EOF), supporting
full 4-trit (`0..80`) arithmetic, comparisons, conditionals, and `!!` (`ANS`)
chaining with 2-digit decimal output:

    (+ ab cd) -> (ab + cd) % 81  (2 ASCII digits)
    (- ab cd) -> (ab - cd) % 81  (2 ASCII digits)
    (* ab cd) -> (ab * cd) % 81  (2 ASCII digits)
    (= ab cd) -> '01' if ab == cd else '00'
    (< ab cd) -> '01' if ab <  cd else '00'
    (> ab cd) -> '01' if ab >  cd else '00'
    (? ab cd) -> cd if ab != 0 else '00'
    !!        -> previous result ANS (0..80)
"""

from __future__ import annotations

from dataclasses import dataclass

from ._native_eval_add import UNARY
from .cycles import PAIR_GAP, jump_cell, padding, pair_cell, pair_residue
from .native_asm import LAP, STEP, Conflict, Laps, Memory, bootstrap, once, seed as byte_seed
from .native_ir_loop import EOF_WORD, TABLE_LAPS

LOWERING = "fixed19-native-lisp-num80-v2"
_PAD = tuple(padding(i) for i in range(94))

PARAMS = {
    "Y": 82, "W": 114, "U": 115, "V": 45, "C2": 125, "M80": 126,
    "table": 60, "eof": 51, "halt": 59, "slack": 3, "budget": 2800, "P": 68,
    "far": 80 * STEP,
}


def reference(stdin: bytes) -> bytes:
    """Expected stdout of the H57 2-digit (`00..80`) Mini-Lisp REPL v2 on 9-byte frames."""
    ans = 0
    out = bytearray()
    idx = 0
    while idx < len(stdin):
        if stdin[idx] == 0:
            break
        if idx + 9 > len(stdin):
            break
        op = stdin[idx + 1]

        def parse_2(pos: int) -> int:
            if stdin[pos] == ord("!"):
                return ans
            return ((stdin[pos] - 48) * 10 + (stdin[pos + 1] - 48)) % 81

        a = parse_2(idx + 3)
        b = parse_2(idx + 6)
        if op == ord("+"):
            res = (a + b) % 81
        elif op == ord("-"):
            res = (a - b) % 81
        elif op == ord("*"):
            res = (a * b) % 81
        elif op == ord("="):
            res = 1 if a == b else 0
        elif op == ord("<"):
            res = 1 if a < b else 0
        elif op == ord(">"):
            res = 1 if a > b else 0
        elif op == ord("?"):
            res = b if a != 0 else 0
        else:
            res = 0
        ans = res
        out.append(48 + res // 10)
        out.append(48 + res % 10)
        idx += 9
    return bytes(out)


@dataclass(frozen=True, slots=True)
class LispNum80V2Repl:
    image: bytes
    cells: dict[str, int]
    lowering: str = LOWERING


def build_lisp_num80_v2(rounds: int = 3, params: dict[str, int] | None = None) -> LispNum80V2Repl:
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
    pair, move, crazy = laps.pair, laps.move, laps.crazy
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
            if lap > laps.lap + 300:
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
            if rot_lap > laps.lap + 300:
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
    access_any(w)
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
    k5 = claim_const(5, "k5")
    k10 = claim_const(10, "k10")
    k18 = claim_const(18, "k18")  # -63 mod 81 ('?')
    k19 = claim_const(19, "k19")  # -62 mod 81 ('>')
    k20 = claim_const(20, "k20")
    k21 = claim_const(21, "k21")
    k27 = claim_const(27, "k27")
    k31 = claim_const(31, "k31")  # -50 mod 81
    k33 = claim_const(33, "k33")
    k36 = claim_const(36, "k36")
    k38 = claim_const(38, "k38")
    k39 = claim_const(39, "k39")
    k48 = claim_const(48, "k48")
    k61 = claim_const(61, "k61")  # -20 mod 81
    k71 = claim_const(71, "k71")  # -10 mod 81

    reg_pool = [
        r
        for r in (*range(128, 150), *range(116, 124))
        if memory.free(r) and r not in (entry - PAIR_GAP, entry, entry + PAIR_GAP)
    ]
    tmp_copy = reg_pool.pop(0)
    ans_reg = reg_pool.pop(0)
    memory.claim(tmp_copy, 0, "tmp_copy")
    memory.claim(ans_reg, 0, "ans_reg")
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

    def broadcast_t0(r: int) -> int:
        b0 = keep(r, k1)
        b0_s1 = shl(copy(b0))
        b01 = oradd(b0, b0_s1)
        drop(b0)
        drop(b0_s1)
        b23 = shl(shl(copy(b01)))
        out_r = mask_low4(oradd(b01, b23))
        drop(b01)
        drop(b23)
        return out_r

    def broadcast_t3_is2(r: int) -> int:
        t3 = unary_ip(keep(r, k27), (0, 0, 1))
        t2 = copy(t3)
        rotate_reg(t2)
        t23 = oradd(t3, t2)
        drop(t3)
        drop(t2)
        t01 = copy(t23)
        rotate_reg(t01)
        rotate_reg(t01)
        out_r = mask_low4(oradd(t23, t01))
        drop(t23)
        drop(t01)
        return out_r

    def broadcast_t3_is1(r: int) -> int:
        t3 = unary_ip(keep(r, k27), (0, 1, 0))
        t2 = copy(t3)
        rotate_reg(t2)
        t23 = oradd(t3, t2)
        drop(t3)
        drop(t2)
        t01 = copy(t23)
        rotate_reg(t01)
        rotate_reg(t01)
        out_r = mask_low4(oradd(t23, t01))
        drop(t23)
        drop(t01)
        return out_r

    def is_zero4(r: int) -> int:
        nz = mask_low4(un(r, (0, 1, 1)))
        nz_r1 = copy(nz)
        rotate_reg(nz_r1)
        d01 = oradd(nz, nz_r1)
        drop(nz)
        drop(nz_r1)
        d01_r2 = copy(d01)
        rotate_reg(d01_r2)
        rotate_reg(d01_r2)
        any_nz = oradd(d01, d01_r2)
        drop(d01)
        drop(d01_r2)
        nz0 = keep(any_nz, k1)
        drop(any_nz)
        eq0 = unary_ip(nz0, (1, 0, 0))
        out_r = broadcast_t0(eq0)
        drop(eq0)
        return out_r

    def eq_const(r: int, k_neg: int) -> int:
        d = mask_low4(add_in_loop(r, k_neg, rounds))
        m = is_zero4(d)
        drop(d)
        return m

    def mul_0_to_80(a_r: int, b_r: int) -> int:
        prod = uniform(0)
        a_scaled = a_r
        b_cur = b_r
        for step in range(4):
            t0 = keep(b_cur, k1)
            eq1_b0 = un(t0, (0, 1, 0))
            m1 = broadcast_t0(eq1_b0)
            drop(eq1_b0)
            k_1 = keep(a_scaled, m1)
            drop(m1)

            eq2_b0 = un(t0, (0, 0, 1))
            drop(t0)
            m2 = broadcast_t0(eq2_b0)
            drop(eq2_b0)
            a_x2 = mask_low4(add_in_loop(a_scaled, a_scaled, rounds))
            k_2 = keep(a_x2, m2)
            drop(m2)
            drop(a_x2)

            term = oradd(k_1, k_2)
            drop(k_1)
            drop(k_2)
            new_prod = mask_low4(add_in_loop(prod, term, rounds))
            drop(prod)
            drop(term)
            prod = new_prod
            if step < 3:
                shl(a_scaled)
                rotate_reg(b_cur)
        drop(a_scaled)
        drop(b_cur)
        return prod

    def read_2digit(skip_before: int) -> int:
        hi_c = read_into(skip_before=skip_before)
        lo_c = read_into(skip_before=0)
        is_ans = eq_const(hi_c, k48)
        hi = mask_low4(add_in_loop(hi_c, k33, rounds))
        drop(hi_c)
        lo = mask_low4(add_in_loop(lo_c, k33, rounds))
        drop(lo_c)
        hi10 = mul_0_to_80(copy(k10), hi)
        num = mask_low4(add_in_loop(hi10, lo, rounds))
        drop(hi10)
        drop(lo)
        pa = keep(ans_reg, is_ans)
        not_ans = mask_low4(un(is_ans, (1, 0, 0)))
        drop(is_ans)
        pb = keep(num, not_ans)
        drop(not_ans)
        drop(num)
        val = oradd(pa, pb)
        drop(pa)
        drop(pb)
        return val

    # Read 9-byte frame `(op ab cd)`:
    op_reg = read_into(skip_before=0)
    a_val = read_2digit(skip_before=1)
    b_val = read_2digit(skip_before=1)
    last = position(laps.lap - 1, "crazy")
    put("input", last)

    # 1. Multiply *
    res_mul = mul_0_to_80(copy(a_val), copy(b_val))
    m_mul = eq_const(op_reg, k39)
    acc_mul = keep(res_mul, m_mul)
    drop(res_mul)
    drop(m_mul)

    # 2. Add +
    res_add = mask_low4(add_in_loop(a_val, b_val, rounds))
    m_plus = eq_const(op_reg, k38)
    k_plus = keep(res_add, m_plus)
    drop(res_add)
    drop(m_plus)
    acc1 = oradd(acc_mul, k_plus)
    drop(acc_mul)
    drop(k_plus)

    # 2b. Conditional ? (ab != 0 ? cd : 0)
    a_z = is_zero4(a_val)
    a_nz = mask_low4(un(a_z, (1, 0, 0)))
    drop(a_z)
    if_raw = keep(b_val, a_nz)
    drop(a_nz)
    m_if = eq_const(op_reg, k18)
    k_if = keep(if_raw, m_if)
    drop(if_raw)
    drop(m_if)
    acc1b = oradd(acc1, k_if)
    drop(acc1)
    drop(k_if)

    # 3. Subtract - and Comparisons =, <, > (exact on 0..80)
    a_t3 = keep(a_val, k27)
    b_t3 = keep(b_val, k27)
    for _ in range(3):
        rotate_reg(a_t3)
        rotate_reg(b_t3)
    b_t3_neg = mask_low4(add_in_loop(un(b_t3, (2, 1, 0)), k1, rounds))
    drop(b_t3)
    diff_t3 = mask_low4(add_in_loop(a_t3, b_t3_neg, rounds))
    drop(a_t3)
    drop(b_t3_neg)
    hi_eq = is_zero4(diff_t3)
    hi_lt = broadcast_t3_is2(diff_t3)
    drop(diff_t3)

    b_neg = mask_low4(add_in_loop(un(b_val, (2, 1, 0)), k1, rounds))
    drop(b_val)
    diff = mask_low4(add_in_loop(a_val, b_neg, rounds))
    drop(a_val)
    drop(b_neg)

    m_minus = eq_const(op_reg, k36)
    k_minus = keep(diff, m_minus)
    drop(m_minus)
    acc2 = oradd(acc1b, k_minus)
    drop(acc1b)
    drop(k_minus)

    lo_lt = broadcast_t3_is2(diff)
    c_lt_lo = keep(hi_eq, lo_lt)
    drop(hi_eq)
    drop(lo_lt)
    c_lt = oradd(hi_lt, c_lt_lo)
    drop(hi_lt)
    drop(c_lt_lo)
    c_eq = is_zero4(diff)
    drop(diff)

    not_eq = mask_low4(un(c_eq, (1, 0, 0)))
    not_lt = mask_low4(un(c_lt, (1, 0, 0)))
    c_gt = keep(not_eq, not_lt)
    drop(not_eq)
    drop(not_lt)

    m_eq = eq_const(op_reg, k20)
    k_eq_raw = keep(c_eq, m_eq)
    drop(c_eq)
    drop(m_eq)
    k_eq = keep(k_eq_raw, k1)
    drop(k_eq_raw)
    acc3 = oradd(acc2, k_eq)
    drop(acc2)
    drop(k_eq)

    m_lt = eq_const(op_reg, k21)
    k_lt_raw = keep(c_lt, m_lt)
    drop(c_lt)
    drop(m_lt)
    k_lt = keep(k_lt_raw, k1)
    drop(k_lt_raw)
    acc4 = oradd(acc3, k_lt)
    drop(acc3)
    drop(k_lt)

    m_gt = eq_const(op_reg, k19)
    drop(op_reg)
    k_gt_raw = keep(c_gt, m_gt)
    drop(c_gt)
    drop(m_gt)
    k_gt = keep(k_gt_raw, k1)
    drop(k_gt_raw)
    res = oradd(acc4, k_gt)
    drop(acc4)
    drop(k_gt)

    copy(res, ans_reg)

    # Convert `res` (0..80) to 2 decimal digits (tens, ones):
    # Step A: >=54 -> -50 (+5 tens); Step B (x2): >=27 -> -20 (+2 tens); Step C (x2): >=10 -> -10 (+1 ten)
    tens = uniform(0)
    rem = copy(res)
    drop(res)

    def div_step(cond_mask: int, k_sub_neg: int, k_ten_inc: int) -> None:
        nonlocal tens, rem
        t_inc = keep(k_ten_inc, cond_mask)
        new_tens = mask_low4(add_in_loop(tens, t_inc, rounds))
        drop(t_inc)
        drop(tens)
        tens = new_tens

        rem_sub = mask_low4(add_in_loop(rem, k_sub_neg, rounds))
        r_a = keep(rem_sub, cond_mask)
        drop(rem_sub)
        not_c = mask_low4(un(cond_mask, (1, 0, 0)))
        r_b = keep(rem, not_c)
        drop(not_c)
        drop(rem)
        rem = oradd(r_a, r_b)
        drop(r_a)
        drop(r_b)

    c54 = broadcast_t3_is2(rem)
    div_step(c54, k31, k5)
    drop(c54)

    for _ in range(2):
        c27 = broadcast_t3_is1(rem)
        div_step(c27, k61, k2)
        drop(c27)

    for _ in range(2):
        rem_m10 = mask_low4(add_in_loop(rem, k71, rounds))
        lt10 = broadcast_t3_is2(rem_m10)
        drop(rem_m10)
        ge10 = mask_low4(un(lt10, (1, 0, 0)))
        drop(lt10)
        div_step(ge10, k71, k1)
        drop(ge10)

    tens_ch = mask_low4(add_in_loop(tens, k48, rounds))
    drop(tens)
    ones_ch = mask_low4(add_in_loop(rem, k48, rounds))
    drop(rem)

    load(tens_ch)
    drop(tens_ch)
    last = position(laps.lap - 1, "crazy")
    put("output", last)

    load(ones_ch)
    drop(ones_ch)
    last = position(laps.lap - 1, "output")
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
    return LispNum80V2Repl(
        image,
        {"C2": c2, "M80": m80, "ANS": ans_reg, "halt": halt_at, "landing": landing},
    )

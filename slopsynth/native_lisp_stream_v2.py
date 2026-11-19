"""H48: Re-executable fixed19 streaming nested S-expression evaluator v2.

Reads `stdin` byte-by-byte with arbitrary whitespace (` `, `\\n`, `\\t`) and
arbitrary multi-expression streaming, supporting up to depth-3 nested
S-expressions over `+`, `-`, `*`, `=`, `<`:

    (+ (* 2 3) (- 9 (+ 1 2)))  -> '9'
    (= (+ 2 3) 5)(< (* 2 2) 5) -> '11'

Uses the H43 conditional `jump_c` branch so `output` is executed ONLY when a
top-level `)` closes (`sp == 0`), avoiding spurious bytes on non-closing chars.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._native_eval_add import UNARY
from .cycles import PAIR_GAP, jump_cell, padding, pair_cell, pair_residue
from .native_asm import LAP, STEP, Conflict, Laps, Memory, bootstrap, once, seed as byte_seed
from .native_ir_loop import EOF_WORD, TABLE_LAPS

LOWERING = "fixed19-native-lisp-stream-v2"
STACK_DEPTH = 3
_PAD = tuple(padding(i) for i in range(94))

PARAMS = {
    "Y": 82, "W": 114, "U": 115, "V": 45, "C2": 125, "M80": 126,
    "table": 60, "eof": 51, "halt": 59, "slack": 3, "budget": 2800, "P": 68,
    "emit_tgt": 95, "skip_tgt": 102,
    "far": 80 * STEP,
}


def _seed_align(addr: int) -> int:
    k = 4
    while True:
        step = 3**k
        aligned = ((addr + step - 1) // step) * step
        if aligned // step < 128:
            return aligned
        k += 1


def reference(stdin: bytes) -> bytes:
    """Expected stdout of the H48 streaming nested S-expression evaluator."""
    ops: list[int] = []
    v1s: list[int] = []
    v2s: list[int] = []
    acs: list[int] = []
    out = bytearray()
    for ch in stdin:
        if ch == 0:
            break
        if ch == ord("("):
            ops.append(ord("+"))
            v1s.append(ord("0"))
            v2s.append(ord("0"))
            acs.append(0)
        elif ch in (ord("+"), ord("-"), ord("*"), ord("="), ord("<")):
            if ops:
                ops[-1] = ch
        elif ord("0") <= ch <= ord("9"):
            if ops:
                if acs[-1] == 0:
                    v1s[-1] = ch
                    acs[-1] = 1
                else:
                    v2s[-1] = ch
                    acs[-1] = 2
        elif ch == ord(")"):
            if ops:
                op = ops.pop()
                a = v1s.pop()
                b = v2s.pop()
                acs.pop()
                if op == ord("+"):
                    res = (a + (b - 48)) % 81
                elif op == ord("-"):
                    res = (a - (b - 48)) % 81
                elif op == ord("*"):
                    res = (48 + (((a - 48) % 81) * ((b - 48) % 81))) % 81
                elif op == ord("="):
                    res = ord("1") if a == b else ord("0")
                else:
                    res = ord("1") if a < b else ord("0")
                res &= 0xFF
                if not ops:
                    out.append(res)
                else:
                    if acs[-1] == 0:
                        v1s[-1] = res
                        acs[-1] = 1
                    else:
                        v2s[-1] = res
                        acs[-1] = 2
    return bytes(out)


@dataclass(frozen=True, slots=True)
class LispStreamV2Repl:
    image: bytes
    cells: dict[str, int]
    lowering: str = LOWERING


def build_lisp_stream_v2(rounds: int = 3, params: dict[str, int] | None = None) -> LispStreamV2Repl:
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

    halt_at = p["halt"] + 1
    memory.claim(halt_at, once("halt", halt_at), "halt")
    tmp_copy = 149
    ch_reg_slot = 148
    memory.claim(tmp_copy, 0, "tmp_copy")
    memory.claim(ch_reg_slot, 0, "ch_reg")

    access_any(tmp_copy)
    access_any(ch_reg_slot)
    access_any(y)
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
    for address, value in constants:
        memory.claim(address, byte_seed(value)[0], "seed")

    reserved = {
        entry - PAIR_GAP, entry, entry + PAIR_GAP,
        p["emit_tgt"] + 5, p["emit_tgt"] + 5 - PAIR_GAP,
        p["skip_tgt"] + 5, p["skip_tgt"] + 5 - PAIR_GAP,
        *range(p["eof"] + 1, halt_at + 1),
    }

    def claim_const(val: int, name: str) -> int:
        for addr in range(46, 124):
            if memory.free(addr) and addr not in reserved:
                memory.claim(addr, val, name)
                return addr
        raise Conflict(f"no room for constant {name}")

    k1 = claim_const(1, "k1")
    k2 = claim_const(2, "k2")
    k3 = claim_const(3, "k3")
    k20 = claim_const(20, "k20")  # =
    k21 = claim_const(21, "k21")  # <
    k23 = claim_const(23, "k23")  # -58 mod 81 ('9'+1 = 58)
    k27 = claim_const(27, "k27")
    k33 = claim_const(33, "k33")  # -48 mod 81 ('0')
    k36 = claim_const(36, "k36")  # -45 mod 81 ('-')
    k38 = claim_const(38, "k38")  # -43 mod 81 ('+')
    k39 = claim_const(39, "k39")  # -42 mod 81 ('*')
    k40 = claim_const(40, "k40")  # -41 mod 81 (')')
    k41 = claim_const(41, "k41")  # -40 mod 81 ('(')
    k48 = claim_const(48, "k48")
    k49 = claim_const(49, "k49")
    k79 = claim_const(79, "k79")  # -2 mod 81
    k80 = claim_const(80, "k80")  # -1 mod 81
    k_slot_neg = (k80, k79, claim_const(78, "k78"))  # -(1, 2, 3) mod 81

    reg_pool = [
        r
        for r in (*range(128, 150), *range(108, 124))
        if memory.free(r) and r not in reserved
    ]
    sp_reg = reg_pool.pop(0)
    op_regs = [reg_pool.pop(0) for _ in range(STACK_DEPTH)]
    v1_regs = [reg_pool.pop(0) for _ in range(STACK_DEPTH)]
    v2_regs = [reg_pool.pop(0) for _ in range(STACK_DEPTH)]
    ac_regs = [reg_pool.pop(0) for _ in range(STACK_DEPTH)]
    emit_flag_reg = reg_pool.pop(0)
    out_char_reg = reg_pool.pop(0)
    memory.claim(sp_reg, 0, "sp_reg")
    for i in range(STACK_DEPTH):
        memory.claim(op_regs[i], ord("+"), f"op_{i}")
        memory.claim(v1_regs[i], ord("0"), f"v1_{i}")
        memory.claim(v2_regs[i], ord("0"), f"v2_{i}")
        memory.claim(ac_regs[i], 0, f"ac_{i}")
    memory.claim(emit_flag_reg, 0, "emit_flag")
    memory.claim(out_char_reg, 0, "out_char")
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

    def read_into_cur() -> int:
        dst = alloc()
        reset(tmp_copy, 1)
        reset(dst, 1)
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

    def mul_0_to_9(a_r: int, b_r: int) -> int:
        prod = uniform(0)
        a_scaled = a_r
        b_cur = b_r
        for step in range(3):
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
            if step < 2:
                shl(a_scaled)
                rotate_reg(b_cur)
        drop(a_scaled)
        drop(b_cur)
        return prod

    def mux_update(reg: int, new_val: int, wr_mask: int) -> None:
        keep_old = mask_low4(un(wr_mask, (1, 0, 0)))
        new_part = keep(new_val, wr_mask)
        old_part = keep(reg, keep_old)
        drop(keep_old)
        updated = oradd(new_part, old_part)
        drop(new_part)
        drop(old_part)
        copy(updated, reg)
        drop(updated)

    # Byte `ch` was already saved into `ch_reg_slot` at top of loop!
    ch_reg = copy(ch_reg_slot)

    m_open = eq_const(ch_reg, k41)
    m_close = eq_const(ch_reg, k40)

    # Digit '0'..'9': ch >= 48 and ch < 58 (i.e. ch - 48 in 0..9 -> (ch-48) - 10 < 0 and ch - 48 >= 0)
    ch_m48 = mask_low4(add_in_loop(ch_reg, k33, rounds))
    ch_ge48 = mask_low4(un(broadcast_t3_is2(ch_m48), (1, 0, 0)))
    drop(ch_m48)
    ch_m58 = mask_low4(add_in_loop(ch_reg, k23, rounds))
    ch_lt58 = broadcast_t3_is2(ch_m58)
    drop(ch_m58)
    m_digit = keep(ch_ge48, ch_lt58)
    drop(ch_ge48)
    drop(ch_lt58)

    # Operator check: +, -, *, =, <
    m_op_plus = eq_const(ch_reg, k38)
    m_op_minus = eq_const(ch_reg, k36)
    m_op_mul = eq_const(ch_reg, k39)
    m_op_eq = eq_const(ch_reg, k20)
    m_op_lt = eq_const(ch_reg, k21)
    o1 = oradd(m_op_plus, m_op_minus)
    drop(m_op_plus)
    drop(m_op_minus)
    o2 = oradd(m_op_mul, m_op_eq)
    drop(m_op_mul)
    drop(m_op_eq)
    o12 = oradd(o1, o2)
    drop(o1)
    drop(o2)
    m_op = oradd(o12, m_op_lt)
    drop(o12)
    drop(m_op_lt)

    # 1. Handle '(' -> push (sp += 1, init new frame ac=0)
    sp_inc = mask_low4(add_in_loop(sp_reg, k1, rounds))
    mux_update(sp_reg, sp_inc, m_open)
    drop(sp_inc)
    for i, k_neg in enumerate(k_slot_neg):
        m_slot = eq_const(sp_reg, k_neg)
        wr_init = keep(m_open, m_slot)
        drop(m_slot)
        z_reg = uniform(0)
        mux_update(ac_regs[i], z_reg, wr_init)
        drop(z_reg)
        drop(wr_init)
    drop(m_open)

    # 2. Handle operator -> op_regs[sp-1] = ch_reg
    for i, k_neg in enumerate(k_slot_neg):
        m_slot = eq_const(sp_reg, k_neg)
        wr_op = keep(m_op, m_slot)
        drop(m_slot)
        mux_update(op_regs[i], ch_reg, wr_op)
        drop(wr_op)
    drop(m_op)

    # 3. Handle digit -> write to v1_regs[sp-1] if ac==0 else v2_regs[sp-1], ac=1
    for i, k_neg in enumerate(k_slot_neg):
        m_slot = eq_const(sp_reg, k_neg)
        m_d = keep(m_digit, m_slot)
        drop(m_slot)
        ac_z = is_zero4(ac_regs[i])
        wr_v1 = keep(m_d, ac_z)
        not_ac_z = mask_low4(un(ac_z, (1, 0, 0)))
        drop(ac_z)
        wr_v2 = keep(m_d, not_ac_z)
        drop(not_ac_z)
        mux_update(v1_regs[i], ch_reg, wr_v1)
        mux_update(v2_regs[i], ch_reg, wr_v2)
        mux_update(ac_regs[i], k1, m_d)
        drop(wr_v1)
        drop(wr_v2)
        drop(m_d)
    drop(m_digit)
    drop(ch_reg)

    # 4. Handle ')' -> read top frame (op, v1, v2), evaluate, pop (sp -= 1), emit or store in parent!
    cur_op = uniform(0)
    cur_v1 = uniform(0)
    cur_v2 = uniform(0)
    for i, k_neg in enumerate(k_slot_neg):
        m_slot = eq_const(sp_reg, k_neg)
        t_op = keep(op_regs[i], m_slot)
        t_v1 = keep(v1_regs[i], m_slot)
        t_v2 = keep(v2_regs[i], m_slot)
        drop(m_slot)
        new_op = oradd(cur_op, t_op)
        new_v1 = oradd(cur_v1, t_v1)
        new_v2 = oradd(cur_v2, t_v2)
        drop(cur_op)
        drop(cur_v1)
        drop(cur_v2)
        drop(t_op)
        drop(t_v1)
        drop(t_v2)
        cur_op, cur_v1, cur_v2 = new_op, new_v1, new_v2

    # Evaluate (cur_op, cur_v1, cur_v2):
    a_num = mask_low4(add_in_loop(cur_v1, k33, rounds))
    b_num = mask_low4(add_in_loop(cur_v2, k33, rounds))
    prod_num = mul_0_to_9(a_num, b_num)
    res_mul = mask_low4(add_in_loop(prod_num, k48, rounds))
    drop(prod_num)
    m_mul = eq_const(cur_op, k39)
    acc_mul = keep(res_mul, m_mul)
    drop(res_mul)
    drop(m_mul)

    m_plus = eq_const(cur_op, k38)
    y_plus = mask_low4(add_in_loop(cur_v2, k33, rounds))
    res_add = mask_low4(add_in_loop(cur_v1, y_plus, rounds))
    drop(y_plus)
    k_plus = keep(res_add, m_plus)
    drop(res_add)
    drop(m_plus)
    acc1 = oradd(acc_mul, k_plus)
    drop(acc_mul)
    drop(k_plus)

    m_minus = eq_const(cur_op, k36)
    v2_comp = mask_low4(un(cur_v2, (2, 1, 0)))
    y_minus = mask_low4(add_in_loop(v2_comp, k49, rounds))
    drop(v2_comp)
    res_sub = mask_low4(add_in_loop(cur_v1, y_minus, rounds))
    drop(y_minus)
    k_minus = keep(res_sub, m_minus)
    drop(res_sub)
    drop(m_minus)
    acc2 = oradd(acc1, k_minus)
    drop(acc1)
    drop(k_minus)

    v2_neg = mask_low4(add_in_loop(un(cur_v2, (2, 1, 0)), k1, rounds))
    drop(cur_v2)
    diff = mask_low4(add_in_loop(cur_v1, v2_neg, rounds))
    drop(cur_v1)
    drop(v2_neg)
    c_lt = broadcast_t3_is2(diff)
    c_eq = is_zero4(diff)
    drop(diff)

    m_eq = eq_const(cur_op, k20)
    k_eq_raw = keep(c_eq, m_eq)
    drop(c_eq)
    b_eq = keep(k_eq_raw, k1)
    drop(k_eq_raw)
    res_eq = mask_low4(add_in_loop(b_eq, k48, rounds))
    drop(b_eq)
    k_eq = keep(res_eq, m_eq)
    drop(res_eq)
    drop(m_eq)
    acc3 = oradd(acc2, k_eq)
    drop(acc2)
    drop(k_eq)

    m_lt = eq_const(cur_op, k21)
    drop(cur_op)
    k_lt_raw = keep(c_lt, m_lt)
    drop(c_lt)
    b_lt = keep(k_lt_raw, k1)
    drop(k_lt_raw)
    res_lt = mask_low4(add_in_loop(b_lt, k48, rounds))
    drop(b_lt)
    k_lt = keep(res_lt, m_lt)
    drop(res_lt)
    drop(m_lt)
    eval_res = oradd(acc3, k_lt)
    drop(acc3)
    drop(k_lt)

    # Pop sp_reg when m_close:
    sp_dec = mask_low4(add_in_loop(sp_reg, k80, rounds))
    mux_update(sp_reg, sp_dec, m_close)
    drop(sp_dec)

    # If m_close and sp_reg == 0 -> emit! Else store eval_res into parent frame!
    sp_is0 = is_zero4(sp_reg)
    do_emit = keep(m_close, sp_is0)
    not_sp0 = mask_low4(un(sp_is0, (1, 0, 0)))
    drop(sp_is0)
    do_push_parent = keep(m_close, not_sp0)
    drop(not_sp0)
    drop(m_close)

    emit_bit = keep(do_emit, k1)
    drop(do_emit)
    copy(emit_bit, emit_flag_reg)
    drop(emit_bit)
    copy(eval_res, out_char_reg)

    for i, k_neg in enumerate(k_slot_neg):
        m_slot = eq_const(sp_reg, k_neg)
        m_p = keep(do_push_parent, m_slot)
        drop(m_slot)
        ac_z = is_zero4(ac_regs[i])
        wr_v1 = keep(m_p, ac_z)
        not_ac_z = mask_low4(un(ac_z, (1, 0, 0)))
        drop(ac_z)
        wr_v2 = keep(m_p, not_ac_z)
        drop(not_ac_z)
        mux_update(v1_regs[i], eval_res, wr_v1)
        mux_update(v2_regs[i], eval_res, wr_v2)
        mux_update(ac_regs[i], k1, m_p)
        drop(wr_v1)
        drop(wr_v2)
        drop(m_p)
    drop(do_push_parent)
    drop(eval_res)

    # Reset input registers and load `out_char_reg` into A before branching:
    reset(tmp_copy, 1)
    reset(ch_reg_slot, 1)
    load(out_char_reg)

    # Conditional branch on `emit_flag_reg` (0 -> skip_tgt; 1 -> emit_tgt):
    move_any(emit_flag_reg - LAP)
    laps.lap += 1
    dispatch2 = pair("move", laps.lap)
    branch_laps = 7
    while not (memory.free(branch_laps * LAP) and memory.free(branch_laps * LAP + 1)):
        branch_laps += 1
    laps.lap += branch_laps
    table_move2 = pair("move", laps.lap)
    branch_table = table_move2 - dispatch2
    memory.claim(branch_table + 0, p["skip_tgt"], "branch_skip")
    memory.claim(branch_table + 1, p["emit_tgt"], "branch_emit")
    jump_c = table_move2 + PAIR_GAP + 1

    def make_tail(ptr_key: str, prev_end: int, emit_out: bool) -> int:
        b_start = _seed_align(prev_end + 1)
        for lag in (0, PAIR_GAP):
            addr = p[ptr_key] + 5 - lag
            memory.claim(addr, byte_seed(b_start)[0], "seed")
            constants.append((addr, b_start))
        laps.off = p[ptr_key] + 5 - b_start
        laps.lap = (b_start - base) // LAP
        if position(laps.lap, "output") <= b_start:
            laps.lap += 1
        if emit_out:
            last_p = position(laps.lap, "output")
            if last_p <= b_start:
                laps.lap += 1
            put("output", b_start)
            laps.lap += 1
        lap = laps.lap
        while True:
            at = position(lap, "move")
            slot = laps.off + at
            if (
                0 <= slot - PAIR_GAP
                and slot + PAIR_GAP < far
                and memory.fits(slot, p["P"])
                and memory.fits(slot - PAIR_GAP, p["P"])
                and memory.fits(slot + PAIR_GAP, p["P"])
            ):
                break
            lap += 1
            if lap > laps.lap + 1000:
                raise Conflict("no room for parity-invariant tail move")
        memory.claim(slot, p["P"])
        memory.claim(slot - PAIR_GAP, p["P"])
        memory.claim(slot + PAIR_GAP, p["P"])
        pair("move", lap)
        laps.off = p["P"] - at
        laps.lap = lap
        return at + 22 + PAIR_GAP + 1 + p["slack"]

    jump_b_skip = make_tail("skip_tgt", jump_c, emit_out=False)
    jump_b_emit = make_tail("emit_tgt", jump_b_skip, emit_out=True)

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
    code.at(zero_p, "rotate")
    code.at(tmp_copy, "crazy")
    code.at(zero_p, "rotate")
    code.at(ch_reg_slot, "crazy")

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

    end = jump_b_emit
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
    for at in (jump_a, jump_b_emit, jump_b_skip, jump_c):
        if cells[at] is not None:
            raise Conflict("jump overlaps")
        cells[at] = jump_cell(at)
    image = bytes((_PAD[i % 94] if i >= far else 0) if value is None else value for i, value in enumerate(cells))
    return LispStreamV2Repl(
        image,
        {
            "SP": sp_reg,
            "EMIT": emit_flag_reg,
            "OUT": out_char_reg,
            "halt": halt_at,
            "landing": landing,
        },
    )

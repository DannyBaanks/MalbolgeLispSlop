"""H46: Re-executable fixed19 2-arg user-defined functions (`def`/`call`) Mini-Lisp REPL.

Extends H39 (`fn`/`ap`) to 2-argument user-defined functions with local
parameter binding:

    (D op c) -> DEF: define f(p, q) = (op p q) if c == '.' else (op p c)
                     where op in {+, -, *}, emitting c
    (C a b)  -> CALL: evaluate f(a, b) with local p=a, q=b, emitting result
    (s x v)  -> set global x := v, emit v
    (+ a b)  -> add resolved operands
    (- a b)  -> subtract resolved operands
    (* a b)  -> multiply resolved operands (0..9)

Operands resolve `'0'..'9'`, `'x'`, and `'!'` (`ANS`).
"""

from __future__ import annotations

from dataclasses import dataclass

from ._native_eval_add import UNARY
from .cycles import PAIR_GAP, jump_cell, padding, pair_cell, pair_residue
from .native_asm import LAP, STEP, Conflict, Laps, Memory, bootstrap, once, seed as byte_seed
from .native_ir_loop import EOF_WORD, TABLE_LAPS

LOWERING = "fixed19-native-lisp-fn2-v1"
INIT_CHAR = ord("0")
_PAD = tuple(padding(i) for i in range(94))

PARAMS = {
    "Y": 82, "W": 114, "U": 115, "V": 45, "C2": 125, "M80": 126,
    "table": 60, "eof": 51, "halt": 59, "slack": 3, "budget": 2800, "P": 68,
    "far": 80 * STEP,
}


def reference(stdin: bytes, initial: int = INIT_CHAR) -> bytes:
    """Expected stdout of the H46 2-arg def/call Mini-Lisp REPL on 7-byte frames."""
    var_x = initial
    fn_op = ord("+")
    fn_k = ord(".")
    ans = initial
    out = bytearray()
    idx = 0
    while idx < len(stdin):
        if stdin[idx] == 0:
            break
        if idx + 7 > len(stdin):
            break
        op = stdin[idx + 1]
        r1 = stdin[idx + 3]
        r2 = stdin[idx + 5]

        def res_tok(tok: int) -> int:
            if tok == ord("!"):
                return ans
            if tok == ord("x"):
                return var_x
            return tok

        v1 = res_tok(r1)
        v2 = res_tok(r2)

        def eval_arith(aop: int, a: int, b: int) -> int:
            if aop == ord("+"):
                return (a + (b - 48)) % 81
            if aop == ord("-"):
                return (a - (b - 48)) % 81
            return (48 + (((a - 48) % 81) * ((b - 48) % 81))) % 81

        if op in (ord("+"), ord("-"), ord("*")):
            res = eval_arith(op, v1, v2)
        elif op == ord("s"):
            res = v2
            if r1 == ord("x"):
                var_x = res & 0xFF
        elif op == ord("D"):
            fn_op = r1
            fn_k = r2 if r2 == ord(".") else v2
            res = fn_k
        elif op == ord("C"):
            rhs = v2 if fn_k == ord(".") else fn_k
            res = eval_arith(fn_op, v1, rhs)
        else:
            res = 0
        ans = res & 0xFF
        out.append(ans)
        idx += 7
    return bytes(out)


@dataclass(frozen=True, slots=True)
class LispFn2Repl:
    image: bytes
    cells: dict[str, int]
    lowering: str = LOWERING


def build_lisp_fn2(rounds: int = 3, params: dict[str, int] | None = None) -> LispFn2Repl:
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
    k13 = claim_const(13, "k13")  # D: 81 - 68 = 13
    k14 = claim_const(14, "k14")  # C: 81 - 67 = 14
    k33 = claim_const(33, "k33")
    k36 = claim_const(36, "k36")
    k38 = claim_const(38, "k38")
    k39 = claim_const(39, "k39")
    k42 = claim_const(42, "k42")  # x: 120 % 81 = 39 -> 81 - 39 = 42
    k47 = claim_const(47, "k47")  # s: 115 % 81 = 34 -> 81 - 34 = 47
    k48 = claim_const(48, "k48")  # !: 81 - 33 = 48
    k49 = claim_const(49, "k49")
    k35 = claim_const(35, "k35")  # .: 81 - 46 = 35

    reg_pool = [
        r
        for r in (*range(128, 150), *range(116, 124))
        if memory.free(r) and r not in (entry - PAIR_GAP, entry, entry + PAIR_GAP)
    ]
    var_x = reg_pool.pop(0)
    fn_op_reg = reg_pool.pop(0)
    fn_k_reg = reg_pool.pop(0)
    ans_reg = reg_pool.pop(0)
    tmp_copy = reg_pool.pop(0)
    memory.claim(var_x, INIT_CHAR, "var_x")
    memory.claim(fn_op_reg, ord("+"), "fn_op_reg")
    memory.claim(fn_k_reg, ord("."), "fn_k_reg")
    memory.claim(ans_reg, INIT_CHAR, "ans_reg")
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

    def resolve_tok(tok: int) -> int:
        m_bang = eq_const(tok, k48)
        m_x = eq_const(tok, k42)
        bx = oradd(m_bang, m_x)
        m_lit = mask_low4(un(bx, (1, 0, 0)))
        drop(bx)
        kb = keep(ans_reg, m_bang)
        drop(m_bang)
        kx = keep(var_x, m_x)
        drop(m_x)
        kl = keep(tok, m_lit)
        drop(m_lit)
        k12 = oradd(kb, kx)
        drop(kb)
        drop(kx)
        val = oradd(k12, kl)
        drop(k12)
        drop(kl)
        return val

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

    op_reg = read_into(skip_before=0)
    r1_reg = read_into(skip_before=1)
    r2_reg = read_into(skip_before=1)
    last = position(laps.lap - 1, "crazy")
    put("input", last)

    v1 = resolve_tok(r1_reg)
    v2 = resolve_tok(r2_reg)

    m_def = eq_const(op_reg, k13)
    m_call = eq_const(op_reg, k14)
    m_set = eq_const(op_reg, k47)

    # Update fn_op_reg and fn_k_reg when m_def (r2=='_' -> v2==95 already)
    mux_update(fn_op_reg, r1_reg, m_def)
    drop(r2_reg)
    mux_update(fn_k_reg, v2, m_def)

    # Update var_x when m_set and r1 == 'x'
    m_r1_x = eq_const(r1_reg, k42)
    drop(r1_reg)
    wr_x = keep(m_set, m_r1_x)
    drop(m_r1_x)
    mux_update(var_x, v2, wr_x)
    drop(wr_x)

    # Effective arithmetic op: fn_op_reg if m_call else op_reg
    m_not_call = mask_low4(un(m_call, (1, 0, 0)))
    eff_op_a = keep(fn_op_reg, m_call)
    eff_op_b = keep(op_reg, m_not_call)
    drop(op_reg)
    drop(m_not_call)
    eff_op = oradd(eff_op_a, eff_op_b)
    drop(eff_op_a)
    drop(eff_op_b)

    # Effective rhs: (v2 if fn_k == '.' else fn_k) if m_call else v2
    m_fk_us = eq_const(fn_k_reg, k35)
    m_fk_not_us = mask_low4(un(m_fk_us, (1, 0, 0)))
    call_rhs_a = keep(v2, m_fk_us)
    call_rhs_b = keep(fn_k_reg, m_fk_not_us)
    drop(m_fk_us)
    drop(m_fk_not_us)
    call_rhs = oradd(call_rhs_a, call_rhs_b)
    drop(call_rhs_a)
    drop(call_rhs_b)

    m_not_call2 = mask_low4(un(m_call, (1, 0, 0)))
    eff_b_a = keep(call_rhs, m_call)
    drop(call_rhs)
    eff_b_b = keep(v2, m_not_call2)
    drop(m_not_call2)
    eff_b = oradd(eff_b_a, eff_b_b)
    drop(eff_b_a)
    drop(eff_b_b)

    # Arithmetic +, -, * on (v1, eff_b)
    a_num = mask_low4(add_in_loop(v1, k33, rounds))
    b_num = mask_low4(add_in_loop(eff_b, k33, rounds))
    prod_num = mul_0_to_9(a_num, b_num)
    res_mul = mask_low4(add_in_loop(prod_num, k48, rounds))
    drop(prod_num)

    m_mul = eq_const(eff_op, k39)
    acc_mul = keep(res_mul, m_mul)
    drop(res_mul)
    drop(m_mul)

    m_plus = eq_const(eff_op, k38)
    y_plus = mask_low4(add_in_loop(eff_b, k33, rounds))
    res_add = mask_low4(add_in_loop(v1, y_plus, rounds))
    drop(y_plus)
    k_plus = keep(res_add, m_plus)
    drop(res_add)
    drop(m_plus)
    acc1 = oradd(acc_mul, k_plus)
    drop(acc_mul)
    drop(k_plus)

    m_minus = eq_const(eff_op, k36)
    drop(eff_op)
    b_comp = mask_low4(un(eff_b, (2, 1, 0)))
    drop(eff_b)
    y_minus = mask_low4(add_in_loop(b_comp, k49, rounds))
    drop(b_comp)
    res_sub = mask_low4(add_in_loop(v1, y_minus, rounds))
    drop(y_minus)
    drop(v1)
    k_minus = keep(res_sub, m_minus)
    drop(res_sub)
    drop(m_minus)
    acc2 = oradd(acc1, k_minus)
    drop(acc1)
    drop(k_minus)

    # Select final result: fn_k_reg on m_def, v2 on m_set, else acc2
    m_ds = oradd(m_def, m_set)
    m_arith = mask_low4(un(m_ds, (1, 0, 0)))
    drop(m_ds)
    k_arith = keep(acc2, m_arith)
    drop(acc2)
    drop(m_arith)
    k_def = keep(fn_k_reg, m_def)
    drop(m_def)
    k_set = keep(v2, m_set)
    drop(v2)
    drop(m_set)

    acc3 = oradd(k_arith, k_def)
    drop(k_arith)
    drop(k_def)
    res = oradd(acc3, k_set)
    drop(acc3)
    drop(k_set)

    copy(res, ans_reg)
    load(res)
    drop(res)
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
    return LispFn2Repl(
        image,
        {
            "X": var_x,
            "FN_OP": fn_op_reg,
            "FN_K": fn_k_reg,
            "ANS": ans_reg,
            "C2": c2,
            "M80": m80,
            "halt": halt_at,
            "landing": landing,
        },
    )

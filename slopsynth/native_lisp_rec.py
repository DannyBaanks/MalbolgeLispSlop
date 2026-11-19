"""H44: Re-executable fixed19 internal-loop `fact(n)`, `fib(n)`, and `sum(n)` Mini-Lisp REPL.

Uses the H43 runtime conditional jump (`branch_table` + `jump_c`) to execute
multi-step iterative/recursive algorithms inside a single Lisp call:

    (F n _) -> factorial(n) mod 81, emits chr(48 + fact(n) % 81)
    (B n _) -> fibonacci(n) mod 81, emits chr(48 + fib(n) % 81)
    (S n _) -> sum(1..n) mod 81, emits chr(48 + sum(n) % 81)
    (+ a b) -> add resolved operands
    (- a b) -> subtract resolved operands
"""

from __future__ import annotations

from dataclasses import dataclass

from ._native_eval_add import UNARY
from .cycles import PAIR_GAP, jump_cell, padding, pair_cell, pair_residue
from .native_asm import LAP, STEP, Conflict, Laps, Memory, bootstrap, once, seed as byte_seed
from .native_ir_loop import EOF_WORD, TABLE_LAPS

LOWERING = "fixed19-native-lisp-rec-v1"
INIT_CHAR = ord("0")
_PAD = tuple(padding(i) for i in range(94))

PARAMS = {
    "Y": 82, "W": 114, "U": 115, "V": 45, "C2": 125, "M80": 126,
    "table": 60, "eof": 51, "halt": 59, "slack": 3, "budget": 2800, "P": 68,
    "loop_tgt": 95, "exit_tgt": 102,
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


def reference(stdin: bytes, initial: int = INIT_CHAR) -> bytes:
    """Expected stdout of the H44 fact/fib/sum Mini-Lisp REPL on 7-byte frames."""
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

        v1 = ans if r1 == ord("!") else r1
        v2 = ans if r2 == ord("!") else r2

        if op == ord("+"):
            res = (v1 + (v2 - 48)) % 81
        elif op == ord("-"):
            res = (v1 - (v2 - 48)) % 81
        elif op == ord("S"):
            n = (v1 - 48) % 81
            acc = 0
            while n > 0:
                acc = (acc + n) % 81
                n -= 1
            res = (48 + acc) % 81
        elif op == ord("F"):
            n = (v1 - 48) % 81
            acc = 1
            while n > 0:
                acc = (acc * n) % 81
                n -= 1
            res = (48 + acc) % 81
        elif op == ord("B"):
            n = (v1 - 48) % 81
            a, b = 0, 1
            while n > 0:
                a, b = b, (a + b) % 81
                n -= 1
            res = (48 + a) % 81
        else:
            res = 0
        ans = res & 0xFF
        out.append(ans)
        idx += 7
    return bytes(out)


@dataclass(frozen=True, slots=True)
class LispRecRepl:
    image: bytes
    cells: dict[str, int]
    lowering: str = LOWERING


def build_lisp_rec(rounds: int = 3, params: dict[str, int] | None = None) -> LispRecRepl:
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

    reserved = {
        entry - PAIR_GAP, entry, entry + PAIR_GAP,
        p["loop_tgt"] + 5, p["loop_tgt"] + 5 - PAIR_GAP,
        p["exit_tgt"] + 5, p["exit_tgt"] + 5 - PAIR_GAP,
    }

    def claim_const(val: int, name: str) -> int:
        for addr in range(46, 124):
            if memory.free(addr) and addr not in reserved:
                memory.claim(addr, val, name)
                return addr
        raise Conflict(f"no room for constant {name}")

    k1 = claim_const(1, "k1")
    k11 = claim_const(11, "k11")  # F: 81 - 70 = 11
    k15 = claim_const(15, "k15")  # B: 81 - 66 = 15
    k33 = claim_const(33, "k33")
    k36 = claim_const(36, "k36")
    k38 = claim_const(38, "k38")
    k48 = claim_const(48, "k48")
    k49 = claim_const(49, "k49")
    k79 = claim_const(79, "k79")  # S: 81 - 2 = 79
    k80 = claim_const(80, "k80")

    reg_pool = [
        r
        for r in (*range(128, 150), *range(116, 124))
        if memory.free(r) and r not in reserved
    ]
    ans_reg = reg_pool.pop(0)
    cnt_reg = reg_pool.pop(0)
    acc_reg = reg_pool.pop(0)
    fib_b_reg = reg_pool.pop(0)
    mode_fact = reg_pool.pop(0)
    mode_fib = reg_pool.pop(0)
    mode_sum = reg_pool.pop(0)
    is_loop_reg = reg_pool.pop(0)
    done_reg = reg_pool.pop(0)
    tmp_copy = reg_pool.pop(0)
    for r, val, name in (
        (ans_reg, INIT_CHAR, "ans_reg"),
        (cnt_reg, 0, "cnt_reg"),
        (acc_reg, 0, "acc_reg"),
        (fib_b_reg, 0, "fib_b_reg"),
        (mode_fact, 0, "mode_fact"),
        (mode_fib, 0, "mode_fib"),
        (mode_sum, 0, "mode_sum"),
        (is_loop_reg, 0, "is_loop_reg"),
        (done_reg, 0, "done_reg"),
        (tmp_copy, 0, "tmp_copy"),
    ):
        memory.claim(r, val, name)
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
        m_not_bang = mask_low4(un(m_bang, (1, 0, 0)))
        kb = keep(ans_reg, m_bang)
        kd = keep(tok, m_not_bang)
        drop(m_bang)
        drop(m_not_bang)
        val = oradd(kb, kd)
        drop(kb)
        drop(kd)
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

    def mux_select(reg: int, new_val: int, active_mask: int) -> None:
        not_active = mask_low4(un(active_mask, (1, 0, 0)))
        part_a = keep(new_val, active_mask)
        part_b = keep(reg, not_active)
        drop(not_active)
        merged = oradd(part_a, part_b)
        drop(part_a)
        drop(part_b)
        copy(merged, reg)
        drop(merged)

    # 1. Read 7-byte frame `(op r1 r2)`:
    op_reg = read_into(skip_before=0)
    r1_reg = read_into(skip_before=1)
    r2_reg = read_into(skip_before=1)
    last = position(laps.lap - 1, "crazy")
    put("input", last)

    v1 = resolve_tok(r1_reg)
    drop(r1_reg)
    v2 = resolve_tok(r2_reg)
    drop(r2_reg)

    m_plus = eq_const(op_reg, k38)
    y_plus = mask_low4(add_in_loop(v2, k33, rounds))
    res_add = mask_low4(add_in_loop(v1, y_plus, rounds))
    drop(y_plus)
    k_plus = keep(res_add, m_plus)
    drop(res_add)
    drop(m_plus)

    m_minus = eq_const(op_reg, k36)
    v2_comp = mask_low4(un(v2, (2, 1, 0)))
    y_minus = mask_low4(add_in_loop(v2_comp, k49, rounds))
    drop(v2_comp)
    res_sub = mask_low4(add_in_loop(v1, y_minus, rounds))
    drop(y_minus)
    drop(v2)
    k_minus = keep(res_sub, m_minus)
    drop(res_sub)
    drop(m_minus)

    arith_acc = oradd(k_plus, k_minus)
    drop(k_plus)
    drop(k_minus)

    m_sum = eq_const(op_reg, k79)
    m_fact = eq_const(op_reg, k11)
    m_fib = eq_const(op_reg, k15)
    drop(op_reg)
    copy(m_sum, mode_sum)
    copy(m_fact, mode_fact)
    copy(m_fib, mode_fib)

    sf = oradd(m_sum, m_fact)
    drop(m_sum)
    m_loop = oradd(sf, m_fib)
    drop(sf)
    drop(m_fib)
    copy(m_loop, is_loop_reg)

    n_val = mask_low4(add_in_loop(v1, k33, rounds))
    drop(v1)
    init_cnt = keep(n_val, m_loop)
    drop(n_val)
    copy(init_cnt, cnt_reg)
    drop(init_cnt)

    # Initial acc_reg: arith_acc if not m_loop; 1 if m_fact; 0 if m_sum or m_fib
    m_not_loop = mask_low4(un(m_loop, (1, 0, 0)))
    drop(m_loop)
    init_a = keep(arith_acc, m_not_loop)
    drop(arith_acc)
    drop(m_not_loop)
    init_f = keep(k1, m_fact)
    drop(m_fact)
    init_acc = oradd(init_a, init_f)
    drop(init_a)
    drop(init_f)
    copy(init_acc, acc_reg)
    drop(init_acc)

    copy(k1, fib_b_reg)

    # 2. Jump to `body_start` with D = loop_tgt + 5:
    pre_move = move_any(p["loop_tgt"])
    jump_pre = pre_move + PAIR_GAP + 1
    body_start = _seed_align(jump_pre + 1)
    laps.lap = (body_start - base) // LAP
    while position(laps.lap, "move") <= body_start or not all(
        memory.free(p["loop_tgt"] + 5 + (position(laps.lap, "move") - body_start) + lag)
        for lag in (-PAIR_GAP, 0, PAIR_GAP)
    ):
        laps.lap += 1
    first_body_move = pair("move", laps.lap)
    body_delta = first_body_move - body_start
    for lag in (-PAIR_GAP, 0, PAIR_GAP):
        memory.claim(p["loop_tgt"] + 5 + body_delta + lag, y - 22, "body_entry")
    laps.off = (y - 22) - first_body_move

    # 3. Internal loop body (`body_start`):
    done_now = is_zero4(cnt_reg)
    active = mask_low4(un(done_now, (1, 0, 0)))
    drop(done_now)

    step_sum = mask_low4(add_in_loop(acc_reg, cnt_reg, rounds))
    step_fact = mul_0_to_9(copy(acc_reg), copy(cnt_reg))
    step_fib_a = copy(fib_b_reg)
    step_fib_b = mask_low4(add_in_loop(acc_reg, fib_b_reg, rounds))

    ks = keep(step_sum, mode_sum)
    drop(step_sum)
    kf = keep(step_fact, mode_fact)
    drop(step_fact)
    kb = keep(step_fib_a, mode_fib)
    drop(step_fib_a)
    ksf = oradd(ks, kf)
    drop(ks)
    drop(kf)
    next_acc = oradd(ksf, kb)
    drop(ksf)
    drop(kb)

    mux_select(acc_reg, next_acc, active)
    drop(next_acc)
    mux_select(fib_b_reg, step_fib_b, active)
    drop(step_fib_b)

    next_cnt_dec = mask_low4(add_in_loop(cnt_reg, k80, rounds))
    mux_select(cnt_reg, next_cnt_dec, active)
    drop(next_cnt_dec)
    drop(active)

    done_mask = is_zero4(cnt_reg)
    done_bit = keep(done_mask, k1)
    drop(done_mask)
    copy(done_bit, done_reg)
    drop(done_bit)

    # 4. Conditional branch on `done_reg`:
    move_any(done_reg - LAP)
    laps.lap += 1
    dispatch2 = pair("move", laps.lap)
    branch_laps = 7
    while not (memory.free(branch_laps * LAP) and memory.free(branch_laps * LAP + 1)):
        branch_laps += 1
    laps.lap += branch_laps
    table_move2 = pair("move", laps.lap)
    branch_table = table_move2 - dispatch2
    memory.claim(branch_table + 0, p["loop_tgt"], "branch_loop")
    memory.claim(branch_table + 1, p["exit_tgt"], "branch_exit")
    jump_c = table_move2 + PAIR_GAP + 1
    exit_resume = _seed_align(jump_c + 1)

    for lag in (0, PAIR_GAP):
        for addr, val in ((p["loop_tgt"] + 5 - lag, body_start), (p["exit_tgt"] + 5 - lag, exit_resume)):
            memory.claim(addr, byte_seed(val)[0], "seed")
            constants.append((addr, val))

    # 5. Exit path (`exit_resume`):
    laps.lap = (exit_resume - base) // LAP
    while position(laps.lap, "move") <= exit_resume or not all(
        memory.free(p["exit_tgt"] + 5 + (position(laps.lap, "move") - exit_resume) + lag)
        for lag in (-PAIR_GAP, 0, PAIR_GAP)
    ):
        laps.lap += 1
    first_exit_move = pair("move", laps.lap)
    exit_delta = first_exit_move - exit_resume
    for lag in (-PAIR_GAP, 0, PAIR_GAP):
        memory.claim(p["exit_tgt"] + 5 + exit_delta + lag, y - 22, "exit_entry")
    laps.off = (y - 22) - first_exit_move

    loop_char = mask_low4(add_in_loop(acc_reg, k48, rounds))
    not_loop = mask_low4(un(is_loop_reg, (1, 0, 0)))
    k_l = keep(loop_char, is_loop_reg)
    drop(loop_char)
    k_a = keep(acc_reg, not_loop)
    drop(not_loop)
    res = oradd(k_l, k_a)
    drop(k_l)
    drop(k_a)

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
    for at in (jump_a, jump_b, jump_c, jump_pre):
        if cells[at] is not None:
            raise Conflict("jump overlaps")
        cells[at] = jump_cell(at)
    image = bytes((_PAD[i % 94] if i >= far else 0) if value is None else value for i, value in enumerate(cells))
    return LispRecRepl(
        image,
        {
            "ANS": ans_reg,
            "CNT": cnt_reg,
            "ACC": acc_reg,
            "FIB_B": fib_b_reg,
            "body_start": body_start,
            "exit_resume": exit_resume,
            "halt": halt_at,
            "landing": landing,
        },
    )

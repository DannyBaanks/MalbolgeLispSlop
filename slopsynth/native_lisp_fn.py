"""H39: Re-executable fixed19 Lisp REPL with user-defined 1-arg functions (`fn` / `ap`).

Evaluates a stream of 10-byte function definitions and applications in a native
re-executable `fixed19` loop, halting in-image on `0` or EOF:

    (fn + x 2)   -> defines f(x) = (+ x 2), emits '2'
    (fn - x 1)   -> defines f(x) = (- x 1), emits '1'
    (fn * x 2)   -> defines f(x) = (* x 2), emits '2'
    (ap f 3 0)   -> applies f(3), updates ANS, emits result
    (ap f ! 0)   -> applies f(ANS), enabling chained function composition

Architecture:
1. Byte 1 (`'f'` = 102, trit 0 = 0 vs `'a'` = 97, trit 0 = 1) yields
   orthogonal 4-trit masks `m_fn` and `m_ap` via `keep(t1, k1)`.
2. Persistent closure registers `fn_op` (initialized `'+'`) and `fn_k`
   (initialized `'0'`) store the function body across passes; `ans_reg`
   (initialized `'0'`) stores the last application result for `'!'`.
3. `ap` resolves `arg` (`'0'..'9'` or `'!'`), evaluates `(fn_op arg fn_k)`
   across `+`, `-`, and `*` (base-3 shift-and-add on `0..9`), and updates
   `ans_reg`.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._native_eval_add import UNARY
from .cycles import PAIR_GAP, jump_cell, padding, pair_cell, pair_residue
from .native_asm import LAP, STEP, Conflict, Laps, Memory, bootstrap, once, seed as byte_seed
from .native_ir_loop import EOF_WORD, TABLE_LAPS

LOWERING = "fixed19-native-lisp-fn-v1"
_PAD = tuple(padding(i) for i in range(94))

PARAMS = {
    "Y": 82, "W": 114, "U": 115, "V": 45, "C2": 125, "M80": 126,
    "table": 60, "eof": 51, "halt": 59, "slack": 3, "budget": 2400, "P": 68,
    "far": 80 * STEP,
}


def reference(stdin: bytes) -> bytes:
    """Expected stdout of the H39 fn/ap REPL loop on 10-byte frames."""
    out = bytearray()
    fn_op = ord("+")
    fn_k = ord("0")
    ans = ord("0")
    idx = 0
    while idx < len(stdin):
        if stdin[idx] == 0:
            break
        if idx + 10 > len(stdin):
            break
        frame = stdin[idx : idx + 10]
        if frame[1] == ord("f"):
            fn_op = frame[4]
            fn_k = frame[8]
            out.append(fn_k & 0xFF)
        else:
            arg = ans if frame[6] == ord("!") else frame[6]
            a_num = (arg - 48) % 81
            k_num = (fn_k - 48) % 81
            if fn_op == ord("+"):
                res = (48 + ((a_num + k_num) % 81)) % 81
            elif fn_op == ord("-"):
                res = (arg - k_num) % 81
            else:
                res = (48 + ((a_num * k_num) % 81)) % 81
            ans = res & 0xFF
            out.append(ans)
        idx += 10
    return bytes(out)


@dataclass(frozen=True, slots=True)
class LispFnRepl:
    image: bytes
    cells: dict[str, int]
    lowering: str = LOWERING


def build_lisp_fn(rounds: int = 3, params: dict[str, int] | None = None) -> LispFnRepl:
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
    k9 = claim_const(9, "k9")
    k33 = claim_const(33, "k33")
    k39 = claim_const(39, "k39")
    k48 = claim_const(48, "k48")
    k49 = claim_const(49, "k49")

    reg_pool = [r for r in range(128, 150) if memory.free(r)]
    fn_op = reg_pool.pop(0)
    fn_k = reg_pool.pop(0)
    ans_reg = reg_pool.pop(0)
    tmp_copy = reg_pool.pop(0)
    memory.claim(fn_op, ord("+"), "fn_op")
    memory.claim(fn_k, ord("0"), "fn_k")
    memory.claim(ans_reg, ord("0"), "ans_reg")
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

    def resolve_bang(tok: int) -> int:
        is_two = un(tok, (0, 0, 1))
        r_rot = copy(is_two)
        rotate_reg(r_rot)
        w_or = oradd(is_two, r_rot)
        drop(is_two)
        drop(r_rot)
        b2 = keep(w_or, k9)
        drop(w_or)
        b1 = copy(b2)
        rotate_reg(b1)
        b21 = oradd(b2, b1)
        drop(b2)
        drop(b1)
        b32 = shl(copy(b21))
        b10 = copy(b21)
        rotate_reg(b10)
        drop(b21)
        m_dig = mask_low4(oradd(b32, b10))
        drop(b32)
        drop(b10)
        m_bang = mask_low4(un(m_dig, (1, 0, 0)))
        kd = keep(tok, m_dig)
        kb = keep(ans_reg, m_bang)
        drop(m_dig)
        drop(m_bang)
        out_r = oradd(kd, kb)
        drop(kd)
        drop(kb)
        return out_r

    def mul_0_to_9(a_r: int, b_r: int) -> int:
        prod = uniform(0)
        a_scaled = copy(a_r)
        b_cur = copy(b_r)
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

    def mux_update(reg: int, new_val: int, m_write: int) -> None:
        m_keep = mask_low4(un(m_write, (1, 0, 0)))
        kw = keep(new_val, m_write)
        ko = keep(reg, m_keep)
        drop(m_keep)
        merged = oradd(kw, ko)
        drop(kw)
        drop(ko)
        copy(merged, reg)
        drop(merged)

    # Read 10-byte frame:
    # 0:'(', 1:t1('f'/'a'), 2:'n'/'p', 3:' ', 4:t4, 5:' ', 6:t6, 7:' ', 8:t8, 9:')'
    t1_reg = read_into(skip_before=0)
    t4_reg = read_into(skip_before=2)
    t6_reg = read_into(skip_before=1)
    t8_reg = read_into(skip_before=1)
    last = position(laps.lap - 1, "crazy")
    put("input", last)

    m_ap = broadcast_t0(t1_reg)
    drop(t1_reg)
    m_fn = mask_low4(un(m_ap, (1, 0, 0)))

    # Update closure (fn_op, fn_k) when m_fn == 1:
    mux_update(fn_op, t4_reg, m_fn)
    drop(t4_reg)
    mux_update(fn_k, t8_reg, m_fn)
    drop(t8_reg)

    # Resolve arg (t6_reg or ans_reg on '!') and compute f(arg):
    arg_ascii = resolve_bang(t6_reg)
    drop(t6_reg)

    op_rel = mask_low4(add_in_loop(fn_op, k39, rounds))
    m_plus = broadcast_t0(op_rel)
    op_r1 = copy(op_rel)
    rotate_reg(op_r1)
    drop(op_rel)
    m_minus = broadcast_t0(op_r1)
    drop(op_r1)
    m_pm = oradd(m_plus, m_minus)
    m_mul = mask_low4(un(m_pm, (1, 0, 0)))
    drop(m_pm)

    y_plus = mask_low4(add_in_loop(fn_k, k33, rounds))
    k_comp = mask_low4(un(fn_k, (2, 1, 0)))
    y_minus = mask_low4(add_in_loop(k_comp, k49, rounds))
    drop(k_comp)
    kp = keep(y_plus, m_plus)
    km_y = keep(y_minus, m_minus)
    drop(y_plus)
    drop(y_minus)
    y_pm = oradd(kp, km_y)
    drop(kp)
    drop(km_y)
    res_pm = mask_low4(add_in_loop(arg_ascii, y_pm, rounds))
    drop(y_pm)
    m_pm2 = oradd(m_plus, m_minus)
    drop(m_plus)
    drop(m_minus)

    a_num = mask_low4(add_in_loop(arg_ascii, k33, rounds))
    drop(arg_ascii)
    k_num = mask_low4(add_in_loop(fn_k, k33, rounds))
    prod_num = mul_0_to_9(a_num, k_num)
    drop(a_num)
    drop(k_num)
    res_mul = mask_low4(add_in_loop(prod_num, k48, rounds))
    drop(prod_num)

    k_pm_res = keep(res_pm, m_pm2)
    k_mul_res = keep(res_mul, m_mul)
    drop(res_pm)
    drop(res_mul)
    drop(m_pm2)
    drop(m_mul)
    ap_res = oradd(k_pm_res, k_mul_res)
    drop(k_pm_res)
    drop(k_mul_res)

    mux_update(ans_reg, ap_res, m_ap)

    out_val = oradd(keep(ap_res, m_ap), keep(fn_k, m_fn))
    drop(ap_res)
    drop(m_ap)
    drop(m_fn)
    load(out_val)
    drop(out_val)
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
    return LispFnRepl(image, {"FN_OP": fn_op, "FN_K": fn_k, "ANS": ans_reg, "C2": c2, "M80": m80, "halt": halt_at, "landing": landing})

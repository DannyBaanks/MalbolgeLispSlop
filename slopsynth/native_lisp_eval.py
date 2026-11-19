"""H49: Re-executable fixed19 code-as-data AST-heap `eval` Mini-Lisp REPL.

Stores Lisp AST nodes `(op, lhs, rhs)` in a 4-slot runtime-indexed AST heap
(`0..3`) and evaluates them dynamically via `(e idx _)`:

    (p idx op)  -> set node_op[idx] := op (+, -, *, =, <), emit op
    (l idx val) -> set node_lhs[idx] := val, emit val
    (r idx val) -> set node_rhs[idx] := val, emit val
    (e idx _)   -> EVAL: evaluate (node_op[idx] node_lhs[idx] node_rhs[idx])
    (+ a b)     -> direct add
    (- a b)     -> direct sub

Every value/index resolves `'0'..'9'` or `'!'` (`ANS`), enabling data-driven
AST construction and dynamic evaluation in native `fixed19` Malbolge.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._native_eval_add import UNARY
from .cycles import PAIR_GAP, jump_cell, padding, pair_cell, pair_residue
from .native_asm import LAP, STEP, Conflict, Laps, Memory, bootstrap, once, seed as byte_seed
from .native_ir_loop import EOF_WORD, TABLE_LAPS

LOWERING = "fixed19-native-lisp-eval-v1"
INIT_CHAR = ord("0")
AST_SLOTS = 4
_PAD = tuple(padding(i) for i in range(94))

PARAMS = {
    "Y": 82, "W": 114, "U": 115, "V": 45, "C2": 125, "M80": 126,
    "table": 60, "eof": 51, "halt": 59, "slack": 3, "budget": 2800, "P": 68,
    "far": 80 * STEP,
}


def reference(stdin: bytes, initial: int = INIT_CHAR) -> bytes:
    """Expected stdout of the H49 AST-heap `eval` Mini-Lisp REPL on 7-byte frames."""
    node_op = [ord("+")] * AST_SLOTS
    node_a = [initial] * AST_SLOTS
    node_b = [initial] * AST_SLOTS
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

        def eval_ast(aop: int, a: int, b: int) -> int:
            if aop == ord("+"):
                return (a + (b - 48)) % 81
            if aop == ord("-"):
                return (a - (b - 48)) % 81
            if aop == ord("*"):
                return (48 + (((a - 48) % 81) * ((b - 48) % 81))) % 81
            if aop == ord("="):
                return ord("1") if a == b else ord("0")
            return ord("1") if a < b else ord("0")

        slot = v1 - 48
        if op in (ord("+"), ord("-")):
            res = eval_ast(op, v1, v2)
        elif op == ord("p"):
            res = r2
            if 0 <= slot < AST_SLOTS:
                node_op[slot] = r2
        elif op == ord("l"):
            res = v2
            if 0 <= slot < AST_SLOTS:
                node_a[slot] = v2
        elif op == ord("r"):
            res = v2
            if 0 <= slot < AST_SLOTS:
                node_b[slot] = v2
        elif op == ord("e"):
            if 0 <= slot < AST_SLOTS:
                res = eval_ast(node_op[slot], node_a[slot], node_b[slot])
            else:
                res = 0
        else:
            res = 0
        ans = res & 0xFF
        out.append(ans)
        idx += 7
    return bytes(out)


@dataclass(frozen=True, slots=True)
class LispEvalRepl:
    image: bytes
    cells: dict[str, int]
    lowering: str = LOWERING


def build_lisp_eval(rounds: int = 3, params: dict[str, int] | None = None) -> LispEvalRepl:
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

    reserved = {entry - PAIR_GAP, entry, entry + PAIR_GAP, *range(p["eof"] + 1, halt_at + 1)}

    def claim_const(val: int, name: str) -> int:
        for addr in range(46, 124):
            if memory.free(addr) and addr not in reserved:
                memory.claim(addr, val, name)
                return addr
        raise Conflict(f"no room for constant {name}")

    k1 = claim_const(1, "k1")
    k20 = claim_const(20, "k20")  # =
    k21 = claim_const(21, "k21")  # <
    k27 = claim_const(27, "k27")
    k30 = claim_const(30, "k30")  # '3'
    k31 = claim_const(31, "k31")  # '2'
    k32 = claim_const(32, "k32")  # '1'
    k33 = claim_const(33, "k33")  # '0'
    k36 = claim_const(36, "k36")  # '-'
    k38 = claim_const(38, "k38")  # '+'
    k39 = claim_const(39, "k39")  # '*'
    k48 = claim_const(48, "k48")  # '!', +'0', 'r' (114%81=33 -> 48)
    k49 = claim_const(49, "k49")
    k50 = claim_const(50, "k50")  # 'p' (112%81=31 -> 50)
    k54 = claim_const(54, "k54")  # 'l' (108%81=27 -> 54)
    k61 = claim_const(61, "k61")  # 'e' (101%81=20 -> 61)
    k_idx = (k33, k32, k31, k30)

    reg_pool = [
        r
        for r in (*range(128, 150), *range(108, 124))
        if memory.free(r) and r not in reserved
    ]
    op_regs = [reg_pool.pop(0) for _ in range(AST_SLOTS)]
    a_regs = [reg_pool.pop(0) for _ in range(AST_SLOTS)]
    b_regs = [reg_pool.pop(0) for _ in range(AST_SLOTS)]
    ans_reg = reg_pool.pop(0)
    tmp_copy = reg_pool.pop(0)
    for i in range(AST_SLOTS):
        memory.claim(op_regs[i], ord("+"), f"ast_op_{i}")
        memory.claim(a_regs[i], INIT_CHAR, f"ast_a_{i}")
        memory.claim(b_regs[i], INIT_CHAR, f"ast_b_{i}")
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
    drop(r1_reg)
    v2 = resolve_tok(r2_reg)

    m_put_op = eq_const(op_reg, k50)
    m_put_lhs = eq_const(op_reg, k54)
    m_put_rhs = eq_const(op_reg, k48)
    m_eval = eq_const(op_reg, k61)

    ast_op = uniform(0)
    ast_a = uniform(0)
    ast_b = uniform(0)
    for opr, ar, br, k_i in zip(op_regs, a_regs, b_regs, k_idx):
        m_slot = eq_const(v1, k_i)
        wr_op = keep(m_put_op, m_slot)
        wr_a = keep(m_put_lhs, m_slot)
        wr_b = keep(m_put_rhs, m_slot)
        mux_update(opr, r2_reg, wr_op)
        mux_update(ar, v2, wr_a)
        mux_update(br, v2, wr_b)
        drop(wr_op)
        drop(wr_a)
        drop(wr_b)

        t_op = keep(opr, m_slot)
        t_a = keep(ar, m_slot)
        t_b = keep(br, m_slot)
        drop(m_slot)
        n_op = oradd(ast_op, t_op)
        n_a = oradd(ast_a, t_a)
        n_b = oradd(ast_b, t_b)
        drop(ast_op)
        drop(ast_a)
        drop(ast_b)
        drop(t_op)
        drop(t_a)
        drop(t_b)
        ast_op, ast_a, ast_b = n_op, n_a, n_b

    # Wait: remove the duplicate inline mux_update(opr, r2_reg, keep(...)) above!
    # We'll edit that line right after write_file or fix before writing.
    m_not_eval = mask_low4(un(m_eval, (1, 0, 0)))
    eo_a = keep(ast_op, m_eval)
    eo_b = keep(op_reg, m_not_eval)
    eff_op = oradd(eo_a, eo_b)
    drop(eo_a)
    drop(eo_b)

    ea_a = keep(ast_a, m_eval)
    ea_b = keep(v1, m_not_eval)
    eff_a = oradd(ea_a, ea_b)
    drop(ea_a)
    drop(ea_b)

    eb_a = keep(ast_b, m_eval)
    eb_b = keep(v2, m_not_eval)
    eff_b = oradd(eb_a, eb_b)
    drop(eb_a)
    drop(eb_b)
    drop(ast_op)
    drop(ast_a)
    drop(ast_b)
    drop(m_not_eval)
    drop(op_reg)
    drop(v1)

    a_num = mask_low4(add_in_loop(eff_a, k33, rounds))
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
    res_add = mask_low4(add_in_loop(eff_a, y_plus, rounds))
    drop(y_plus)
    k_plus = keep(res_add, m_plus)
    drop(res_add)
    drop(m_plus)
    acc1 = oradd(acc_mul, k_plus)
    drop(acc_mul)
    drop(k_plus)

    m_minus = eq_const(eff_op, k36)
    b_comp = mask_low4(un(eff_b, (2, 1, 0)))
    y_minus = mask_low4(add_in_loop(b_comp, k49, rounds))
    drop(b_comp)
    res_sub = mask_low4(add_in_loop(eff_a, y_minus, rounds))
    drop(y_minus)
    k_minus = keep(res_sub, m_minus)
    drop(res_sub)
    drop(m_minus)
    acc2 = oradd(acc1, k_minus)
    drop(acc1)
    drop(k_minus)

    b_neg = mask_low4(add_in_loop(un(eff_b, (2, 1, 0)), k1, rounds))
    drop(eff_b)
    diff = mask_low4(add_in_loop(eff_a, b_neg, rounds))
    drop(eff_a)
    drop(b_neg)
    c_lt = broadcast_t3_is2(diff)
    c_eq = is_zero4(diff)
    drop(diff)

    m_eq = eq_const(eff_op, k20)
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

    m_lt = eq_const(eff_op, k21)
    drop(eff_op)
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

    m_lr = oradd(m_put_lhs, m_put_rhs)
    drop(m_put_lhs)
    drop(m_put_rhs)
    k_pop = keep(r2_reg, m_put_op)
    drop(r2_reg)
    drop(m_put_op)
    k_lr = keep(v2, m_lr)
    drop(v2)
    drop(m_lr)
    k_ev = keep(eval_res, m_eval)
    drop(m_eval)
    # Also direct + / - when not m_put_op/m_lr/m_eval:
    # Actually eval_res ALREADY computed (+ / -) when not m_eval!
    # Wait: when m_put_op or m_lr, eval_res is 0 (because op_reg is p/l/r), so oradd(eval_res, k_pop, k_lr) is exact!
    drop(k_ev)
    r12 = oradd(eval_res, k_pop)
    drop(eval_res)
    drop(k_pop)
    res = oradd(r12, k_lr)
    drop(r12)
    drop(k_lr)

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
    return LispEvalRepl(
        image,
        {"ANS": ans_reg, "C2": c2, "M80": m80, "halt": halt_at, "landing": landing},
    )

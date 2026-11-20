"""H51: Re-executable fixed19 streaming nested S-expression Mini-Lisp VM v3.

Unifies H48's streaming nested S-expression evaluator (depth-2, arbitrary
whitespace, conditional `jump_c` emit on top-level close) with H50's stateful
VM primitives and 2-arg conditional guard `(? cond val)`:

    (+ a b)     -> add
    (- a b)     -> subtract
    (* a b)     -> multiply (0..9)
    (= a b)     -> '1' if a == b else '0'
    (< a b)     -> '1' if a <  b else '0'
    (? c v)     -> 'v' if c != '0' else '0'
    (s x v)     -> set variable x := v, return v
    (w idx val) -> POKE: heap[idx] := val (idx '0'..'1'), return val
    (r idx _)   -> PEEK: return heap[idx] (idx '0'..'1')
    (D op k)    -> DEF: define f(p, q) = (op p q) if k == '.' else (op p k)
    (C a b)     -> CALL: evaluate f(a, b)

Atoms resolve `'0'..'9'`, `'x'` (variable `x`), `'!'` (`ANS`), `'.'`, `'_'`,
and binary ops (`+`, `-`, `*`, `=`, `<`) when used as arguments (e.g. `(D + .)`).
"""

from __future__ import annotations

from dataclasses import dataclass

from ._native_eval_add import UNARY
from .cycles import PAIR_GAP, jump_cell, padding, pair_cell, pair_residue
from .native_asm import LAP, STEP, Conflict, Laps, Memory, bootstrap, once, seed as byte_seed
from .native_ir_loop import EOF_WORD, TABLE_LAPS

LOWERING = "fixed19-native-lisp-v3"
INIT_CHAR = ord("0")
STACK_DEPTH = 2
HEAP_SIZE = 2
_PAD = tuple(padding(i) for i in range(94))

PARAMS = {
    "Y": 82, "W": 114, "U": 115, "V": 45, "C2": 125, "M80": 126,
    "table": 60, "eof": 51, "halt": 59, "slack": 3, "budget": 3243, "P": 68,
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


def reference(stdin: bytes, initial: int = INIT_CHAR) -> bytes:
    """Expected stdout of the H51 streaming nested S-expression VM v3."""
    var_x = initial
    heap = [initial] * HEAP_SIZE
    fn_op = ord("+")
    fn_k = ord(".")
    ans = initial

    ops: list[int] = []
    args: list[list[int]] = []
    out = bytearray()

    bin_ops = {ord("+"), ord("-"), ord("*"), ord("="), ord("<")}
    kw_ops = {ord("?"), ord("s"), ord("w"), ord("r"), ord("D"), ord("C")}
    all_ops = bin_ops | kw_ops

    def eval_binop(op: int, a: int, b: int) -> int:
        if op == ord("+"):
            return (a + (b - 48)) % 81
        if op == ord("-"):
            return (a - (b - 48)) % 81
        if op == ord("*"):
            return (48 + (((a - 48) % 81) * ((b - 48) % 81))) % 81
        if op == ord("="):
            return ord("1") if a == b else ord("0")
        return ord("1") if a < b else ord("0")

    def push_arg(val: int) -> None:
        if args and len(args[-1]) < 2:
            args[-1].append(val)

    for ch in stdin:
        if ch == 0:
            break
        if ch == ord("("):
            ops.append(0)
            args.append([])
        elif ch == ord(")"):
            if not ops:
                continue
            op = ops.pop()
            argv = args.pop()
            a = argv[0] if len(argv) > 0 else initial
            b = argv[1] if len(argv) > 1 else initial

            if op in bin_ops:
                res = eval_binop(op, a, b)
            elif op == ord("C"):
                arg2 = b if fn_k == ord(".") else fn_k
                res = eval_binop(fn_op, a, arg2)
            elif op == ord("?"):
                res = b if a != ord("0") else ord("0")
            elif op == ord("s"):
                var_x = b
                res = b
            elif op == ord("w"):
                idx = a - 48
                if 0 <= idx < HEAP_SIZE:
                    heap[idx] = b
                res = b
            elif op == ord("r"):
                idx = a - 48
                res = heap[idx] if 0 <= idx < HEAP_SIZE else initial
            elif op == ord("D"):
                fn_op = a
                fn_k = b
                res = b
            else:
                res = initial

            res &= 0xFF
            if not ops:
                ans = res
                out.append(res)
            else:
                push_arg(res)
        elif ch in all_ops and ops and ops[-1] == 0:
            ops[-1] = ch
        elif (
            ord("0") <= ch <= ord("9")
            or ch in (ord("x"), ord("!"), ord("."), ord("_"))
            or (ch in bin_ops and ops and ops[-1] != 0)
        ):
            if ch == ord("x"):
                val = var_x
            elif ch == ord("!"):
                val = ans
            else:
                val = ch
            push_arg(val)

    return bytes(out)


@dataclass(frozen=True, slots=True)
class LispV3Repl:
    image: bytes
    cells: dict[str, int]
    lowering: str = LOWERING


def build_lisp_v3(rounds: int = 3, params: dict[str, int] | None = None) -> LispV3Repl:
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
            slot = laps.off + at if laps.off is not None else None
            if laps.off is None or (
                slot not in reserved
                and not (far <= slot < landing)
                and memory.fits(slot, pointer)
            ):
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
            if (
                z not in reserved
                and (z + 1 not in reserved)
                and not (far <= z < landing)
                and not (far <= z + 1 < landing)
                and (memory.free(z) or memory.cells.get(z) == (0, "zero"))
                and memory.fits(z + 1, target_cell - 22)
            ):
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
    for lag in (-PAIR_GAP, 0, PAIR_GAP):
        memory.claim(entry + lag, y - 22)

    halt_at = p["halt"] + 1
    memory.claim(halt_at, once("halt", halt_at), "halt")

    reserved = {
        entry - PAIR_GAP, entry, entry + PAIR_GAP,
        p["emit_tgt"], p["emit_tgt"] + 5, p["emit_tgt"] + 5 - PAIR_GAP,
        p["skip_tgt"], p["skip_tgt"] + 5, p["skip_tgt"] + 5 - PAIR_GAP,
        *range(p["eof"] + 1, halt_at + 1),
    }

    low_slots = [r for r in range(123, 107, -1) if memory.free(r) and r not in reserved]
    tmp_copy = low_slots[0]
    ch_reg_slot = low_slots[1]
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

    def claim_const(val: int, name: str) -> int:
        for addr in (*range(46, 51), *range(52, 59), *range(61, 82), *range(83, 93)):
            if memory.free(addr) and addr not in reserved:
                memory.claim(addr, val, name)
                return addr
        raise Conflict(f"no room for constant {name}")

    k1 = claim_const(1, "k1")
    k13 = claim_const(13, "k13")   # -68 mod 81 ('D')
    k14 = claim_const(14, "k14")   # -67 mod 81 ('C')
    k18 = claim_const(18, "k18")   # -63 mod 81 ('?')
    k20 = claim_const(20, "k20")   # -61 mod 81 ('=')
    k21 = claim_const(21, "k21")   # -60 mod 81 ('<')
    k23 = claim_const(23, "k23")   # -58 mod 81 ('9'+1)
    k27 = claim_const(27, "k27")
    k32 = claim_const(32, "k32")   # -49 mod 81 ('1')
    k33 = claim_const(33, "k33")   # -48 mod 81 ('0')
    k35 = claim_const(35, "k35")   # -46 mod 81 ('.')
    k36 = claim_const(36, "k36")   # -45 mod 81 ('-')
    k38 = claim_const(38, "k38")   # -43 mod 81 ('+')
    k39 = claim_const(39, "k39")   # -42 mod 81 ('*')
    k40 = claim_const(40, "k40")   # -41 mod 81 (')')
    k41 = claim_const(41, "k41")   # -40 mod 81 ('(')
    k42 = claim_const(42, "k42")   # -120 mod 81 ('x')
    k43 = claim_const(43, "k43")   # -119 mod 81 ('w')
    k47 = claim_const(47, "k47")   # -115 mod 81 ('s')
    k48 = claim_const(48, "k48")   # +'0', -33 ('!'), -114 ('r')
    k49 = claim_const(49, "k49")
    k67 = claim_const(67, "k67")   # -95 mod 81 ('_')
    k79 = claim_const(79, "k79")   # -2 mod 81
    k80 = claim_const(80, "k80")   # -1 mod 81
    k_slot_neg = (k80, k79)
    k_idx = (k33, k32)

    pool_addrs = (*range(128, 150), *range(108, 124), 93, 94)
    reg_pool = [
        r
        for r in pool_addrs
        if memory.free(r) and r not in reserved
    ]
    sp_reg = reg_pool.pop(0)
    op_regs = [reg_pool.pop(0) for _ in range(STACK_DEPTH)]
    v1_regs = [reg_pool.pop(0) for _ in range(STACK_DEPTH)]
    v2_regs = [reg_pool.pop(0) for _ in range(STACK_DEPTH)]
    ac_regs = [reg_pool.pop(0) for _ in range(STACK_DEPTH)]
    var_x = reg_pool.pop(0)
    ans_reg = reg_pool.pop(0)
    fn_op_reg = reg_pool.pop(0)
    fn_k_reg = reg_pool.pop(0)
    heap_regs = [reg_pool.pop(0) for _ in range(HEAP_SIZE)]
    emit_flag_reg = reg_pool.pop(0)
    out_char_reg = reg_pool.pop(0)

    memory.claim(sp_reg, 0, "sp_reg")
    for i in range(STACK_DEPTH):
        memory.claim(op_regs[i], 0, f"op_{i}")
        memory.claim(v1_regs[i], INIT_CHAR, f"v1_{i}")
        memory.claim(v2_regs[i], INIT_CHAR, f"v2_{i}")
        memory.claim(ac_regs[i], 0, f"ac_{i}")
    memory.claim(var_x, INIT_CHAR, "var_x")
    memory.claim(ans_reg, INIT_CHAR, "ans_reg")
    memory.claim(fn_op_reg, ord("+"), "fn_op")
    memory.claim(fn_k_reg, ord("."), "fn_k")
    for i, hr in enumerate(heap_regs):
        memory.claim(hr, INIT_CHAR, f"heap_{i}")
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

    def or_all(*regs: int) -> int:
        acc = copy(regs[0])
        for r in regs[1:]:
            nxt = oradd(acc, r)
            drop(acc)
            acc = nxt
        return acc

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

    def broadcast_t0(r: int) -> int:
        b0 = keep(r, k1)
        drop(r)
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
        return broadcast_t0(eq0)

    def eq_const(r: int, k_neg: int) -> int:
        d = mask_low4(add_in_loop(r, k_neg, rounds))
        m = is_zero4(d)
        drop(d)
        return m

    def fold_eq_any(val_r: int, k_list: tuple[int, ...]) -> int:
        acc = eq_const(val_r, k_list[0])
        for k in k_list[1:]:
            t = eq_const(val_r, k)
            nxt = oradd(acc, t)
            drop(acc)
            drop(t)
            acc = nxt
        return acc

    def mul_0_to_9(a_r: int, b_r: int) -> int:
        prod = uniform(0)
        a_scaled = a_r
        b_cur = b_r
        for step in range(3):
            t0 = keep(b_cur, k1)
            eq1_b0 = un(t0, (0, 1, 0))
            m1 = broadcast_t0(eq1_b0)
            k_1 = keep(a_scaled, m1)
            drop(m1)

            eq2_b0 = un(t0, (0, 0, 1))
            drop(t0)
            m2 = broadcast_t0(eq2_b0)
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

    def mux_select(mask: int, a_if_1: int, b_if_0: int) -> int:
        not_m = mask_low4(un(mask, (1, 0, 0)))
        pa = keep(a_if_1, mask)
        pb = keep(b_if_0, not_m)
        drop(not_m)
        res = oradd(pa, pb)
        drop(pa)
        drop(pb)
        return res

    def mux_update(reg: int, new_val: int, wr_mask: int) -> None:
        updated = mux_select(wr_mask, new_val, reg)
        copy(updated, reg)
        drop(updated)

    def eval_binop_regs(v1_r: int, v2_r: int, get_op: callable) -> int:
        a_num = mask_low4(add_in_loop(v1_r, k33, rounds))
        b_num = mask_low4(add_in_loop(v2_r, k33, rounds))
        prod_num = mul_0_to_9(a_num, b_num)
        res_mul = mask_low4(add_in_loop(prod_num, k48, rounds))
        drop(prod_num)
        op_r = get_op()
        m_mul = eq_const(op_r, k39)
        acc = keep(res_mul, m_mul)
        drop(res_mul)
        drop(m_mul)

        m_plus = eq_const(op_r, k38)
        y_plus = mask_low4(add_in_loop(v2_r, k33, rounds))
        res_add = mask_low4(add_in_loop(v1_r, y_plus, rounds))
        drop(y_plus)
        k_plus = keep(res_add, m_plus)
        drop(res_add)
        drop(m_plus)
        acc1 = oradd(acc, k_plus)
        drop(acc)
        drop(k_plus)

        m_minus = eq_const(op_r, k36)
        v2_comp = mask_low4(un(v2_r, (2, 1, 0)))
        y_minus = mask_low4(add_in_loop(v2_comp, k49, rounds))
        drop(v2_comp)
        res_sub = mask_low4(add_in_loop(v1_r, y_minus, rounds))
        drop(y_minus)
        k_minus = keep(res_sub, m_minus)
        drop(res_sub)
        drop(m_minus)
        acc2 = oradd(acc1, k_minus)
        drop(acc1)
        drop(k_minus)

        v2_neg = mask_low4(add_in_loop(un(v2_r, (2, 1, 0)), k1, rounds))
        diff = mask_low4(add_in_loop(v1_r, v2_neg, rounds))
        drop(v2_neg)
        drop(v2_r)

        c_eq = is_zero4(diff)
        m_eq = eq_const(op_r, k20)
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

        c_lt = broadcast_t3_is2(diff)
        drop(diff)
        m_lt = eq_const(op_r, k21)
        k_lt_raw = keep(c_lt, m_lt)
        drop(c_lt)
        b_lt = keep(k_lt_raw, k1)
        drop(k_lt_raw)
        res_lt = mask_low4(add_in_loop(b_lt, k48, rounds))
        drop(b_lt)
        k_lt = keep(res_lt, m_lt)
        drop(res_lt)
        drop(m_lt)
        out_r = oradd(acc3, k_lt)
        drop(acc3)
        drop(k_lt)
        drop(op_r)
        return out_r

    # ── Read input byte & process sequentially ────────────────────────────────
    ch_reg = copy(ch_reg_slot)

    # 1. Handle '(' -> push (sp += 1, init new frame op=0, ac=0)
    m_open = eq_const(ch_reg, k41)
    sp_inc = mask_low4(add_in_loop(sp_reg, k1, rounds))
    mux_update(sp_reg, sp_inc, m_open)
    drop(sp_inc)
    for i, k_neg in enumerate(k_slot_neg):
        m_slot = eq_const(sp_reg, k_neg)
        wr_init = keep(m_open, m_slot)
        drop(m_slot)
        z_reg = uniform(0)
        mux_update(op_regs[i], z_reg, wr_init)
        mux_update(ac_regs[i], z_reg, wr_init)
        drop(z_reg)
        drop(wr_init)
    drop(m_open)

    # 2. Handle operator (when op_regs[sp-1] == 0)
    # Snapshot op_was_set BEFORE Section 2 writes op_regs[i] so that:
    # (a) a binary op token written as operator is not also pushed as v1 in Section 3, and
    # (b) 'r' (114 ≡ 33 = '!' mod 81) is not misread as an atom arg when opening (r ...).
    op_was_set_list: list[int] = []
    m_any_op = fold_eq_any(
        ch_reg,
        (k38, k36, k39, k20, k21, k18, k47, k43, k48, k13, k14),
    )
    for i, k_neg in enumerate(k_slot_neg):
        m_slot = eq_const(sp_reg, k_neg)
        m_op_slot = keep(m_any_op, m_slot)
        drop(m_slot)
        op_z = is_zero4(op_regs[i])
        op_was_set_list.append(mask_low4(un(op_z, (1, 0, 0))))
        wr_op = keep(m_op_slot, op_z)
        drop(m_op_slot)
        drop(op_z)
        mux_update(op_regs[i], ch_reg, wr_op)
        drop(wr_op)
    drop(m_any_op)

    # 3. Handle argument atoms
    m_x = eq_const(ch_reg, k42)
    m_ans = eq_const(ch_reg, k48)
    val_x = mux_select(m_x, var_x, ch_reg)
    val_reg = mux_select(m_ans, ans_reg, val_x)
    drop(val_x)
    m_atom_2 = oradd(m_x, m_ans)
    drop(m_x)
    drop(m_ans)

    ch_m48 = mask_low4(add_in_loop(ch_reg, k33, rounds))
    ch_ge48 = mask_low4(un(broadcast_t3_is2(ch_m48), (1, 0, 0)))
    drop(ch_m48)
    ch_m58 = mask_low4(add_in_loop(ch_reg, k23, rounds))
    ch_lt58 = broadcast_t3_is2(ch_m58)
    drop(ch_m58)
    m_digit = keep(ch_ge48, ch_lt58)
    drop(ch_ge48)
    drop(ch_lt58)

    m_sym = fold_eq_any(ch_reg, (k35, k67))
    m_atom_1 = oradd(m_digit, m_sym)
    drop(m_digit)
    drop(m_sym)
    m_atom_always = oradd(m_atom_1, m_atom_2)
    drop(m_atom_1)
    drop(m_atom_2)

    m_bin_op = fold_eq_any(ch_reg, (k38, k36, k39, k20, k21))
    m_any_arg = oradd(m_atom_always, m_bin_op)
    drop(m_bin_op)
    drop(m_atom_always)

    for i, k_neg in enumerate(k_slot_neg):
        m_slot = eq_const(sp_reg, k_neg)
        op_set = op_was_set_list[i]
        m_slot_ready = keep(m_slot, op_set)
        drop(m_slot)
        drop(op_set)
        m_arg_slot = keep(m_any_arg, m_slot_ready)
        drop(m_slot_ready)

        ac_z = is_zero4(ac_regs[i])
        wr_v1 = keep(m_arg_slot, ac_z)
        drop(ac_z)
        ac_1 = eq_const(ac_regs[i], k80)
        wr_v2 = keep(m_arg_slot, ac_1)
        drop(ac_1)
        drop(m_arg_slot)

        mux_update(v1_regs[i], val_reg, wr_v1)
        mux_update(v2_regs[i], val_reg, wr_v2)
        wr_ac = oradd(wr_v1, wr_v2)
        drop(wr_v1)
        drop(wr_v2)
        ac_inc = mask_low4(add_in_loop(ac_regs[i], k1, rounds))
        mux_update(ac_regs[i], ac_inc, wr_ac)
        drop(ac_inc)
        drop(wr_ac)

    drop(m_any_arg)
    drop(val_reg)
    drop(ch_reg)

    # 4. Handle ')' -> read top frame, evaluate, pop, emit or push to parent
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

    # 4a. Evaluate binary ops + user fn Call (C a b) via shared eval_binop_regs
    m_call = eq_const(cur_op, k14)
    is_dot = eq_const(fn_k_reg, k35)
    fn_arg2 = mux_select(is_dot, cur_v2, fn_k_reg)
    drop(is_dot)
    eff_b = mux_select(m_call, fn_arg2, cur_v2)
    drop(fn_arg2)
    drop(m_call)

    def _get_eff_op() -> int:
        mc = eq_const(cur_op, k14)
        eo = mux_select(mc, fn_op_reg, cur_op)
        drop(mc)
        return eo

    bin_res = eval_binop_regs(cur_v1, eff_b, _get_eff_op)
    eval_res = bin_res

    def acc_eval(part: int) -> None:
        nonlocal eval_res
        nxt = oradd(eval_res, part)
        drop(eval_res)
        drop(part)
        eval_res = nxt

    # 4b. Evaluate (? cond val) -> return val if cond != '0' else '0'
    m_if = eq_const(cur_op, k18)
    c_is0 = eq_const(cur_v1, k33)
    c_nz = mask_low4(un(c_is0, (1, 0, 0)))
    drop(c_is0)
    if_val = mux_select(c_nz, cur_v2, k48)
    drop(c_nz)
    res_if = keep(if_val, m_if)
    drop(if_val)
    drop(m_if)
    acc_eval(res_if)

    m_close = eq_const(ch_reg_slot, k40)

    # 4c. Evaluate (s x v)
    m_set = eq_const(cur_op, k47)
    wr_set = keep(m_close, m_set)
    mux_update(var_x, cur_v2, wr_set)
    drop(wr_set)
    res_set = keep(cur_v2, m_set)
    drop(m_set)
    acc_eval(res_set)

    # 4d. Evaluate (w idx val)
    m_write = eq_const(cur_op, k43)
    wr_write = keep(m_close, m_write)
    for hr, k_neg in zip(heap_regs, k_idx):
        m_i = eq_const(cur_v1, k_neg)
        wr_i = keep(wr_write, m_i)
        drop(m_i)
        mux_update(hr, cur_v2, wr_i)
        drop(wr_i)
    drop(wr_write)
    res_write = keep(cur_v2, m_write)
    drop(m_write)
    acc_eval(res_write)

    # 4e. Evaluate (r idx _)
    m_read = eq_const(cur_op, k48)
    read_val = uniform(0)
    for hr, k_neg in zip(heap_regs, k_idx):
        m_i = eq_const(cur_v1, k_neg)
        t_h = keep(hr, m_i)
        drop(m_i)
        nxt = oradd(read_val, t_h)
        drop(t_h)
        copy(nxt, read_val)
        drop(nxt)
    res_read = keep(read_val, m_read)
    drop(read_val)
    drop(m_read)
    acc_eval(res_read)

    # 4f. Evaluate (D op k)
    m_def = eq_const(cur_op, k13)
    drop(cur_op)
    wr_def = keep(m_close, m_def)
    mux_update(fn_op_reg, cur_v1, wr_def)
    mux_update(fn_k_reg, cur_v2, wr_def)
    drop(wr_def)
    drop(cur_v1)
    res_def = keep(cur_v2, m_def)
    drop(cur_v2)
    drop(m_def)
    acc_eval(res_def)

    # Pop sp_reg when m_close
    sp_dec = mask_low4(add_in_loop(sp_reg, k80, rounds))
    mux_update(sp_reg, sp_dec, m_close)
    drop(sp_dec)

    # Top-level close -> update ANS & emit; nested close -> push into parent frame
    sp_is0 = is_zero4(sp_reg)
    do_emit = keep(m_close, sp_is0)
    not_sp0 = mask_low4(un(sp_is0, (1, 0, 0)))
    drop(sp_is0)
    do_push_parent = keep(m_close, not_sp0)
    drop(not_sp0)
    drop(m_close)

    mux_update(ans_reg, eval_res, do_emit)
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
        drop(ac_z)
        ac_1 = eq_const(ac_regs[i], k80)
        wr_v2 = keep(m_p, ac_1)
        drop(ac_1)
        drop(m_p)
        mux_update(v1_regs[i], eval_res, wr_v1)
        mux_update(v2_regs[i], eval_res, wr_v2)
        wr_ac = oradd(wr_v1, wr_v2)
        drop(wr_v1)
        drop(wr_v2)
        ac_inc = mask_low4(add_in_loop(ac_regs[i], k1, rounds))
        mux_update(ac_regs[i], ac_inc, wr_ac)
        drop(ac_inc)
        drop(wr_ac)
    drop(do_push_parent)
    drop(eval_res)

    # Reset input registers and load out_char_reg into A before branching
    reset(tmp_copy, 1)
    reset(ch_reg_slot, 1)
    load(out_char_reg)

    # Conditional branch on emit_flag_reg (0 -> skip_tgt; 1 -> emit_tgt)
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
    disk_seeds: dict[int, tuple[int, str]] = {}
    for address, value in constants:
        rot_times = byte_seed(value)[1]
        if rot_times > 0:
            disk_seeds[address] = memory.cells[address]
        code.at(address, "rotate", rot_times)
        if rot_times > 0:
            memory.cells[address] = (value, "seed_ready")
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
        if address in disk_seeds:
            value = disk_seeds[address][0]
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
    return LispV3Repl(
        image,
        {
            "SP": sp_reg,
            "X": var_x,
            "ANS": ans_reg,
            "EMIT": emit_flag_reg,
            "OUT": out_char_reg,
            "halt": halt_at,
            "landing": landing,
        },
    )

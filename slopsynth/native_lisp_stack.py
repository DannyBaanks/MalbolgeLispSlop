"""H38: Re-executable fixed19 streaming S-expression evaluator with stack (arbitrary depth).

Reads 1 byte per loop iteration and evaluates variable-length, arbitrarily
nested binary S-expressions over `+` and `-` (up to 4 levels deep, packed as
4-trit slots in `val_stack` and `op_stack`), halting in-image on `0` or EOF:

    (+ 2 3)                   -> 5
    (+ 1 (+ 2 3))             -> 6
    (- (+ 3 6) (- 5 2))       -> 6
    (+ (+ 1 (+ 2 3)) (- 9 6)) -> 9

Architecture:
1. Loop head copies `ch` into `ch_reg` (pre-reset to `ALL_1` in the prologue
   and at the end of the loop body) while preserving `A == ch`, then dispatches
   via `table`: `0`/`EOF` -> `halt`, `1..255` -> `resume`.
2. Single parity-locked loop body (`resume`) runs on every non-zero byte:
   - Classifies `ch_reg` in 4 trits (`m_dig`, `m_close`, `m_plus`, `m_minus`).
   - Updates `op_stack` and `val_stack` branchlessly via 16-trit masks,
     evaluating `(op a b)` when `ch == ')'` and computing `emit_flag =
     m_close AND (new_op_stack == 0)`.
3. At the end of the loop body, loads `res_out` into `A` and executes a parity-
   invariant 2-way `dispatch` on `branch_reg in {0, 1}`:
   - `0` (`noemit`): jumps directly back to `landing`.
   - `1` (`emit`): executes `output` and jumps back to `landing`.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._native_eval_add import UNARY
from .cycles import PAIR_GAP, jump_cell, padding, pair_cell, pair_residue
from .native_asm import LAP, STEP, Conflict, Laps, Memory, bootstrap, once, seed as byte_seed
from .native_ir_loop import EOF_WORD, TABLE_LAPS

LOWERING = "fixed19-native-lisp-stack-v1"
_PAD = tuple(padding(i) for i in range(94))

PARAMS = {
    "Y": 82, "W": 114, "U": 115, "V": 45, "C2": 125, "M80": 126, "M12": 124,
    "table": 60, "eof": 51, "halt": 59,
    "noemit_ptr": 71, "emit_ptr": 73,
    "slack": 3, "budget": 8000, "P": 68,
    "far": 80 * STEP,
}


def reference(stdin: bytes) -> bytes:
    """Expected stdout of the H38 streaming stack evaluator on `stdin`."""
    out = bytearray()
    ops: list[int] = []
    vals: list[int] = []
    for ch in stdin:
        if ch == 0:
            break
        if ch in (ord("+"), ord("-")):
            ops.append(ch)
        elif 48 <= ch <= 57:
            vals.append(ch)
        elif ch == ord(")"):
            op = ops.pop()
            b = vals.pop()
            a = vals.pop()
            if op == ord("+"):
                res = (a + (b - 48)) % 81
            else:
                res = (a - (b - 48)) % 81
            vals.append(res)
            if not ops:
                out.append(res & 0xFF)
                vals.clear()
                break
    return bytes(out)


@dataclass(frozen=True, slots=True)
class LispStackRepl:
    image: bytes
    cells: dict[str, int]
    lowering: str = LOWERING


def build_lisp_stack(rounds: int = 3, params: dict[str, int] | None = None) -> LispStackRepl:
    p = PARAMS if params is None else params
    memory = Memory()
    y, w, u, v, c2, m80, m12 = p["Y"], p["W"], p["U"], p["V"], p["C2"], p["M80"], p["M12"]
    for name, s in (("Y", 0), ("W", 0), ("V", 0), ("U", 2), ("C2", 0), ("M80", 0), ("M12", 0)):
        memory.claim(p[name], s, name)

    def align_seedable(addr: int) -> int:
        for k in range(4, 18):
            s = 3**k
            aligned = addr + (-addr % s)
            if aligned // s < 128:
                return aligned
        raise Conflict(f"cannot align {addr} to byte * 3^k")

    far = p["far"]
    landing = align_seedable(far + p["budget"])
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
            slot = None if laps.off is None else laps.off + at
            if slot is None or (0 <= slot < far and memory.fits(slot, pointer)):
                break
            lap += 1
            if lap > laps.lap + 1000:
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
            if 0 <= z < far and (memory.free(z) or memory.cells.get(z) == (0, "zero")) and memory.fits(z + 1, target_cell - 22):
                break
            rot_lap += 1
            if rot_lap > laps.lap + 1000:
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

    reg_pool = [r for r in range(128, 150) if memory.free(r)]
    ch_reg = reg_pool.pop(0)
    val_stack = reg_pool.pop(0)
    op_stack = reg_pool.pop(0)
    branch_reg = reg_pool.pop(0)
    tmp_copy = reg_pool.pop(0)
    memory.claim(ch_reg, 0, "ch_reg")
    memory.claim(val_stack, 0, "val_stack")
    memory.claim(op_stack, 0, "op_stack")
    memory.claim(branch_reg, 0, "branch_reg")
    memory.claim(tmp_copy, 0, "tmp_copy")
    for r in reg_pool:
        memory.claim(r, 0, f"reg_{r}")
    free_regs = list(reg_pool)

    for lag in (0, PAIR_GAP):
        memory.claim(p["eof"] + 5 - lag, p["halt"])
    halt_at = p["halt"] + 1
    memory.claim(halt_at, once("halt", halt_at), "halt")

    # Save incoming byte `ch` into `ch_reg` (both `tmp_copy` and `ch_reg` are pre-reset to ALL_1)
    access_any(tmp_copy)
    access_any(ch_reg)
    access_any(y)
    access_any(w)
    move(w - LAP, exact=True)
    laps.lap += 1
    dispatch = pair("move", laps.lap)
    laps.lap += 8
    table_move = pair("move", laps.lap)
    table = table_move - dispatch
    for byte in range(1, 256):
        memory.claim(table + byte, p["table"])
    memory.claim(table, p["eof"])
    memory.claim(table + EOF_WORD, p["eof"])
    jump_a = table_move + PAIR_GAP + 1
    resume = align_seedable(jump_a + 1)
    for lag in (0, PAIR_GAP):
        constants.append((p["table"] + 5 - lag, resume))

    def claim_const(val: int, name: str) -> int:
        for addr in range(46, 124):
            if addr in (
                p["noemit_ptr"] + 1, p["noemit_ptr"] + 5,
                p["emit_ptr"] + 1, p["emit_ptr"] + 5,
                p["table"] + 1, p["table"] + 5,
                p["eof"] + 1, p["eof"] + 5,
                jb_d, jb_d - PAIR_GAP,
            ):
                continue
            if memory.free(addr) and addr not in (entry - PAIR_GAP, entry, entry + PAIR_GAP):
                memory.claim(addr, val, name)
                return addr
        raise Conflict(f"no room for constant {name}")

    k1 = claim_const(1, "k1")
    k27 = claim_const(27, "k27")
    k33 = claim_const(33, "k33")
    k36 = claim_const(36, "k36")
    k38 = claim_const(38, "k38")
    k40 = claim_const(40, "k40")
    k49 = claim_const(49, "k49")

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

    def mask_low12(r: int) -> int:
        m12_01 = un(m12, (0, 1, 1))
        masked = keep(r, m12_01)
        drop(m12_01)
        copy(masked, r)
        drop(masked)
        return r

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

    def broadcast_t3(r: int) -> int:
        t3 = unary_ip(keep(r, k27), (0, 1, 1))
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
        eq0 = keep(unary_ip(nz0, (1, 0, 0)), k1)
        out_r = broadcast_t0(eq0)
        drop(eq0)
        return out_r

    def expand4_to16(m4: int) -> int:
        s1 = copy(m4)
        for _ in range(4):
            shl(s1)
        m8 = oradd(m4, s1)
        drop(s1)
        m8_hi = copy(m8)
        for _ in range(8):
            shl(m8_hi)
        m16 = oradd(m8, m8_hi)
        drop(m8)
        drop(m8_hi)
        return m16

    def push_stack(stack_reg: int, val_r: int) -> int:
        st_shl = mask_low12(copy(stack_reg))
        for _ in range(4):
            shl(st_shl)
        v4 = mask_low4(copy(val_r))
        new_st = oradd(v4, st_shl)
        drop(v4)
        drop(st_shl)
        return new_st

    def pop_stack_ro(stack_reg: int) -> tuple[int, int]:
        top = keep(stack_reg, k40)
        rest = copy(stack_reg)
        for _ in range(4):
            rotate_reg(rest)
        mask_low12(rest)
        return top, rest

    # ---- Classify ch_reg: m_close, m_plus, m_minus
    ch40 = mask_low4(add_in_loop(ch_reg, k40, rounds))
    m_close = is_zero4(ch40)
    drop(ch40)

    ch38 = mask_low4(add_in_loop(ch_reg, k38, rounds))
    m_plus_tok = is_zero4(ch38)
    drop(ch38)

    ch36 = mask_low4(add_in_loop(ch_reg, k36, rounds))
    m_minus_tok = is_zero4(ch36)
    drop(ch36)

    m_op = oradd(m_plus_tok, m_minus_tok)
    drop(m_plus_tok)
    drop(m_minus_tok)

    # ---- Speculative stack updates:
    # 1. op_stack: push(ch_reg) if m_op; pop if m_close; keep if neither
    op_pushed = push_stack(op_stack, ch_reg)
    op_top, op_popped = pop_stack_ro(op_stack)

    m16_op = expand4_to16(m_op)
    m16_close = expand4_to16(m_close)
    m_oc = oradd(m_op, m_close)
    drop(m_op)
    m_keep_op = mask_low4(un(m_oc, (1, 0, 0)))
    drop(m_oc)
    m16_keep_op = expand4_to16(m_keep_op)
    drop(m_keep_op)

    kop_1 = keep(op_pushed, m16_op)
    kop_2 = keep(op_popped, m16_close)
    kop_3 = keep(op_stack, m16_keep_op)
    drop(op_pushed)
    drop(m16_op)
    drop(m16_close)
    drop(m16_keep_op)
    k_o12 = oradd(kop_1, kop_2)
    drop(kop_1)
    drop(kop_2)
    new_op_stack = oradd(k_o12, kop_3)
    drop(k_o12)
    drop(kop_3)
    copy(new_op_stack, op_stack)
    drop(new_op_stack)

    # 2. Evaluate (op_top a_top b_top) -> res_close:
    b_top, val_after1 = pop_stack_ro(val_stack)
    a_top, val_after2 = pop_stack_ro(val_after1)
    drop(val_after1)

    op_rel = mask_low4(add_in_loop(op_top, k36, rounds))
    drop(op_top)
    m_eval_plus = mask_low4(unary_ip(op_rel, (0, 1, 1)))
    m_eval_minus = mask_low4(un(m_eval_plus, (1, 0, 0)))

    y_plus = mask_low4(add_in_loop(b_top, k33, rounds))
    b_comp = mask_low4(un(b_top, (2, 1, 0)))
    drop(b_top)
    y_minus = mask_low4(add_in_loop(b_comp, k49, rounds))
    drop(b_comp)

    kp = keep(y_plus, m_eval_plus)
    km = keep(y_minus, m_eval_minus)
    drop(y_plus)
    drop(y_minus)
    drop(m_eval_plus)
    drop(m_eval_minus)
    y_sel = oradd(kp, km)
    drop(kp)
    drop(km)

    res_close = mask_low4(add_in_loop(a_top, y_sel, rounds))
    drop(a_top)
    drop(y_sel)

    # 3. emit_flag = m_close AND is_zero4(op_popped)
    op_empty = is_zero4(op_popped)
    drop(op_popped)
    emit_mask = keep(m_close, op_empty)
    drop(op_empty)
    branch_bit = keep(emit_mask, k1)
    copy(branch_bit, branch_reg)
    drop(branch_bit)

    # 4. val_stack: push(ch_reg) if m_dig; push(res_close) if m_close & !emit; 0 if emit; keep otherwise
    ch33 = mask_low4(add_in_loop(ch_reg, k33, rounds))
    m_not_dig = broadcast_t3(ch33)
    drop(ch33)
    m_dig = mask_low4(un(m_not_dig, (1, 0, 0)))
    drop(m_not_dig)

    m_dc = oradd(m_dig, m_close)
    m_keep_val = mask_low4(un(m_dc, (1, 0, 0)))
    drop(m_dc)

    m16_dig = expand4_to16(m_dig)
    drop(m_dig)
    val_pushed_dig = push_stack(val_stack, ch_reg)
    kv_1 = keep(val_pushed_dig, m16_dig)
    drop(val_pushed_dig)
    drop(m16_dig)

    m_not_emit = mask_low4(un(emit_mask, (1, 0, 0)))
    drop(emit_mask)
    m_close_noemit = keep(m_close, m_not_emit)
    drop(m_close)
    drop(m_not_emit)
    m16_cne = expand4_to16(m_close_noemit)
    drop(m_close_noemit)
    val_pushed_close = push_stack(val_after2, res_close)
    drop(val_after2)
    kv_2 = keep(val_pushed_close, m16_cne)
    drop(val_pushed_close)
    drop(m16_cne)

    m16_keep_val = expand4_to16(m_keep_val)
    drop(m_keep_val)
    kv_3 = keep(val_stack, m16_keep_val)
    drop(m16_keep_val)

    k_v12 = oradd(kv_1, kv_2)
    drop(kv_1)
    drop(kv_2)
    new_val_stack = oradd(k_v12, kv_3)
    drop(k_v12)
    drop(kv_3)
    copy(new_val_stack, val_stack)
    drop(new_val_stack)

    # Pre-reset tmp_copy and ch_reg to ALL_1 for the next pass's head, then load res_close into A!
    reset(tmp_copy, 1)
    reset(ch_reg, 1)
    load(res_close)
    drop(res_close)

    # ---- Parity-invariant 2-way dispatch on branch_reg in {0, 1}:
    move_any(branch_reg - LAP)
    laps.lap += 1
    b_disp = pair("move", laps.lap)
    laps.lap += TABLE_LAPS
    b_tmove = pair("move", laps.lap)
    b_table = b_tmove - b_disp
    memory.claim(b_table + 0, p["noemit_ptr"])
    memory.claim(b_table + 1, p["emit_ptr"])
    jump_b_disp = b_tmove + PAIR_GAP + 1

    extra_jumps: list[int] = [jump_a, jump_b_disp]

    def make_tail(ptr_name: str, prev_end: int, emit_out: bool) -> int:
        b_start = align_seedable(prev_end + 1)
        for lag in (0, PAIR_GAP):
            constants.append((p[ptr_name] + 5 - lag, b_start))
        laps.off = p[ptr_name] + 5 - b_start
        laps.lap = (b_start - base) // LAP
        if position(laps.lap, "output") <= b_start:
            laps.lap += 1
        if emit_out:
            last_p = position(laps.lap, "output")
            if last_p <= b_start:
                laps.lap += 1
            put("output", b_start)
            laps.lap += 1
        # Place `move(p["P"])` and claim BOTH `slot` and `slot - PAIR_GAP` with p["P"]
        # so odd and even parities of `b_tmove` land identically at `landing`!
        lap = laps.lap
        while True:
            at = position(lap, "move")
            slot = laps.off + at
            if (
                0 <= slot < far
                and 0 <= slot - PAIR_GAP < far
                and memory.fits(slot, p["P"])
                and memory.fits(slot - PAIR_GAP, p["P"])
            ):
                break
            lap += 1
            if lap > laps.lap + 1000:
                raise Conflict("no room for parity-invariant tail move")
        pair("move", lap)
        laps.off = p["P"] - at
        laps.lap = lap
        jb = at + 22 + PAIR_GAP + 1 + p["slack"]
        for lag in (0, PAIR_GAP):
            constants.append((laps.off + jb - lag, landing))
        extra_jumps.append(jb)
        return jb

    jb_noemit = make_tail("noemit_ptr", jump_b_disp, emit_out=False)
    jb_emit = make_tail("emit_ptr", jb_noemit, emit_out=True)

    constants = list(dict.fromkeys(constants))
    for address, value in constants:
        memory.claim(address, byte_seed(value)[0], "seed")

    def scratch(s: int) -> int:
        for address in range(42, 127):
            if memory.free(address):
                memory.claim(address, s, "scratch")
                return address
        raise Conflict("no room for a prologue cell")

    code = bootstrap(memory, far=far)
    for address, value in constants:
        code.at(address, "rotate", byte_seed(value)[1])
    s1, c125, c121, temp, temp2, zero_p, s26, s80 = (
        scratch(s) for s in (26, 125, 121, 0, 0, 0, 26, 80)
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
    code.at(m12, "crazy")
    code.at(s80, "rotate", 18)
    code.at(m12, "crazy")
    code.at(s80, "rotate", 14)
    code.at(m12, "crazy")
    code.at(s80, "rotate", 14)
    code.at(m12, "crazy")
    code.at(zero_p, "rotate")
    code.at(temp2, "crazy")
    code.at(m12, "crazy")
    # Pre-reset tmp_copy and ch_reg to ALL_1 for pass 0 head:
    code.at(zero_p, "rotate")
    code.at(tmp_copy, "crazy")
    code.at(zero_p, "rotate")
    code.at(ch_reg, "crazy")

    for _ in range(7000):
        pointer = entry - PAIR_GAP - (first_move - code.c)
        if code.c >= landing:
            raise Conflict("prologue is longer than its budget")
        if 0 <= pointer < 128 and memory.fits(code.d, pointer):
            code.emit("move")
            break
        code.nop()
    else:
        raise Conflict("no entry pointer")

    end = jb_emit
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
    for at in extra_jumps:
        if cells[at] is not None:
            raise Conflict("jump overlaps")
        cells[at] = jump_cell(at)
    image = bytes((_PAD[i % 94] if i >= far else 0) if value is None else value for i, value in enumerate(cells))
    return LispStackRepl(image, {"CH": ch_reg, "VAL_STACK": val_stack, "OP_STACK": op_stack, "BRANCH": branch_reg, "C2": c2, "M80": m80, "M12": m12, "halt": halt_at, "landing": landing})

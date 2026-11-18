"""H36: Re-executable fixed19 Lisp REPL loop with named variables (`x`, `y`, `z`).

Evaluates a stream of 7-byte S-expressions in a native re-executable `fixed19`
loop, halting in-image on `0` or EOF:

    (= x 5)   -> binds x := 5 and emits '5'
    (+ x y)   -> adds resolved operands (digits '0'..'9' or variables x/y/z)
    (- z 2)   -> subtracts resolved operands

Variables `x`, `y`, `z` are initialized to `'0'` (48) and persist across loop
iterations.

Architecture:
1. `(op + 38) mod 81` maps `'+'` -> `0`, `'-'` -> `2` (trit 0), `'='` -> `18`
   (trit 2), producing orthogonal 4-trit masks `m_plus`, `m_minus`, `m_set`.
2. `(tok + 42) mod 81` maps `'0'..'9'` -> `9..18` (trit 2 != 0) and
   `'x','y','z'` -> `0, 1, 2` (trit 2 == 0, discriminated by trit 0),
   resolving each operand in-loop without branching.
3. For `(= var val)`, conditional muxing updates the targeted register
   (`var_x`, `var_y`, or `var_z`) while preserving the other two.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._native_eval_add import UNARY
from .cycles import PAIR_GAP, jump_cell, padding, pair_cell, pair_residue
from .native_asm import LAP, STEP, Conflict, Laps, Memory, bootstrap, once, seed as byte_seed
from .native_ir_loop import EOF_WORD, TABLE_LAPS

LOWERING = "fixed19-native-lisp-env-v1"
VAR0 = ord("0")
_PAD = tuple(padding(i) for i in range(94))

PARAMS = {
    "Y": 82, "W": 114, "U": 115, "V": 45, "C2": 125, "M80": 126,
    "table": 60, "eof": 51, "halt": 59, "slack": 3, "budget": 2000, "P": 68,
    "far": 80 * STEP,
}


def reference(stdin: bytes, initial: int = VAR0) -> bytes:
    """Expected stdout of the H36 named-variable REPL loop on 7-byte frames."""
    env = {ord("x"): initial, ord("y"): initial, ord("z"): initial}
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
        v1 = env.get(r1, r1)
        v2 = env.get(r2, r2)
        if op == ord("+"):
            res = (v1 + (v2 - 48)) % 81
        elif op == ord("-"):
            res = (v1 - (v2 - 48)) % 81
        else:
            res = v2
            if r1 in env:
                env[r1] = res & 0xFF
        out.append(res & 0xFF)
        idx += 7
    return bytes(out)


@dataclass(frozen=True, slots=True)
class LispEnvRepl:
    image: bytes
    cells: dict[str, int]
    lowering: str = LOWERING


def build_lisp_env(rounds: int = 3, params: dict[str, int] | None = None) -> LispEnvRepl:
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
    k38 = claim_const(38, "k38")
    k42 = claim_const(42, "k42")
    k49 = claim_const(49, "k49")

    reg_pool = [r for r in range(128, 150) if memory.free(r)]
    var_x = reg_pool.pop(0)
    var_y = reg_pool.pop(0)
    var_z = reg_pool.pop(0)
    tmp_copy = reg_pool.pop(0)
    memory.claim(var_x, VAR0, "var_x")
    memory.claim(var_y, VAR0, "var_y")
    memory.claim(var_z, VAR0, "var_z")
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

    def broadcast_t2(r: int) -> int:
        t2 = unary_ip(keep(r, k9), (0, 1, 1))
        t1 = copy(t2)
        rotate_reg(t1)
        t12 = oradd(t2, t1)
        drop(t2)
        drop(t1)
        t32 = shl(copy(t12))
        t10 = copy(t12)
        rotate_reg(t10)
        drop(t12)
        out_r = mask_low4(oradd(t32, t10))
        drop(t32)
        drop(t10)
        return out_r

    def resolve_token(tok: int, need_masks: bool = False) -> tuple[int, int | None, int | None, int | None]:
        tok_rel = mask_low4(add_in_loop(tok, k42, rounds))
        m_dig = broadcast_t2(tok_rel)
        m_var = mask_low4(un(m_dig, (1, 0, 0)))
        t0 = keep(tok_rel, k1)
        drop(tok_rel)

        kd = keep(tok, m_dig)
        drop(m_dig)

        def pick_var(var_r: int, tbl: tuple[int, int, int]) -> tuple[int, int | None]:
            t_u = un(t0, tbl)
            m_raw = broadcast_t0(t_u)
            drop(t_u)
            m_v = keep(m_var, m_raw)
            drop(m_raw)
            kv = keep(var_r, m_v)
            if not need_masks:
                drop(m_v)
                return kv, None
            return kv, m_v

        kx, m_x = pick_var(var_x, (1, 0, 0))
        ky, m_y = pick_var(var_y, (0, 1, 0))
        kz, m_z = pick_var(var_z, (0, 0, 1))
        drop(t0)
        drop(m_var)

        kxy = oradd(kx, ky)
        drop(kx)
        drop(ky)
        kxyz = oradd(kxy, kz)
        drop(kxy)
        drop(kz)
        val = oradd(kd, kxyz)
        drop(kd)
        drop(kxyz)
        return val, m_x, m_y, m_z

    # Read 7-byte frame `(op r1 r2)`:
    op_reg = read_into(skip_before=0)
    r1_reg = read_into(skip_before=1)
    r2_reg = read_into(skip_before=1)
    last = position(laps.lap - 1, "crazy")
    put("input", last)

    v1, m_x1, m_y1, m_z1 = resolve_token(r1_reg, need_masks=True)
    drop(r1_reg)
    v2, _, _, _ = resolve_token(r2_reg, need_masks=False)
    drop(r2_reg)

    # op_rel = (op + 38) mod 81: '+'->0, '-'->2 (t0), '='->18 (t2)
    op_rel = mask_low4(add_in_loop(op_reg, k38, rounds))
    drop(op_reg)
    m_minus = mask_low4(unary_ip(broadcast_t0(op_rel), (0, 1, 1)))
    m_set = broadcast_t2(op_rel)
    drop(op_rel)
    m_ms = oradd(m_minus, m_set)
    m_plus = mask_low4(un(m_ms, (1, 0, 0)))
    drop(m_ms)

    y_plus = mask_low4(add_in_loop(v2, k33, rounds))
    v2_comp = mask_low4(un(v2, (2, 1, 0)))
    y_minus = mask_low4(add_in_loop(v2_comp, k49, rounds))
    drop(v2_comp)

    kp_y = keep(y_plus, m_plus)
    km_y = keep(y_minus, m_minus)
    drop(y_plus)
    drop(y_minus)
    y_pm = oradd(kp_y, km_y)
    drop(kp_y)
    drop(km_y)

    res_pm = mask_low4(add_in_loop(v1, y_pm, rounds))
    drop(v1)
    drop(y_pm)

    m_pm = oradd(m_plus, m_minus)
    drop(m_plus)
    drop(m_minus)
    k_pm = keep(res_pm, m_pm)
    k_set = keep(v2, m_set)
    drop(res_pm)
    drop(v2)
    drop(m_pm)
    res = oradd(k_pm, k_set)
    drop(k_pm)
    drop(k_set)

    # Update env variable if op == '=':
    def update_var(var_reg: int, m_var1: int) -> None:
        wr = keep(m_set, m_var1)
        drop(m_var1)
        keep_old = mask_low4(un(wr, (1, 0, 0)))
        new_part = keep(res, wr)
        old_part = keep(var_reg, keep_old)
        drop(wr)
        drop(keep_old)
        updated = oradd(new_part, old_part)
        drop(new_part)
        drop(old_part)
        copy(updated, var_reg)
        drop(updated)

    update_var(var_x, m_x1)
    update_var(var_y, m_y1)
    update_var(var_z, m_z1)
    drop(m_set)

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
    return LispEnvRepl(image, {"X": var_x, "Y_VAR": var_y, "Z_VAR": var_z, "C2": c2, "M80": m80, "halt": halt_at, "landing": landing})

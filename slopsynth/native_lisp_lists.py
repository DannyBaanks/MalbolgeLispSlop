"""H37: Re-executable fixed19 Lisp list (`cons`, `car`, `cdr`) REPL loop.

Packs up to 4 ASCII-digit elements (4 trits each, trits 0..15) into a single
18-trit `fixed19` register `list_reg`, supporting native list operations in
7-byte frames (halting in-image on `0` or EOF):

    (c x 0)   -> cons(x, list): pushes `x` onto head of `list_reg`, emits `x`
    (a 0 0)   -> car(list): emits head of `list_reg` (`0` if empty)
    (d 0 0)   -> cdr(list): drops head (4-trit right shift), emits new head

Architecture:
1. `(op + 63) mod 81` maps `'c'` (99) -> `0`, `'d'` (100) -> `1`, `'a'` (97) -> `79`,
   yielding orthogonal 4-trit masks `m_cons`, `m_cdr`, `m_car`.
2. `M_LOW12` (trits 0..11 = `2`, trits 12..17 = `1`) is initialized in the
   prologue from three disjoint 4-trit blocks (`80`, `80*3^4`, `80*3^8`).
3. `cons` shifts `mask_low12(list_reg)` left by 4 trits (`shl` x4) and inserts
   `x` into trits 0..3; `cdr` shifts `list_reg` right by 4 trits (`rotate_reg` x4)
   and masks with `M_LOW12`.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._native_eval_add import UNARY
from .cycles import PAIR_GAP, jump_cell, padding, pair_cell, pair_residue
from .native_asm import LAP, STEP, Conflict, Laps, Memory, bootstrap, once, seed as byte_seed
from .native_ir_loop import EOF_WORD, TABLE_LAPS

LOWERING = "fixed19-native-lisp-lists-v1"
_PAD = tuple(padding(i) for i in range(94))

PARAMS = {
    "Y": 82, "W": 114, "U": 115, "V": 45, "C2": 125, "M80": 126, "M12": 124,
    "table": 60, "eof": 51, "halt": 59, "slack": 3, "budget": 2600, "P": 68,
    "far": 80 * STEP,
}


def reference(stdin: bytes) -> bytes:
    """Expected stdout of the H37 cons/car/cdr REPL loop on 7-byte frames."""
    out = bytearray()
    lst = 0
    mod12 = 3**12
    idx = 0
    while idx < len(stdin):
        if stdin[idx] == 0:
            break
        if idx + 7 > len(stdin):
            break
        op = stdin[idx + 1]
        x = stdin[idx + 3] % 81
        if op == ord("c"):
            lst = ((lst % mod12) * 81) + x
            res = x
        elif op == ord("d"):
            lst = lst // 81
            res = lst % 81
        else:
            res = lst % 81
        out.append((res if res != 0 else ord("0")) & 0xFF)
        idx += 7
    return bytes(out)


@dataclass(frozen=True, slots=True)
class LispListsRepl:
    image: bytes
    cells: dict[str, int]
    lowering: str = LOWERING


def build_lisp_lists(rounds: int = 3, params: dict[str, int] | None = None) -> LispListsRepl:
    p = PARAMS if params is None else params
    memory = Memory()
    y, w, u, v, c2, m80, m12 = p["Y"], p["W"], p["U"], p["V"], p["C2"], p["M80"], p["M12"]
    for name, s in (("Y", 0), ("W", 0), ("V", 0), ("U", 2), ("C2", 0), ("M80", 0), ("M12", 0)):
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
    k27 = claim_const(27, "k27")
    k48 = claim_const(48, "k48")
    k63 = claim_const(63, "k63")

    reg_pool = [r for r in range(128, 150) if memory.free(r)]
    list_reg = reg_pool.pop(0)
    tmp_copy = reg_pool.pop(0)
    memory.claim(list_reg, 0, "list_reg")
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

    def mask_low12(r: int) -> int:
        m12_01 = un(m12, (0, 1, 1))
        masked = keep(r, m12_01)
        drop(m12_01)
        copy(masked, r)
        drop(masked)
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

    # Read 7-byte frame `(op x y)`:
    op_reg = read_into(skip_before=0)
    x_raw = read_into(skip_before=1)
    last = position(laps.lap - 1, "crazy")
    ch_sp2 = put("input", last)
    ch_y = put("input", ch_sp2)
    put("input", ch_y)

    x_val = mask_low4(x_raw)

    # op_rel = (op + 63) mod 81: 'c'->0, 'd'->1, 'a'->79
    op_rel = mask_low4(add_in_loop(op_reg, k63, rounds))
    drop(op_reg)
    m_car = broadcast_t3(op_rel)
    m_not_car = mask_low4(un(m_car, (1, 0, 0)))
    m_cdr = keep(broadcast_t0(op_rel), m_not_car)
    drop(op_rel)
    drop(m_not_car)
    m_ca = oradd(m_car, m_cdr)
    m_cons = mask_low4(un(m_ca, (1, 0, 0)))
    drop(m_ca)

    # Compute cons_list = oradd(x_val, shl4(mask_low12(list_reg)))
    lst_shl = mask_low12(copy(list_reg))
    for _ in range(4):
        shl(lst_shl)
    cons_list = oradd(x_val, lst_shl)
    drop(x_val)
    drop(lst_shl)

    # Compute cdr_list = mask_low12(shr4(list_reg))
    cdr_list = copy(list_reg)
    for _ in range(4):
        rotate_reg(cdr_list)
    mask_low12(cdr_list)

    # Mux new list_reg: cons->cons_list, cdr->cdr_list, car->list_reg
    # Expand 4-trit masks to 16 trits via shift-OR? Or simply use 18-trit broadcast!
    # Wait: keep() works tritwise! Replicating m_cons/m_cdr/m_car to trits 0..15:
    def expand4_to16(m4: int) -> int:
        m8 = oradd(copy(m4), shl(shl(shl(shl(copy(m4))))))
        m8_hi = copy(m8)
        for _ in range(8):
            shl(m8_hi)
        m16 = oradd(m8, m8_hi)
        drop(m8)
        drop(m8_hi)
        return m16

    m16_cons = expand4_to16(m_cons)
    m16_cdr = expand4_to16(m_cdr)
    m16_car = expand4_to16(m_car)
    drop(m_cons)
    drop(m_cdr)
    drop(m_car)

    k_cons = keep(cons_list, m16_cons)
    k_cdr = keep(cdr_list, m16_cdr)
    k_car = keep(list_reg, m16_car)
    drop(cons_list)
    drop(cdr_list)
    drop(m16_cons)
    drop(m16_cdr)
    drop(m16_car)

    k_cc = oradd(k_cons, k_cdr)
    drop(k_cons)
    drop(k_cdr)
    new_list = oradd(k_cc, k_car)
    drop(k_cc)
    drop(k_car)
    copy(new_list, list_reg)
    drop(new_list)

    # Head of updated list_reg (0 -> '0' = 48):
    head = mask_low4(copy(list_reg))
    nz = mask_low4(un(head, (0, 1, 1)))
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
    m_empty = broadcast_t0(eq0)
    drop(eq0)
    m_nonempty = mask_low4(un(m_empty, (1, 0, 0)))

    res = oradd(keep(head, m_nonempty), keep(k48, m_empty))
    drop(head)
    drop(m_empty)
    drop(m_nonempty)
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
    s1, c125, c121, temp, temp2, zero_p, s26, s80, s80_4, s80_8 = (
        scratch(s) for s in (26, 125, 121, 0, 0, 0, 26, 80, 80, 80)
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
    code.at(s80_4, "rotate", 14)
    code.at(m12, "crazy")
    code.at(s80_8, "rotate", 10)
    code.at(m12, "crazy")
    code.at(zero_p, "rotate")
    code.at(temp2, "crazy")
    code.at(m12, "crazy")

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
    return LispListsRepl(image, {"LIST": list_reg, "C2": c2, "M80": m80, "M12": m12, "halt": halt_at, "landing": landing})

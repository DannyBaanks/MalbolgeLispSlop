"""Classic Malbolge (3^10) trace-to-CFG lifter and Unshackled fast20 (3^19) lowering.

Lifts a Classic Malbolge program's dynamic execution trace into a Control Flow
Graph (nodes, edges, Tarjan SCCs, and in->out dataflow) and lowers supported
classes into native fixed-3^19 (`fast20` / `bolge19`) images:

* `STRAIGHT_LINE_HALT`: no input-driven loop; halts cleanly -> `Once` + 6-cell pool
* `ECHO_LOOP`: cyclic SCC with A-preserving `in -> out` pairs and 0 `opr`/`rot`
  -> `slopsynth.native_cat.build_cat()` (`fixed19-native-cat-v1`)
* `TAGGED_ECHO_LOOP`: H15 tagged-record loop -> `slopsynth.native_ir_unified.lower()`
* `UNSUPPORTED_CFG`: complex stateful/ALU loops -> explicitly reported
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .cycles import padding
from .ir import BasicBlock, BranchZero, Function, Halt, Jump, Module, ModuleCase, ReadA, WriteA
from .native_asm import FAR, Memory, bootstrap, seed as byte_seed
from .native_cat import build_cat

CLASSIC_END = 3 ** 10
FAST20_END = 3 ** 19
FAST20_THIRD = FAST20_END // 3
VALID_OPCODES = (4, 5, 23, 39, 40, 62, 68, 81)
OPCODE_NAMES = {4: "jmp", 5: "out", 23: "in", 39: "rot", 40: "movd", 62: "opr", 68: "nop", 81: "hlt"}
XLAT94 = "5z]&gqtyfr$(we4{WP)H-Zn,[%\\3dL+Q;>U!pJS72FhOA1CB6v^=I_0/8|jsb9m<.TVac`uY*MK'X~xDl}REokN:#?G\"i@"
CRZ = ((1, 0, 0), (1, 0, 2), (2, 2, 1))


def crazy(a: int, d: int, trits: int) -> int:
    r, k = 0, 1
    for _ in range(trits):
        r += k * CRZ[d % 3][a % 3]
        a //= 3
        d //= 3
        k *= 3
    return r


def mrot19(x: int) -> int:
    b = x % FAST20_THIRD
    return b // 3 + (b % 3) * (FAST20_THIRD // 3) + (x - b)


class ClassicLoadError(ValueError):
    pass


@dataclass
class ClassicRun:
    stdout: bytes
    status: str
    steps: int
    trace: list = field(default_factory=list)
    inputs_used: int = 0
    in_executed: int = 0


class ClassicVM:
    """Olmstead 1998 Classic Malbolge (3^10) interpreter."""

    def __init__(self, source: bytes, eof: int = CLASSIC_END - 1):
        mem = [0] * CLASSIC_END
        i = 0
        for ch in source:
            if ch in b" \t\r\n\f\v":
                continue
            if not 33 <= ch <= 126 or (ch + i) % 94 not in VALID_OPCODES:
                raise ClassicLoadError(f"invalid character {ch!r} at cell {i}")
            if i >= CLASSIC_END:
                raise ClassicLoadError("program longer than 3^10")
            mem[i] = ch
            i += 1
        if i < 2:
            raise ClassicLoadError("program shorter than two cells")
        self.length = i
        for j in range(i, CLASSIC_END):
            mem[j] = crazy(mem[j - 1], mem[j - 2], 10)
        self.mem, self.eof = mem, eof
        self.a = self.c = self.d = 0

    def step(self, inp: list[int], out: bytearray) -> Optional[str]:
        m, c = self.mem, self.c
        if not 33 <= m[c] <= 126:
            return "INVALID_CELL"
        op = (m[c] + c) % 94
        if op == 4:
            self.c = c = m[self.d]
        elif op == 5:
            out.append(self.a % 256)
        elif op == 23:
            self.a = inp.pop(0) if inp else self.eof
        elif op == 39:
            v = m[self.d]
            self.a = m[self.d] = v // 3 + (v % 3) * 3 ** 9
        elif op == 40:
            self.d = m[self.d]
        elif op == 62:
            self.a = m[self.d] = crazy(self.a, m[self.d], 10)
        elif op == 81:
            return "HALT"
        if 33 <= m[c] <= 126:
            m[c] = ord(XLAT94[m[c] - 33])
        self.c = (c + 1) % CLASSIC_END
        self.d = (self.d + 1) % CLASSIC_END
        return None

    def run(self, inp: bytes = b"", max_steps: int = 500_000, keep_trace: bool = True) -> ClassicRun:
        queue, out, trace, ins = list(inp), bytearray(), [], 0
        for n in range(max_steps):
            c = self.c
            op = (self.mem[c] + c) % 94 if 33 <= self.mem[c] <= 126 else None
            ins += op == 23
            status = self.step(queue, out)
            if keep_trace:
                trace.append((n, c, op, self.a, self.d))
            if status:
                return ClassicRun(bytes(out), status, n + 1, trace, len(inp) - len(queue), ins)
        return ClassicRun(bytes(out), "MAX_STEPS", max_steps, trace, len(inp) - len(queue), ins)


@dataclass
class LiftedCFG:
    nodes: Dict[int, Set[int]]
    edges: Dict[int, Set[int]]
    sccs: List[List[int]]
    loop_ops: Dict[str, int]
    kind: str
    reason: str
    stdout: bytes = b""
    in_executed: int = 0
    steps: int = 0
    status: str = ""
    details: dict = field(default_factory=dict)


def _tarjan_sccs(nodes: Set[int], edges: Dict[int, Set[int]]) -> List[List[int]]:
    index = 0
    indices: Dict[int, int] = {}
    lowlink: Dict[int, int] = {}
    stack: List[int] = []
    on_stack: Set[int] = set()
    result: List[List[int]] = []

    for start in sorted(nodes):
        if start in indices:
            continue
        call_stack: List[Tuple[int, List[int], int]] = [(start, sorted(edges.get(start, ())), 0)]
        indices[start] = lowlink[start] = index
        index += 1
        stack.append(start)
        on_stack.add(start)

        while call_stack:
            v, nbrs, idx = call_stack[-1]
            if idx < len(nbrs):
                call_stack[-1] = (v, nbrs, idx + 1)
                w = nbrs[idx]
                if w not in indices:
                    indices[w] = lowlink[w] = index
                    index += 1
                    stack.append(w)
                    on_stack.add(w)
                    call_stack.append((w, sorted(edges.get(w, ())), 0))
                elif w in on_stack and indices[w] < lowlink[v]:
                    lowlink[v] = indices[w]
            else:
                call_stack.pop()
                if call_stack:
                    parent = call_stack[-1][0]
                    if lowlink[v] < lowlink[parent]:
                        lowlink[parent] = lowlink[v]
                if lowlink[v] == indices[v]:
                    scc = []
                    while True:
                        w = stack.pop()
                        on_stack.remove(w)
                        scc.append(w)
                        if w == v:
                            break
                    if len(scc) > 1 or v in edges.get(v, ()):
                        result.append(sorted(scc))
    return result


def lift_classic_cfg(source: bytes, probe_input: bytes = b"AB", max_steps: int = 500_000) -> LiftedCFG:
    """Run ClassicVM on `source` and lift its dynamic CFG structurally."""
    vm = ClassicVM(source)
    run = vm.run(probe_input, max_steps=max_steps, keep_trace=True)
    nodes: Dict[int, Set[int]] = defaultdict(set)
    edges: Dict[int, Set[int]] = defaultdict(set)
    prev_c: Optional[int] = None
    for _, c, op, _, _ in run.trace:
        if op is not None:
            nodes[c].add(op)
        if prev_c is not None:
            edges[prev_c].add(c)
        prev_c = c
    sccs = _tarjan_sccs(set(nodes.keys()), edges)

    scc_cells = {c for comp in sccs for c in comp}
    loop_ops: Dict[str, int] = defaultdict(int)
    for _, c, op, _, _ in run.trace:
        if c in scc_cells and op is not None:
            loop_ops[OPCODE_NAMES.get(op, str(op))] += 1

    if run.status == "HALT" and run.in_executed == 0:
        return LiftedCFG(
            nodes=dict(nodes), edges=dict(edges), sccs=sccs, loop_ops=dict(loop_ops),
            kind="STRAIGHT_LINE_HALT",
            reason=f"halts in {run.steps} steps without executing `in`",
            stdout=run.stdout, in_executed=run.in_executed, steps=run.steps, status=run.status,
        )

    if sccs:
        active_scc = set(sccs[-1])
        tail = [(c, op, a, d) for _, c, op, a, d in run.trace[-4000:] if c in active_scc and op is not None]
        non_nop = [(c, OPCODE_NAMES.get(op, str(op)), a, d) for c, op, a, d in tail if op != 68]
        op_names = [name for _, name, _, _ in non_nop]

        if op_names.count("in") >= 2 and op_names.count("out") >= 2 and (op_names.count("opr") + op_names.count("rot")) == 0:
            pairs_match = True
            last_in_a = None
            checked_pairs = 0
            for _, name, a, _ in non_nop:
                if name == "in":
                    last_in_a = a
                elif name == "out" and last_in_a is not None:
                    if a != last_in_a:
                        pairs_match = False
                        break
                    checked_pairs += 1
                    last_in_a = None
            if pairs_match and checked_pairs >= 2:
                return LiftedCFG(
                    nodes=dict(nodes), edges=dict(edges), sccs=sccs, loop_ops=dict(loop_ops),
                    kind="ECHO_LOOP",
                    reason=f"loop SCC ({len(active_scc)} cells) has {checked_pairs} direct in->out A-preserving pairs and 0 opr/rot",
                    stdout=run.stdout, in_executed=run.in_executed, steps=run.steps, status=run.status,
                    details={"scc_size": len(active_scc), "checked_pairs": checked_pairs},
                )

    if run.in_executed > 0:
        run0 = ClassicVM(source).run(b"", max_steps=max_steps, keep_trace=False)
        if run0.status == "HALT":
            return LiftedCFG(
                nodes=dict(nodes), edges=dict(edges), sccs=sccs, loop_ops=dict(loop_ops),
                kind="STRAIGHT_LINE_HALT",
                reason=f"halts on empty stdin in {run0.steps} steps (reads EOF {run0.in_executed}x)",
                stdout=run0.stdout, in_executed=run0.in_executed, steps=run0.steps, status=run0.status,
            )

    return LiftedCFG(
        nodes=dict(nodes), edges=dict(edges), sccs=sccs, loop_ops=dict(loop_ops),
        kind="UNSUPPORTED_CFG",
        reason=f"status={run.status}, sccs={len(sccs)}, loop_ops={dict(loop_ops)}",
        stdout=run.stdout, in_executed=run.in_executed, steps=run.steps, status=run.status,
        details={"scc_sizes": [len(s) for s in sccs]},
    )


def retarget_bytes(
    data: bytes,
    pool_at: Tuple[int, ...] = (50, 60, 70, 80, 90, 100),
    pool_seed: Tuple[int, ...] = (3, 29, 55, 81, 107, 124),
    depth: int = 5,
    max_states: int = 250_000,
) -> Tuple[bytes, list[dict]]:
    """Synthesize a native fast20 (3^19) image that prints `data` and halts."""
    memory = Memory()
    active_at = list(pool_at)
    vals = list(pool_seed)
    for at, s in zip(active_at, vals):
        memory.claim(at, s, "pool")
    reserve = [(46, 37), (54, 73), (64, 109), (74, 19), (84, 61), (94, 97), (104, 43), (110, 83), (114, 113), (118, 13)]
    code = bootstrap(memory)
    s, r = byte_seed(FAR)
    a = s
    for _ in range(r):
        a = mrot19(a)
    plan = []

    def _bfs(target_b: int):
        actions = [(kind, i) for i in range(len(active_at)) for kind in ("rotate", "crazy")]
        start = (a, tuple(vals))
        parent = {start: None}
        frontier = [start]
        if a % 256 == target_b:
            return [], start
        level = 0
        while level < depth and frontier:
            nxt = []
            for st in frontier:
                aa, vv = st
                for kind, i in actions:
                    v = list(vv)
                    x = v[i] = mrot19(v[i]) if kind == "rotate" else crazy(aa, v[i], 19)
                    ns = (x, tuple(v))
                    if ns in parent:
                        continue
                    parent[ns] = (st, (kind, i))
                    if x % 256 == target_b:
                        seq, cur = [], ns
                        while parent[cur] is not None:
                            cur, act = parent[cur]
                            seq.append(act)
                        seq.reverse()
                        return seq, ns
                    if len(parent) < max_states:
                        nxt.append(ns)
            frontier, level = nxt, level + 1
        return None

    for b in data:
        res = _bfs(b)
        while res is None and reserve:
            r_at, r_seed = reserve.pop(0)
            if memory.free(r_at):
                memory.claim(r_at, r_seed, "pool")
                active_at.append(r_at)
                vals.append(r_seed)
                res = _bfs(b)
        if res is None:
            raise RuntimeError(f"no sequence of depth <= {depth} for byte {b}")
        seq, found = res
        a, vals = found[0], list(found[1])
        for kind, i in seq:
            code.at(active_at[i], kind)
        code.emit("output")
        plan.append({"byte": b, "ops": [f"{k}@{active_at[i]}" for k, i in seq]})
    code.emit("halt")
    end = code.c
    cells: list[Optional[int]] = [None] * end
    for address, (value, _) in memory.cells.items():
        if address >= end:
            raise RuntimeError("data beyond code end")
        cells[address] = value
    image = bytes((padding(i) if i >= FAR else 0) if v is None else v for i, v in enumerate(cells))
    return image, plan


def build_tagged_echo_ir() -> Module:
    """Construct the H15 tagged echo-loop IR Module for `native_ir_unified.lower()`."""
    return Module(
        name="c2u_tagged_echo",
        entry_function="main",
        functions=(
            Function(
                name="main",
                parameters=(),
                entry_block="top",
                blocks=(
                    BasicBlock(name="top", operations=(ReadA(), BranchZero("A", "zero", "echo"))),
                    BasicBlock(name="zero", operations=(Halt(),)),
                    BasicBlock(name="echo", operations=(ReadA(), WriteA(), Jump("top"))),
                ),
            ),
        ),
        cases=(ModuleCase(stdin=b"\x01A\x00", stdout=b"A"),),
    )


def lower_lifted_cfg(cfg: LiftedCFG) -> Optional[dict]:
    """Lower a lifted CFG into a native fixed-3^19 (`fast20` / `bolge19`) image."""
    if cfg.kind == "STRAIGHT_LINE_HALT":
        img, plan = retarget_bytes(cfg.stdout)
        return {"lowering": "c2u-once-retarget-v1", "image": img, "ops_per_byte": [len(p["ops"]) for p in plan]}
    if cfg.kind == "ECHO_LOOP":
        cat = build_cat()
        return {"lowering": cat.lowering, "image": cat.image, "steps_per_byte": cat.steps_per_byte}
    if cfg.kind == "TAGGED_ECHO_LOOP":
        from .native_ir_unified import lower as unified_lower
        root = Path(__file__).resolve().parent.parent
        cwd = os.getcwd()
        try:
            os.chdir(root)
            res = unified_lower(build_tagged_echo_ir())
        finally:
            os.chdir(cwd)
        return {"lowering": res.lowering, "image": res.image, "kind": res.kind}
    return None

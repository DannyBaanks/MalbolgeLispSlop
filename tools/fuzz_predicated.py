#!/usr/bin/env python3
"""Differential fuzzer for the predicated compiler: random IR programs, the host
reference against bolge19.

Each program reads up to three bytes, runs a few blocks of arithmetic,
comparisons, memory and forward or (bounded) backward branches, and ends by
printing every memory cell and variable, so a wrong value anywhere is visible.
Programs the compiler rejects with AssemblyError are counted, not failures.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import random
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from slopsynth.assemble import AssemblyError
from slopsynth.ir import (
    Add, And, BasicBlock, BranchZero, Eq, Function, Halt, Jump, Load, Lt, Module, ModuleCase, Mul, Or, ReadA,
    Store, Sub, WriteA, WriteDecimal,
)
from slopsynth.predicated import lower_predicated, reference
from slopsynth.profile import load_profile

VARS = ("a", "b", "c", "d")
CELLS = (0, 1, 2)


def program(rng: random.Random):
    """A random module with its width, unrolling bound and number of input bytes."""
    width = rng.choice((3, 4, 5, 7))
    reads = rng.randrange(1, 4)
    names = [f"b{i}" for i in range(rng.randrange(2, 6))]
    loops = rng.random() < 0.3

    def operand():
        return rng.randrange(3**width + 5) if rng.random() < 0.35 else rng.choice(VARS)

    def address():
        return rng.choice(CELLS + ("f",))  # f is always 0, 1 or 2

    def body():
        ops = []
        for _ in range(rng.randrange(5)):
            kind, dst = rng.random(), rng.choice(VARS)
            if kind < 0.20:
                ops.append(Add(dst, operand(), operand()))
            elif kind < 0.38:
                ops.append(Sub(dst, operand(), operand()))
            elif kind < 0.48:
                ops.append(Mul(dst, operand(), operand()))
            elif kind < 0.58:
                ops.append(Lt(dst, operand(), operand()))
            elif kind < 0.66:
                ops.append(Eq(dst, operand(), operand()))
            elif kind < 0.72:
                ops.append(rng.choice((And, Or))(dst, operand(), operand()))
            elif kind < 0.80:
                ops.append(Store(address(), operand()))
            elif kind < 0.88:
                ops.append(Load(dst, address()))
            elif kind < 0.94:
                ops.append(WriteDecimal(rng.choice(VARS)))
            else:
                ops.append(WriteA(rng.choice(VARS)))
            if isinstance(ops[-1], (Lt, Eq, And, Or)) and rng.random() < 0.6:
                ops.append(Add("f", dst, rng.randrange(2)))
        return ops

    blocks = []
    for i, name in enumerate(names):
        ops = []
        if i == 0:
            ops += [ReadA(v) for v in VARS[:reads]]
            ops += [Add(v, rng.randrange(5), 0) for v in VARS[reads:]]
            ops.append(Add("f", 0, 0))
        ops += body()
        later = names[i + 1:]
        if not later:
            for cell in CELLS:
                ops += [Load("a", cell), WriteDecimal("a"), Add("a", 32, 0), WriteA("a")]
            for var in VARS[1:] + ("f",):
                ops += [WriteDecimal(var), Add("a", 32, 0), WriteA("a")]
            ops.append(Halt())
        elif rng.random() < 0.6:
            zero, nonzero = rng.choice(later), rng.choice(later)
            if loops and i > 0 and rng.random() < 0.5:
                nonzero = rng.choice(names[1:i + 1])
            ops.append(BranchZero(operand(), zero, nonzero))
        else:
            ops.append(Jump(rng.choice(later)))
        blocks.append(BasicBlock(name, tuple(ops)))
    bound = rng.randrange(1, 4) if loops else 0
    function = Function("main", (), names[0], tuple(blocks))
    draft = Module("fuzz", "main", (function,), (ModuleCase(b"", b""),))
    module = Module("fuzz", "main", (function,), (ModuleCase(b"", reference(draft, b"", width, bound)),))
    return module, width, bound, reads


def fuzz(seeds, engine: Path, inputs_per_program: int = 8, report=print) -> dict[str, int]:
    profile = load_profile(ROOT / "profiles/fixed19.json")
    stats = {"ok": 0, "rejected": 0, "mismatch": 0}
    with tempfile.TemporaryDirectory() as tmp:
        image = Path(tmp) / "fuzz.mb"
        for seed in seeds:
            rng = random.Random(seed)
            module, width, bound, reads = program(rng)
            try:
                image.write_bytes(lower_predicated(module, profile, width=width, bound=bound).image)
            except AssemblyError as error:
                stats["rejected"] += 1
                report(f"seed {seed}: rejected ({error})")
                continue
            for _ in range(inputs_per_program):
                stdin = bytes(rng.choice((rng.randrange(256), rng.randrange(48, 58), 0, 1, 2))
                              for _ in range(rng.randrange(reads + 1)))
                want = reference(module, stdin, width, bound)
                got = subprocess.run([str(engine), str(image), "--loader", "canonical", "--max-steps", "400000000"],
                                     input=stdin, capture_output=True, timeout=300).stdout
                if got != want:
                    stats["mismatch"] += 1
                    report(f"seed {seed}: MISMATCH stdin={stdin!r} width={width} bound={bound} want={want!r} got={got!r}")
                    break
            else:
                stats["ok"] += 1
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=0, help="first seed")
    parser.add_argument("--count", type=int, default=50, help="number of programs")
    parser.add_argument("--engine", type=Path, default=ROOT / "build/bolge19")
    args = parser.parse_args()
    if not args.engine.is_file():
        print(f"missing engine {args.engine}; run ./tools/build.sh", file=sys.stderr)
        return 2
    stats = fuzz(range(args.seed, args.seed + args.count), args.engine)
    print(stats)
    return 1 if stats["mismatch"] else 0


if __name__ == "__main__":
    sys.exit(main())

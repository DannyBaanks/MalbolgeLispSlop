#!/usr/bin/env python3
"""Seal H10-H12: compile each IR guest, run fixed batteries on upstream fast20.c and bolge19."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import platform
import random
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from guest_ir.lisp import arith, arith_multi, nested
from slopsynth.predicated import LOWERING, lower_predicated
from slopsynth.profile import load_profile
from tools.battery import battery
from tools.verify_h9_fast20 import UPSTREAM_REVISION, UPSTREAM_SHA256, digest, write_json


def mutate(rng, pool, n, limit):
    out = []
    for _ in range(n):
        c = bytearray(rng.choice(pool))
        c[rng.randrange(len(c))] = rng.randrange(256)
        out.append(bytes(c)[:limit])
    return out


def h10_inputs():
    rng = random.Random(5)
    valid = [f"({o} {a} {b}){e}".encode() for o in "+-*" for a in range(10) for b in range(10) for e in ("", "\n", "\r\n")]
    bad = [b"", b"(/ 1 2)", b"(+ 1 2", b"(+ : 2)", b"(+ / 2)", b"(+ 1 2)\n\n", b"(+ 1 2)\r", b"\xff" * 9,
           b"(% 1 2)", b"(, 1 2)"]
    bad += mutate(rng, valid, 150, 9)
    bad += [bytes(rng.randrange(256) for _ in range(rng.randrange(1, 10))) for _ in range(50)]
    return valid + bad


def h11_inputs():
    rng = random.Random(11)
    ends = ["", "\n", "\r\n"]
    valid = [f"({o} {a} {b})".encode() for o in "+-*" for a in range(10) for b in range(10)]
    edge = [0, 1, 9, 10, 11, 42, 50, 89, 98, 99]
    valid += [f"({o} {a} {b})".encode() for o in "+-*" for a in edge for b in edge]
    valid += [f"({rng.choice('+-*')} {rng.randrange(100)} {rng.randrange(100)}){rng.choice(ends)}".encode()
              for _ in range(300)]
    bad = [b"", b"(+ 123 4)", b"(+ 1 234)", b"(+  1 2)", b"(+ 1 2) ", b"(/ 1 2)", b"(+ 1 2)\r",
           b"(+ 1 2)\n\n", b"(+1 2)", b"(+ 1 2", b"+ 1 2)", b"(+ -1 2)", b"\xff" * 12]
    bad += mutate(rng, valid, 200, 12)
    return [x for x in valid + bad if len(x) <= 12]


def h12_inputs():
    rng = random.Random(12)
    leaf = lambda: str(rng.randrange(10))
    sub = lambda: f"({rng.choice('+-*')} {leaf()} {leaf()})"
    node = lambda: rng.choice([leaf, sub])()
    valid = [str(d).encode() for d in range(10)]
    valid += [f"({o} {a} {b})".encode() for o in "+-*" for a in range(10) for b in range(10)]
    valid += [f"({rng.choice('+-*')} {node()} {node()}){rng.choice(['', chr(10), chr(13) + chr(10)])}".encode()
              for _ in range(400)]
    valid += [f"({rng.choice('+-*')} {sub()} {sub()})".encode() for _ in range(100)]
    bad = [b"", b"(+ 1 (+ 2 (+ 3 4)))", b"(+ 12 3)", b"(+ (1) 2)", b"(+ 1 2) ", b"(/ 1 2)", b"(+ 1 2)\r",
           b"((+ 1 2) 3)", b"(+ 1 2 3)", b"\xff" * 22]
    bad += mutate(rng, valid, 250, 22)
    return [x for x in valid + bad if len(x) <= 22]


GATES = {
    "h10": (arith.build_arith_module, 7, 0, h10_inputs, 9,
            "(op a b), op in + - *, single digits; signed result"),
    "h11": (arith_multi.build_arith_multi_module, arith_multi.WIDTH, arith_multi.BOUND, h11_inputs, 12,
            "(op a b) with 1-2 digit operands; one-byte-per-iteration loop unrolled to bound 11"),
    "h12": (nested.build_nested_module, nested.WIDTH, 0, h12_inputs, nested.MAX_BYTES,
            "nested (op e1 e2), depth <= 2, single-digit leaves; recursive descent over Load/Store memory"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gates", nargs="*", default=list(GATES))
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    if digest((ROOT / "evidence/h9_fast20_crosscheck_v1/upstream/fast20.c").read_bytes()) != UPSTREAM_SHA256:
        print("pinned fast20.c changed", file=sys.stderr)
        return 2
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "evidence/h10_h12_predicated_v1/runs" / f"{stamp}-{uuid.uuid4().hex[:8]}"
    out.mkdir(parents=True)
    fast20 = out / "fast20"
    subprocess.run(["gcc", "-O2", "-w", "-o", str(fast20),
                    str(ROOT / "evidence/h9_fast20_crosscheck_v1/upstream/fast20.c")], check=True)
    profile = load_profile(ROOT / "profiles/fixed19.json")
    summary = {"lowering": LOWERING, "upstream_fast20": {"revision": UPSTREAM_REVISION, "sha256": UPSTREAM_SHA256},
               "host": {"python": platform.python_version(), "platform": platform.platform()}, "gates": {}}
    status = "PASS"
    for gate in args.gates:
        build, width, bound, inputs_of, max_bytes, contract = GATES[gate]
        module = build()
        started = time.time()
        built = lower_predicated(module, profile, width=width, bound=bound)
        compile_s = round(time.time() - started, 1)
        image = out / f"{gate}.mb"
        image.write_bytes(built.image)
        inputs = inputs_of()
        rows = battery(image, module, inputs, width, bound, fast20, ROOT / "build/bolge19", args.jobs)
        with gzip.open(out / f"{gate}.mb.gz", "wb", compresslevel=9) as stream:
            stream.write(built.image)
        image.unlink()
        with (out / f"{gate}-cases.jsonl").open("x", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps(row, sort_keys=True) + "\n")
        passed = sum(r["pass"] for r in rows)
        summary["gates"][gate] = {
            "contract": contract, "width": width, "bound": bound, "max_input_bytes": max_bytes,
            "cells": built.cells, "ir_nodes": built.nodes, "conditional_outputs": len(built.landings),
            "image_sha256": hashlib.sha256(built.image).hexdigest(), "compile_seconds": compile_s,
            "cases": len(rows), "pass": passed,
        }
        if passed != len(rows):
            status = "FAIL"
        print(f"{gate}: {built.cells} cells, {passed}/{len(rows)} on fast20 and bolge19", flush=True)
    fast20.unlink()
    summary["status"] = status
    summary["not_demonstrated"] = [
        "Native Malbolge loops: loops are unrolled to the declared bound.",
        "Inputs longer than the gate's max_input_bytes, or stdin left open (gates load EOF as a control word).",
        "Depth above 2, multi-digit leaves under nesting, division, general Lisp evaluation.",
    ]
    write_json(out / "report.json", summary)
    (out / "SHA256SUMS.txt").write_text(
        "".join(f"{digest(p.read_bytes())}  {p.name}\n" for p in sorted(out.iterdir())), encoding="utf-8")
    print(f"{status}  evidence: {out.relative_to(ROOT)}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

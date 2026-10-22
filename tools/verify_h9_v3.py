#!/usr/bin/env python3
"""Seal an H9 v3 campaign: IR-lowered ternary adder on upstream fast20.c and bolge19."""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from guest_ir.lisp.evaluator import build_eval_add_module
from slopsynth.assemble import AssemblyError
from slopsynth.eval_add_v3 import LOWERING, lower_eval_add_v3, reference
from slopsynth.ir import Add, BasicBlock, ModuleCase, Sub
from slopsynth.profile import load_profile
from tools.verify_h9_fast20 import UPSTREAM_REVISION, UPSTREAM_SHA256, cases, digest, run, write_json

VARIANTS = {
    "a_plus_b": [Add("sum", "op1", "op2"), Sub("result", "sum", 96)],
    "a_plus_a": [Add("s", "op1", "op1"), Sub("result", "s", 96)],
    "b_only": [Sub("result", "op2", 48)],
    "digits_then_add": [Sub("x", "op1", 48), Sub("y", "op2", 48), Add("result", "x", "y")],
    "a_plus_b_plus_1": [Add("s", "op1", "op2"), Sub("t", "s", 96), Add("result", "t", 1)],
}
REJECTED = {
    "negative_difference": [Add("s", "op1", "op2"), Sub("result", "s", 97)],
    "decimal_out_of_range": [Add("s", "op1", "op2"), Sub("result", "s", 90)],
    "name_minus_name": [Add("s", "op2", 57), Sub("result", "s", "op1")],
}


def variant(body):
    module = build_eval_add_module()
    function = module.functions[0]
    ops = function.blocks[0].operations
    block = BasicBlock("main", tuple(ops[:7]) + tuple(body) + tuple(ops[-2:]))
    return replace(
        module,
        functions=(replace(function, blocks=(block,)),),
        cases=(ModuleCase(stdin=b"x", stdout=b"", status="HALT"),),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "evidence/h9_eval_add_v3/runs")
    parser.add_argument("--fast20-src", type=Path, default=ROOT / "evidence/h9_fast20_crosscheck_v1/upstream/fast20.c")
    parser.add_argument("--engine", type=Path, default=ROOT / "build/bolge19")
    parser.add_argument("--cc", default="gcc")
    args = parser.parse_args()

    if digest(args.fast20_src.read_bytes()) != UPSTREAM_SHA256:
        print("fast20.c is not the pinned upstream file", file=sys.stderr)
        return 2
    if not args.engine.is_file():
        print(f"missing engine {args.engine}; run ./tools/build.sh", file=sys.stderr)
        return 2
    profile = load_profile(ROOT / "profiles/fixed19.json")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.output_root / f"{stamp}-{uuid.uuid4().hex[:8]}"
    out.mkdir(parents=True)
    fast20 = out / "fast20"
    subprocess.run([args.cc, "-O2", "-w", "-o", str(fast20), str(args.fast20_src)], check=True)

    def vms(image_path, stdin):
        upstream = run([str(fast20), str(image_path)], stdin)
        ours = run([str(args.engine), str(image_path), "--loader", "canonical", "--max-steps", "20000000"], stdin)
        return upstream, ours

    summary = {"lowering": LOWERING, "upstream_fast20": {"revision": UPSTREAM_REVISION, "sha256": UPSTREAM_SHA256},
               "host": {"python": platform.python_version(), "platform": platform.platform()}, "variants": {}, "rejected": {}}
    records = []
    all_pass = True
    for name, body in VARIANTS.items():
        module = build_eval_add_module() if name == "a_plus_b" else variant(body)
        built = lower_eval_add_v3(module, profile)
        image_path = out / f"{name}.mb"
        image_path.write_bytes(built.image)
        battery = cases() if name == "a_plus_b" else [
            ("valid", f"(+ {a} {b})".encode()) for a in range(10) for b in range(10)
        ] + [("invalid_fixed", x) for x in (b"(+ 4 x)", b"(+ 1 2", b"")]
        passed = {"fast20": 0, "bolge19": 0}
        for kind, stdin in battery:
            want = reference(module, stdin)
            upstream, ours = vms(image_path, stdin)
            ok_f = upstream["stdout_hex"] == want.hex() and not upstream["timeout"]
            ok_b = ours["stdout_hex"] == want.hex() and not ours["timeout"]
            passed["fast20"] += ok_f
            passed["bolge19"] += ok_b
            all_pass &= ok_f and ok_b
            records.append({"variant": name, "kind": kind, "stdin_hex": stdin.hex(), "expected_hex": want.hex(),
                            "fast20": upstream, "bolge19": ours})
        summary["variants"][name] = {
            "ir_body": [repr(op) for op in body],
            "cells": built.cells,
            "image_sha256": hashlib.sha256(built.image).hexdigest(),
            "steps": [repr(step) for step in built.steps],
            "cases": len(battery),
            **passed,
        }
    for name, body in REJECTED.items():
        try:
            lower_eval_add_v3(variant(body), profile)
            summary["rejected"][name] = "ACCEPTED (unexpected)"
            all_pass = False
        except AssemblyError as error:
            summary["rejected"][name] = str(error)
    summary["status"] = "PASS" if all_pass else "FAIL"
    summary["not_demonstrated"] = [
        "Frames other than (+ a b) with single digits; inputs longer than nine bytes or open streams.",
        "Subtraction of a named value, multiplication, nesting, or general Lisp evaluation.",
        "Loops: the circuit is acyclic and executes each gate once.",
    ]
    with (out / "cases.jsonl").open("x", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
    write_json(out / "report.json", summary)
    fast20.unlink()
    sums = "".join(f"{digest(p.read_bytes())}  {p.name}\n" for p in sorted(out.iterdir()))
    (out / "SHA256SUMS.txt").write_text(sums, encoding="utf-8")
    for name, v in summary["variants"].items():
        print(f"{name:16s} {v['cells']:8d} cells  fast20 {v['fast20']}/{v['cases']}  bolge19 {v['bolge19']}/{v['cases']}")
    for name, reason in summary["rejected"].items():
        print(f"rejected {name}: {reason}")
    print(f"{summary['status']}  evidence: {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())

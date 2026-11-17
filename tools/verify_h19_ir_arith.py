#!/usr/bin/env python3
"""Seal H19: the arithmetic loop lowered from an IR module, on upstream
fast20.c, bolge19 and the Python model, for every count the compiler supports.

Each count is compiled through the IR path (parse module_source(n) -> check ->
lower); the emitted image must be byte-identical to the sealed H18 image. The
model runs with max_address = len(image) - 1. Refused modules must raise
AssemblyError; image mutants must differ on both VMs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from slopsynth.assemble import AssemblyError
from slopsynth.lang import parse_placed
from slopsynth.model import RunStatus, run_model
from slopsynth.native_arith_loop import MAX_COUNT, build_arith_loop, reference
from slopsynth.native_asm import seed
from slopsynth.native_count_in import dispatch_values
from slopsynth.native_ir_arith import LOWERING, lower, module_source
from slopsynth.profile import load_profile
from tools.verify_h9_fast20 import UPSTREAM_REVISION, UPSTREAM_SHA256, digest, write_json

TIMEOUT_S = 60


def run_bolge19(engine: Path, image: Path) -> tuple[bytes, int | None]:
    try:
        done = subprocess.run([str(engine), str(image), "--loader", "raw", "--max-steps", "1000000"],
                              stdin=subprocess.DEVNULL, capture_output=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return b"", None
    halt = re.search(rb"HALT steps=(\d+)", done.stderr)
    return done.stdout, int(halt.group(1)) if halt and done.returncode == 0 else None


def run_fast20(fast20: Path, image: Path) -> tuple[bytes, bool]:
    try:
        done = subprocess.run([str(fast20), str(image)], stdin=subprocess.DEVNULL, capture_output=True, timeout=10)
    except subprocess.TimeoutExpired:
        return b"", False
    return done.stdout, done.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "evidence/h19_ir_arith_v1/runs")
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

    rows, passed = [], 0
    for n in range(MAX_COUNT + 1):
        source = module_source(n)
        (out / f"ir_arith_{n}.slop").write_text(source, encoding="utf-8")
        built = lower(parse_placed(source).module)
        path = out / f"ir_arith_{n}.mb"
        path.write_bytes(built.image)
        expected = reference(n)
        model = run_model(built.image, b"", profile, loader="raw", max_steps=1_000_000,
                          max_address=len(built.image) - 1, trace_accesses=True)
        max_access = max((a.address for a in model.memory_accesses), default=-1)
        b_out, b_steps = run_bolge19(args.engine, path)
        f_out, f_halt = run_fast20(fast20, path)
        checks = {"model": model.stdout == expected and model.status is RunStatus.HALT,
                  "bolge19": b_out == expected and b_steps == model.steps,
                  "fast20": f_out == expected and f_halt,
                  "halts_at_in_image_stub": model.final_c == built.cells["halt"] < len(built.image),
                  "no_access_above_image": max_access < len(built.image),
                  "image_equals_h18_builder": built.image == build_arith_loop(n).image,
                  "max_byte_below_128": max(built.image) < 128}
        ok = all(checks.values())
        passed += ok
        rows.append({"count": n, "cells": len(built.image), "image_sha256": digest(built.image),
                     "expected_hex": expected.hex(), "vm_steps": model.steps,
                     "max_access": max_access, "checks": checks, "pass": ok})

    refusals, refusals_ok = [], True
    base = module_source(4)
    mutants = {
        "breq-rhs-2.slop": base.replace("breq v, 1, done, body", "breq v, 2, done, body"),
        "counter-not-pow3.slop": base.replace("st Z, 81", "st Z, 80"),
        "acc-seed-changed.slop": base.replace("st ACC, 5", "st ACC, 6"),
        "crazy-on-counter.slop": base.replace("craz ACC", "craz Z"),
        "no-crazy.slop": base.replace("    craz ACC\n", ""),
        "contradicted-case.slop": base.replace("case ,1bd309e503eb01ee", "case ,1bd309e503eb01ef"),
    }
    for name, source in mutants.items():
        (out / name).write_text(source, encoding="utf-8")
        try:
            lower(parse_placed(source).module)
            refused = False
        except AssemblyError:
            refused = True
        refusals_ok &= refused
        refusals.append({"source": name, "refused": refused})

    controls, controls_ok = [], True
    built = lower(parse_placed(base).module)
    expected = reference(4)
    broken_first = bytearray(built.image)
    broken_first[dispatch_values(4)[0] + built.cells["delta"]] ^= 1
    broken_halt = bytearray(built.image)
    halt_rotations = seed(built.cells["halt"] - 1)[1]
    broken_halt[built.cells["halt_entry"]] = built.cells["resume"] // 3 ** (18 - halt_rotations)
    broken_counter = bytearray(built.image)
    broken_counter[built.cells["Z"]] += 1
    for name, cells in (("mutant-first-entry.mb", broken_first), ("mutant-halt-entry.mb", broken_halt),
                        ("mutant-counter-seed.mb", broken_counter)):
        path = out / name
        path.write_bytes(bytes(cells))
        b_out, b_steps = run_bolge19(args.engine, path)
        f_out, f_halt = run_fast20(fast20, path)
        differs = (b_out, b_steps is not None) != (expected, True) and (f_out, f_halt) != (expected, True)
        controls_ok &= differs
        controls.append({"image": name, "stdout_hex": {"bolge19": b_out.hex(), "fast20": f_out.hex()},
                         "halted": {"bolge19": b_steps is not None, "fast20": f_halt},
                         "differs_from_reference": differs})

    fast20.unlink()
    with (out / "cases.jsonl").open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    status = "PASS" if passed == len(rows) and controls_ok and refusals_ok else "FAIL"
    write_json(out / "report.json", {
        "status": status, "lowering": LOWERING, "counts": list(range(MAX_COUNT + 1)),
        "cases": len(rows), "pass": passed, "module_refusals": refusals,
        "negative_controls": controls,
        "model_bound": "max_address = len(image) - 1 (any read above the image would be MODEL_BOUND)",
        "ir_path": "parse_placed(module_source(n)) -> check_module -> lower -> native_arith_loop._build",
        "upstream_fast20": {"revision": UPSTREAM_REVISION, "sha256": UPSTREAM_SHA256},
        "host": {"python": platform.python_version(), "platform": platform.platform()},
        "not_demonstrated": [
            "CFGs other than the arithmetic loop: check_module refuses any other block shape.",
            "CrazyCell in the predicated compiler: predicated.py still has no lowering for it.",
            "Borrow-based arithmetic (add/sub with carry) in a re-executing loop: no store opcode and crazy is tritwise (see H18).",
            "A layout search driven by the module: layouts are the frozen H18 ones keyed by n.",
            "Loading with the canonical loader: the image contains inert cells.",
        ],
    })
    (out / "SHA256SUMS.txt").write_text(
        "".join(f"{digest(p.read_bytes())}  {p.name}\n" for p in sorted(out.iterdir())), encoding="utf-8")
    print(f"{status}: {passed}/{len(rows)} counts, refusals {'ok' if refusals_ok else 'FAILED'}, "
          f"controls {'differ' if controls_ok else 'DID NOT differ'}")
    print(f"evidence: {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

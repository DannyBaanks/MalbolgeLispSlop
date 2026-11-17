#!/usr/bin/env python3
"""Seal H16: the countdown whose exit is decided inside the image, on upstream
fast20.c, bolge19 and the Python model, for every count the builder supports.

The model runs with max_address = len(image) - 1: any read above the image would
return MODEL_BOUND, so a HALT proves the exit never left the image. Every run
must end by itself with the exact output; bolge19 and the model must agree on
the step count where the engine reports it.
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
from slopsynth.model import RunStatus, run_model
from slopsynth.native_asm import seed
from slopsynth.native_count_in import LOWERING, MAX_COUNT, build_count_in, counter_values, dispatch_values
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
    parser.add_argument("--output-root", type=Path, default=ROOT / "evidence/h16_count_in_v1/runs")
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
        loop = build_count_in(n)
        path = out / f"count_in_{n}.mb"
        path.write_bytes(loop.image)
        expected = bytes(v & 255 for v in counter_values(n))
        # strict model bound: the cell at len(image) is already above the image
        model = run_model(loop.image, b"", profile, loader="raw", max_steps=1_000_000,
                          max_address=len(loop.image) - 1, trace_accesses=True)
        max_access = max((a.address for a in model.memory_accesses), default=-1)
        b_out, b_steps = run_bolge19(args.engine, path)
        f_out, f_halt = run_fast20(fast20, path)
        checks = {"model": model.stdout == expected and model.status is RunStatus.HALT,
                  "bolge19": b_out == expected and b_steps == model.steps,
                  "fast20": f_out == expected and f_halt,
                  "halts_at_in_image_stub": model.final_c == loop.cells["halt"] < len(loop.image),
                  "no_access_above_image": max_access < len(loop.image),
                  "max_byte_below_128": max(loop.image) < 128}
        ok = all(checks.values())
        passed += ok
        rows.append({"count": n, "cells": len(loop.image), "image_sha256": digest(loop.image),
                     "expected_hex": expected.hex(), "vm_steps": model.steps,
                     "max_access": max_access, "checks": checks, "pass": ok,
                     "cells_map": {k: v for k, v in loop.cells.items()}})

    controls, controls_ok = [], True
    loop = build_count_in(4)
    expected = bytes(v & 255 for v in counter_values(4))
    # first dispatch entry (v = 3^4, pass 1): its target seed flips, so the first pass jumps elsewhere
    broken_first = bytearray(loop.image)
    first_entry = dispatch_values(4)[0] + loop.cells["delta"]
    broken_first[first_entry] ^= 1
    # halt entry (v = 1): re-seeded so that after its prologue rotations it points at
    # the resume path instead of the halt, so the loop runs one pass too many and prints extra
    broken_halt = bytearray(loop.image)
    halt_rotations = seed(loop.cells["halt"] - 1)[1]
    broken_halt[loop.cells["halt_entry"]] = loop.cells["resume"] // 3 ** (18 - halt_rotations)
    # counter seed: the counter no longer starts at 3^4, so the first dispatch reads an empty cell
    broken_counter = bytearray(loop.image)
    broken_counter[loop.cells["Z"]] += 1
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
                         "differs_from_count_in": differs})

    fast20.unlink()
    with (out / "cases.jsonl").open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    status = "PASS" if passed == len(rows) and controls_ok else "FAIL"
    write_json(out / "report.json", {
        "status": status, "lowering": LOWERING, "counts": list(range(MAX_COUNT + 1)),
        "cases": len(rows), "pass": passed, "negative_controls": controls,
        "model_bound": "max_address = len(image) - 1 (any read above the image would be MODEL_BOUND)",
        "upstream_fast20": {"revision": UPSTREAM_REVISION, "sha256": UPSTREAM_SHA256},
        "host": {"python": platform.python_version(), "platform": platform.platform()},
        "not_demonstrated": [
            "A compiler from IR: each count has a generated layout, and the body is always the pre-rotate dispatch countdown.",
            f"Counts above {MAX_COUNT}: the dispatch table spreads over the low image and competes with the bootstrap and the prologue's far-pointer slots.",
            "Loop bodies that compute with several cells, or branch on more than the counter.",
            "Loading with the canonical loader: the image contains inert cells that are not valid opcodes.",
        ],
    })
    (out / "SHA256SUMS.txt").write_text(
        "".join(f"{digest(p.read_bytes())}  {p.name}\n" for p in sorted(out.iterdir())), encoding="utf-8")
    print(f"{status}: {passed}/{len(rows)} counts, negative controls {'differ' if controls_ok else 'DID NOT differ'}")
    print(f"evidence: {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

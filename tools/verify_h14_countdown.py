#!/usr/bin/env python3
"""Seal H14: native countdown loops (counter state rewritten on every pass) on
upstream fast20.c, bolge19 and the Python model, for every count the builder supports.

Every run must end by itself with the exact output; bolge19 and the model must
agree on the step count where the engine reports it.
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
from slopsynth.native_count import LOWERING, MAX_COUNT, build_countdown, counter_values
from slopsynth.profile import load_profile
from tools.verify_h9_fast20 import UPSTREAM_REVISION, UPSTREAM_SHA256, digest, write_json

TIMEOUT_S = 60
MODEL_MAX_ADDRESS = 3**19 - 1


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
    parser.add_argument("--output-root", type=Path, default=ROOT / "evidence/h14_countdown_v1/runs")
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
        loop = build_countdown(n)
        path = out / f"countdown_{n}.mb"
        path.write_bytes(loop.image)
        expected = bytes(v & 255 for v in counter_values(n))
        model = run_model(loop.image, b"", profile, loader="raw", max_steps=1_000_000, max_address=MODEL_MAX_ADDRESS)
        b_out, b_steps = run_bolge19(args.engine, path)
        f_out, f_halt = run_fast20(fast20, path)
        checks = {"model": model.stdout == expected and model.status is RunStatus.HALT,
                  "bolge19": b_out == expected and b_steps == model.steps,
                  "fast20": f_out == expected and f_halt,
                  "halts_at_stub": model.final_c == loop.cells["halt"],
                  "max_byte_below_128": max(loop.image) < 128}
        ok = all(checks.values())
        passed += ok
        rows.append({"count": n, "cells": len(loop.image), "image_sha256": digest(loop.image),
                     "expected_hex": expected.hex(), "vm_steps": model.steps, "checks": checks, "pass": ok})

    controls, controls_ok = [], True
    loop = build_countdown(3)
    expected = bytes(v & 255 for v in counter_values(3))
    broken_table = bytearray(loop.image)
    first_entry = counter_values(3)[0] + loop.cells["delta"]  # table cell the first pass's jump reads
    broken_table[first_entry] ^= 1  # its far address changes: the first pass jumps elsewhere
    other_start = bytearray(loop.image)
    other_start[loop.cells["Z"]] = other_start[loop.cells["Z"]] + 1  # the counter no longer starts at 3^3
    for name, cells in (("mutant-table-cell.mb", broken_table), ("mutant-counter-seed.mb", other_start)):
        path = out / name
        path.write_bytes(bytes(cells))
        b_out, b_steps = run_bolge19(args.engine, path)
        f_out, f_halt = run_fast20(fast20, path)
        differs = (b_out, b_steps is not None) != (expected, True) and (f_out, f_halt) != (expected, True)
        controls_ok &= differs
        controls.append({"image": name, "stdout_hex": {"bolge19": b_out.hex(), "fast20": f_out.hex()},
                         "halted": {"bolge19": b_steps is not None, "fast20": f_halt}, "differs_from_countdown": differs})

    fast20.unlink()
    with (out / "cases.jsonl").open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    status = "PASS" if passed == len(rows) and controls_ok else "FAIL"
    write_json(out / "report.json", {
        "status": status, "lowering": LOWERING, "counts": list(range(MAX_COUNT + 1)),
        "cases": len(rows), "pass": passed, "negative_controls": controls,
        "upstream_fast20": {"revision": UPSTREAM_REVISION, "sha256": UPSTREAM_SHA256},
        "host": {"python": platform.python_version(), "platform": platform.platform()},
        "not_demonstrated": [
            "A compiler from IR: each count has a generated layout, and the body is always `rotate; output; exit on far value`.",
            f"Counts above {MAX_COUNT}: counter values are table addresses and must fit in the image.",
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

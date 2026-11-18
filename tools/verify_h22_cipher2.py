#!/usr/bin/env python3
"""Seal H22: the chained two-accumulator cipher on upstream fast20.c, bolge19
and the Python model. Model bound max_address = len(image) - 1. Negative
controls mutate a selector dispatch entry and each accumulator seed; all must
differ on both VMs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import random
import re
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from slopsynth.model import RunStatus, run_model
from slopsynth.native_cipher2 import LOWERING, build_cipher2, chains, reference
from slopsynth.profile import load_profile
from tools.verify_h9_fast20 import UPSTREAM_REVISION, UPSTREAM_SHA256, digest, write_json

TIMEOUT_S = 60


def run_bolge19(engine, image, stdin):
    try:
        done = subprocess.run([str(engine), str(image), "--loader", "raw", "--max-steps", "2000000"],
                              input=stdin, capture_output=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return b"", None
    halt = re.search(rb"HALT steps=(\d+)", done.stderr)
    return done.stdout, int(halt.group(1)) if halt and done.returncode == 0 else None


def run_fast20(fast20, image, stdin):
    try:
        done = subprocess.run([str(fast20), str(image)], input=stdin, capture_output=True, timeout=10)
    except subprocess.TimeoutExpired:
        return b"", False
    return done.stdout, done.returncode == 0


def campaign():
    rng = random.Random(22)
    cases = [b"", b"\x00", b"\x02", b"\x02A", b"\x02A\x02B\x00", b"\x01\x02\xff\x00",
             b"\x03hi\x04yo\x00", b"\x01" * 64 + b"\x00", bytes(range(1, 128)), b"\xff" * 100 + b"\x00"]
    for _ in range(40):
        n = rng.randrange(0, 400)
        cases.append(bytes(rng.randrange(1, 256) for _ in range(n)) + (b"\x00" if rng.random() < 0.7 else b""))
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "evidence/h22_cipher2_v1/runs")
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

    cipher = build_cipher2()
    image_path = out / "cipher2.mb"
    image_path.write_bytes(cipher.image)
    cases = campaign()

    rows, passed = [], 0
    model_empty = run_model(cipher.image, b"", profile, loader="raw", max_steps=3_000_000,
                            max_address=len(cipher.image) - 1, trace_accesses=True)
    max_access = max((a.address for a in model_empty.memory_accesses), default=-1)
    for i, data in enumerate(cases):
        expected = reference(data)
        model = run_model(cipher.image, data, profile, loader="raw", max_steps=3_000_000,
                          max_address=len(cipher.image) - 1)
        b_out, b_steps = run_bolge19(args.engine, image_path, data)
        f_out, f_halt = run_fast20(fast20, image_path, data)
        checks = {"model": model.stdout == expected and model.status is RunStatus.HALT,
                  "bolge19": b_out == expected and b_steps == model.steps,
                  "fast20": f_out == expected and f_halt,
                  "halts_at_in_image_stub": model.final_c == cipher.cells["halt"] < len(cipher.image)}
        ok = all(checks.values())
        passed += ok
        rows.append({"case": i, "stdin_hex": data.hex(), "expected_hex": expected.hex(),
                     "vm_steps": model.steps, "checks": checks, "pass": ok})

    data = b"\x02A\x02B\x03C\x00"
    r = run_model(cipher.image, data, profile, loader="raw", max_steps=3_000_000,
                  max_address=len(cipher.image) - 1, trace_writes=True)
    c1, c2 = chains(data)
    w1 = [w.after for w in r.memory_writes if w.address == cipher.cells["ACC"]]
    w2 = [w.after for w in r.memory_writes if w.address == cipher.cells["ACC2"]]
    chains_ok = w1 == c1[:3] and w2 == c2[:3]

    controls, controls_ok = [], True
    mutants = []
    broken = bytearray(cipher.image)
    broken[cipher.cells["table"] + 2] ^= 1
    mutants.append(("mutant-selector-entry.mb", bytes(broken), b"\x02A\x02B"))
    broken = bytearray(cipher.image)
    broken[cipher.cells["ACC"]] += 1
    mutants.append(("mutant-acc1-seed.mb", bytes(broken), b"\x02A\x02B"))
    broken = bytearray(cipher.image)
    broken[cipher.cells["ACC2"]] += 1
    mutants.append(("mutant-acc2-seed.mb", bytes(broken), b"\x02A\x02B"))
    for name, cells, control_input in mutants:
        expected = reference(control_input)
        path = out / name
        path.write_bytes(cells)
        b_out, b_steps = run_bolge19(args.engine, path, control_input)
        f_out, f_halt = run_fast20(fast20, path, control_input)
        differs = (b_out, b_steps is not None) != (expected, True) and (f_out, f_halt) != (expected, True)
        controls_ok &= differs
        controls.append({"image": name, "stdin_hex": control_input.hex(),
                         "stdout_hex": {"bolge19": b_out.hex(), "fast20": f_out.hex()},
                         "halted": {"bolge19": b_steps is not None, "fast20": f_halt},
                         "differs_from_reference": differs})

    fast20.unlink()
    with (out / "cases.jsonl").open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    status = "PASS" if passed == len(rows) and controls_ok and chains_ok else "FAIL"
    write_json(out / "report.json", {
        "status": status, "lowering": LOWERING, "image_cells": len(cipher.image),
        "image_sha256": digest(cipher.image), "cases": len(rows), "pass": passed,
        "chains_ok": chains_ok, "max_access": max_access, "negative_controls": controls,
        "model_bound": "max_address = len(image) - 1 (any read above the image would be MODEL_BOUND)",
        "upstream_fast20": {"revision": UPSTREAM_REVISION, "sha256": UPSTREAM_SHA256},
        "host": {"python": platform.python_version(), "platform": platform.platform()},
        "not_demonstrated": [
            "Borrow-based arithmetic per pass: no store opcode and crazy is tritwise (see H18/H20).",
            "A compiler from IR for this two-accumulator loop: the IR lowering covers the H17/H19/H21 CFGs, not yet this chain.",
            "Loading with the canonical loader: the image contains inert cells.",
            "A proof for all inputs: the campaign is finite (50 cases).",
        ],
    })
    (out / "SHA256SUMS.txt").write_text(
        "".join(f"{digest(p.read_bytes())}  {p.name}\n" for p in sorted(out.iterdir())), encoding="utf-8")
    print(f"{status}: {passed}/{len(rows)} cases, chains {'ok' if chains_ok else 'BAD'}, "
          f"controls {'differ' if controls_ok else 'DID NOT differ'}")
    print(f"evidence: {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

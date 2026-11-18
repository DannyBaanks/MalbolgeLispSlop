#!/usr/bin/env python3
"""Seal H21: the cipher loop lowered from an IR module, on upstream fast20.c,
bolge19 and the Python model.

The module (examples/ir_cipher.slop shape) is compiled through the IR path
(parse -> check -> lower); the emitted image must be byte-identical to the sealed
H20 image. The model runs with max_address = len(image) - 1. A campaign of inputs
must match the reference on all three; bolge19 and the model must agree on step
counts. Refused modules must raise AssemblyError; image mutants must differ on
both VMs.
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
from slopsynth.assemble import AssemblyError
from slopsynth.lang import parse_placed
from slopsynth.model import RunStatus, run_model
from slopsynth.native_cipher import LOWERING as H20_LOWERING, PARAMS as H20_PARAMS, _build as h20_build, reference
from slopsynth.native_ir_cipher import LOWERING, lower
from slopsynth.profile import load_profile
from tools.verify_h9_fast20 import UPSTREAM_REVISION, UPSTREAM_SHA256, digest, write_json

TIMEOUT_S = 60
MODULE = ROOT / "examples/ir_cipher.slop"


def run_bolge19(engine: Path, image: Path, stdin: bytes) -> tuple[bytes, int | None]:
    try:
        done = subprocess.run([str(engine), str(image), "--loader", "raw", "--max-steps", "2000000"],
                              input=stdin, capture_output=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return b"", None
    halt = re.search(rb"HALT steps=(\d+)", done.stderr)
    return done.stdout, int(halt.group(1)) if halt and done.returncode == 0 else None


def run_fast20(fast20: Path, image: Path, stdin: bytes) -> tuple[bytes, bool]:
    try:
        done = subprocess.run([str(fast20), str(image)], input=stdin, capture_output=True, timeout=10)
    except subprocess.TimeoutExpired:
        return b"", False
    return done.stdout, done.returncode == 0


def campaign() -> list[bytes]:
    rng = random.Random(21)
    cases = [b"", b"\x00", b"\x02", b"\x02A", b"\x02A\x02B\x00", b"\x01\x02\xff\x00",
             b"\x03hi\x04yo\x00", b"\x01" * 64 + b"\x00", bytes(range(1, 128)), b"\xff" * 100 + b"\x00"]
    for _ in range(40):
        n = rng.randrange(0, 400)
        cases.append(bytes(rng.randrange(1, 256) for _ in range(n)) + (b"\x00" if rng.random() < 0.7 else b""))
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "evidence/h21_ir_cipher_v1/runs")
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

    built = lower(parse_placed(MODULE.read_text(encoding="utf-8")).module)  # IR path
    (out / "ir_cipher.slop").write_text(MODULE.read_text(encoding="utf-8"), encoding="utf-8")
    image_path = out / "ir_cipher.mb"
    image_path.write_bytes(built.image)
    cases = campaign()

    rows, passed = [], 0
    model_empty = run_model(built.image, b"", profile, loader="raw", max_steps=3_000_000,
                            max_address=len(built.image) - 1, trace_accesses=True)
    max_access = max((a.address for a in model_empty.memory_accesses), default=-1)
    for i, data in enumerate(cases):
        expected = reference(data)
        model = run_model(built.image, data, profile, loader="raw", max_steps=3_000_000,
                          max_address=len(built.image) - 1)
        b_out, b_steps = run_bolge19(args.engine, image_path, data)
        f_out, f_halt = run_fast20(fast20, image_path, data)
        checks = {"model": model.stdout == expected and model.status is RunStatus.HALT,
                  "bolge19": b_out == expected and b_steps == model.steps,
                  "fast20": f_out == expected and f_halt,
                  "halts_at_in_image_stub": model.final_c == built.cells["halt"] < len(built.image),
                  "image_equals_h20_builder": built.image == h20_build(H20_PARAMS).image}
        ok = all(checks.values())
        passed += ok
        rows.append({"case": i, "stdin_hex": data.hex(), "expected_hex": expected.hex(),
                     "vm_steps": model.steps, "checks": checks, "pass": ok})

    refusals, refusals_ok = [], True
    base = MODULE.read_text(encoding="utf-8")
    mutants = {
        "brz-swapped.slop": base.replace("brz s, zero, echo", "brz s, echo, zero"),
        "acc-seed-6.slop": base.replace("st ACC, 5", "st ACC, 6"),
        "craz-other.slop": base.replace("craz ACC", "craz OTHER"),
        "no-write.slop": base.replace("    write\n    jump top", "    jump top"),
        "contradicted-case.slop": base.replace("case 0241,c9", "case 0241,c8"),
        "breq-instead.slop": base.replace("brz s, zero, echo", "breq s, 1, zero, echo"),
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
    expected = reference(b"\x02A\x02B")
    mutants_img = []
    broken = bytearray(built.image)
    broken[built.cells["table"] + 2] ^= 1
    mutants_img.append(("mutant-selector-entry.mb", bytes(broken), b"\x02A\x02B"))
    broken = bytearray(built.image)
    broken[built.cells["ACC"]] += 1
    mutants_img.append(("mutant-acc-seed.mb", bytes(broken), b"\x02A\x02B"))
    for name, cells, control_input in mutants_img:
        exp = reference(control_input)
        path = out / name
        path.write_bytes(cells)
        b_out, b_steps = run_bolge19(args.engine, path, control_input)
        f_out, f_halt = run_fast20(fast20, path, control_input)
        differs = (b_out, b_steps is not None) != (exp, True) and (f_out, f_halt) != (exp, True)
        controls_ok &= differs
        controls.append({"image": name, "stdin_hex": control_input.hex(),
                         "stdout_hex": {"bolge19": b_out.hex(), "fast20": f_out.hex()},
                         "halted": {"bolge19": b_steps is not None, "fast20": f_halt},
                         "differs_from_reference": differs})

    fast20.unlink()
    with (out / "cases.jsonl").open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    status = "PASS" if passed == len(rows) and controls_ok and refusals_ok else "FAIL"
    write_json(out / "report.json", {
        "status": status, "lowering": LOWERING, "h20_lowering": H20_LOWERING,
        "image_cells": len(built.image), "image_sha256": digest(built.image),
        "cases": len(rows), "pass": passed, "module_refusals": refusals,
        "negative_controls": controls, "max_access": max_access,
        "model_bound": "max_address = len(image) - 1 (any read above the image would be MODEL_BOUND)",
        "ir_path": "parse_placed(examples/ir_cipher.slop) -> check_module -> lower -> native_cipher._build(PARAMS)",
        "upstream_fast20": {"revision": UPSTREAM_REVISION, "sha256": UPSTREAM_SHA256},
        "host": {"python": platform.python_version(), "platform": platform.platform()},
        "not_demonstrated": [
            "CFGs other than the cipher loop: check_module refuses any other block shape.",
            "CrazyCell/rot/breq in the predicated compiler: predicated.py still has no lowering for them.",
            "Borrow-based arithmetic per pass: no store opcode and crazy is tritwise (see H18/H20).",
            "Loading with the canonical loader: the image contains inert cells.",
            "A proof for all inputs: the campaign is 50 finite cases.",
        ],
    })
    (out / "SHA256SUMS.txt").write_text(
        "".join(f"{digest(p.read_bytes())}  {p.name}\n" for p in sorted(out.iterdir())), encoding="utf-8")
    print(f"{status}: {passed}/{len(rows)} cases, refusals {'ok' if refusals_ok else 'FAILED'}, "
          f"controls {'differ' if controls_ok else 'DID NOT differ'}")
    print(f"evidence: {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

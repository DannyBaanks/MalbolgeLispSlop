#!/usr/bin/env python3
"""Seal H15: the first native loop emitted from an IR module.

The module is `examples/ir_loop.slop` (H3's loop CFG). `lower()` checks the CFG
and every declared case, emits a lapped native image, and the image must halt by
itself on upstream fast20.c, bolge19 and the Python model, after exactly
`startup + passes * steps_per_pass` VM steps where the engine reports them.
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
from slopsynth.lang import parse_placed
from slopsynth.model import RunStatus, run_model
from slopsynth.native_ir_loop import EOF_WORD, LOWERING, lower, reference
from slopsynth.native_loop import EOF_BYTE
from slopsynth.profile import load_profile
from tools.verify_h9_fast20 import UPSTREAM_REVISION, UPSTREAM_SHA256, digest, write_json

TIMEOUT_S = 300
MODEL_LIMIT = 300  # the Python model checks inputs up to this many bytes
CONTROL_TAIL = 8


def inputs() -> list[tuple[str, bytes]]:
    rng = random.Random(15)
    cases = [("empty", b"")]
    cases += [("single", bytes([b])) for b in range(256)]
    cases += [("single_zero_tail", bytes([b, 0])) for b in range(0, 256, 7)]
    cases += [("pair", bytes([b, 255 - b])) for b in range(1, 256, 5)]
    cases += [("pair_zero_tail", bytes([b, 255 - b, 0])) for b in range(1, 256, 9)]
    cases += [("ramp", bytes(range(1, 256))), ("text", b"(+ 1 2)\n" * 50),
              ("nul", b"\x00" * 500), ("eof_low_byte", bytes([EOF_BYTE]) * 500)]
    cases += [("random", rng.randbytes(n)) for n in (2, 3, 7, 64, 163, 164, 1000, 4096, 65536, 100_000)]
    cases += [("random_1m", rng.randbytes(1_000_000))]
    cases += [("nozero_1m", bytes((i % 255) + 1 for i in range(1_000_000)))]
    return cases


def passes(stdin: bytes) -> int:
    """Iterations the loop runs: selectors that are not zero."""
    count, idx = 0, 0
    while idx < len(stdin):
        selector = stdin[idx]
        idx += 1
        if selector == 0:
            break
        count += 1
        if idx < len(stdin):
            idx += 1
    return count


def run_bolge19(engine: Path, image: Path, stdin: bytes, steps: int) -> tuple[bytes, bool, int | None]:
    done = subprocess.run([str(engine), str(image), "--loader", "raw", "--max-steps", str(steps)],
                          input=stdin, capture_output=True, timeout=TIMEOUT_S)
    halt = re.search(rb"HALT steps=(\d+)", done.stderr)
    return done.stdout, done.returncode == 0 and halt is not None, int(halt.group(1)) if halt else None


def run_fast20(fast20: Path, image: Path, stdin: bytes, limit: int | None = None) -> tuple[bytes, bool]:
    """Run to completion; with `limit`, keep that many output bytes and stop a run that does not end."""
    if limit is None:
        done = subprocess.run([str(fast20), str(image)], input=stdin, capture_output=True, timeout=TIMEOUT_S)
        return done.stdout, done.returncode == 0
    process = subprocess.Popen([str(fast20), str(image)], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    process.stdin.write(stdin)
    process.stdin.close()
    out = process.stdout.read(limit)
    halted = process.poll() is not None or not process.stdout.read(1) and process.wait(5) is not None
    process.kill()
    process.wait()
    return out, halted and process.returncode == 0


def mutants(loop) -> dict[str, tuple[bytes, bytes, bytes]]:
    """(image, stdin, expected stdout) for each negative control."""
    table, eof_cell = loop.cells["table"], loop.cells["eof_cell"]
    zero_loops = bytearray(loop.image)
    zero_loops[table] = zero_loops[table + 1]  # selector 0 now takes the resume path
    early = bytearray(loop.image)
    early[table + ord("M")] = early[eof_cell]  # the byte 'M' now takes the halt path
    return {"mutant-zero-loops.mb": (bytes(zero_loops), b"\x00", b""),
            "mutant-early-exit.mb": (bytes(early), b"M?", b"?")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "evidence/h15_native_ir_loop_v1/runs")
    parser.add_argument("--module", type=Path, default=ROOT / "examples/ir_loop.slop")
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

    module = parse_placed(args.module.read_text(encoding="utf-8")).module
    profile = load_profile(ROOT / "profiles/fixed19.json")
    loop = lower(module)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.output_root / f"{stamp}-{uuid.uuid4().hex[:8]}"
    out.mkdir(parents=True)
    fast20 = out / "fast20"
    subprocess.run([args.cc, "-O2", "-w", "-o", str(fast20), str(args.fast20_src)], check=True)
    image = out / "ir_loop.mb"
    image.write_bytes(loop.image)

    startup = run_model(loop.image, b"", profile, loader="raw", max_steps=10**6, max_address=len(loop.image)).steps
    rows, passed = [], 0
    for label, stdin in inputs():
        steps = startup + loop.steps_per_pass * passes(stdin)
        b_out, b_halt, b_steps = run_bolge19(args.engine, image, stdin, steps + 1)
        f_out, f_halt = run_fast20(fast20, image, stdin)
        got = {"bolge19": b_out, "fast20": f_out}
        halted = {"bolge19": b_halt and b_steps == steps, "fast20": f_halt}
        if len(stdin) <= MODEL_LIMIT:
            model = run_model(loop.image, stdin, profile, loader="raw", max_steps=steps + 1, max_address=len(loop.image))
            got["model"] = model.stdout
            halted["model"] = model.status is RunStatus.HALT and model.steps == steps
        ok = all(value == reference(stdin) for value in got.values()) and all(halted.values())
        passed += ok
        rows.append({"label": label, "stdin_bytes": len(stdin), "stdin_sha256": digest(stdin), "passes": passes(stdin),
                     "vm_steps": steps, "stdout_sha256": {name: digest(value) for name, value in got.items()},
                     "halted_at_predicted_step": halted, "pass": ok})

    controls, controls_ok = [], True
    for name, (cells, probe, expected) in mutants(loop).items():
        path = out / name
        path.write_bytes(cells)
        limit = len(expected) + CONTROL_TAIL
        b_out, b_halt, _ = run_bolge19(args.engine, path, probe, startup + loop.steps_per_pass * (passes(probe) + 2) + 1)
        f_out, f_halt = run_fast20(fast20, path, probe, limit)
        differs = (b_out, b_halt) != (expected, True) and (f_out, f_halt) != (expected, True)
        controls_ok &= differs
        controls.append({"image": name, "stdin_hex": probe.hex(), "stdout_hex": {"bolge19": b_out.hex(), "fast20": f_out.hex()},
                         "halted": {"bolge19": b_halt, "fast20": f_halt}, "differs_from_reference": differs})

    fast20.unlink()
    with (out / "cases.jsonl").open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    status = "PASS" if passed == len(rows) and controls_ok else "FAIL"
    write_json(out / "report.json", {
        "status": status, "lowering": LOWERING, "module": str(args.module.relative_to(ROOT)),
        "cases_declared": len(module.cases), "cells": len(loop.image), "image_sha256": digest(loop.image),
        "largest_image_byte": max(loop.image),
        "loop": {"head": loop.loop_head, "end": loop.loop_end, "steps_per_pass": loop.steps_per_pass,
                 "startup_and_exit_steps": startup, "eof_word": EOF_WORD, "eof_byte": EOF_BYTE,
                 "cells": loop.cells},
        "cases": len(rows), "pass": passed, "longest_input_bytes": max(r["stdin_bytes"] for r in rows),
        "longest_run_vm_steps": max(r["vm_steps"] for r in rows), "negative_controls": controls,
        "upstream_fast20": {"revision": UPSTREAM_REVISION, "sha256": UPSTREAM_SHA256},
        "host": {"python": platform.python_version(), "platform": platform.platform()},
        "not_demonstrated": [
            "Loop bodies other than this CFG: `lower` refuses anything but read/brz/halt/read/write/jump.",
            "Memory, arithmetic or nested loops inside a native loop body.",
            "Loading with the canonical loader: the image contains inert cells that are not valid opcodes.",
            "A proof for all inputs: the campaign is a finite set, including every single byte.",
            "Composition with the predicated compiler, which still unrolls the loops it compiles.",
        ],
    })
    (out / "SHA256SUMS.txt").write_text(
        "".join(f"{digest(p.read_bytes())}  {p.name}\n" for p in sorted(out.iterdir())), encoding="utf-8")
    print(f"{status}: {passed}/{len(rows)} cases, negative controls {'differ' if controls_ok else 'DID NOT differ'}")
    print(f"evidence: {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Seal H13b: the native `cat` that halts at end of input, on upstream fast20.c,
bolge19 and the Python model.

Every run must end by itself: fast20 with exit status 0, bolge19 and the model
with HALT, each after exactly the predicted number of VM steps where the engine
reports it, and stdout must equal stdin.
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
from slopsynth.native_cat import EOF_WORD, LOWERING, build_cat
from slopsynth.native_loop import EOF_BYTE
from slopsynth.profile import load_profile
from tools.verify_h9_fast20 import UPSTREAM_REVISION, UPSTREAM_SHA256, digest, write_json

TIMEOUT_S = 300
MODEL_LIMIT = 300  # the Python model checks inputs up to this many bytes
CONTROL_TAIL = 8


def inputs() -> list[tuple[str, bytes]]:
    rng = random.Random(13)
    cases = [("empty", b"")]
    cases += [("single", bytes([b])) for b in range(256)]
    cases += [("pair", bytes([b, 255 - b])) for b in range(0, 256, 5)]
    cases += [("ramp", bytes(range(256))), ("ramp_down", bytes(range(255, -1, -1))), ("text", b"(+ 1 2)\n" * 50),
              ("nul", b"\x00" * 500), ("eof_low_byte", bytes([EOF_BYTE]) * 500), ("byte_242", b"\xf2" * 500)]
    cases += [("random", rng.randbytes(n)) for n in (2, 3, 7, 64, 163, 164, 1000, 4096, 65536, 100_000)]
    cases += [("random_1m", rng.randbytes(1_000_000))]
    return cases


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


def mutants(cat) -> dict[str, bytes]:
    table, eof_cell = cat.cells["table"], cat.cells["eof_cell"]
    no_exit = bytearray(cat.image)
    no_exit[eof_cell] = no_exit[table]            # EOF now takes the byte path: the loop never ends
    early = bytearray(cat.image)
    early[table + ord("M")] = early[eof_cell]     # the byte 'M' now takes the EOF path
    return {"mutant-no-exit.mb": bytes(no_exit), "mutant-early-exit.mb": bytes(early)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "evidence/h13_cat_v1/runs")
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
    cat = build_cat()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.output_root / f"{stamp}-{uuid.uuid4().hex[:8]}"
    out.mkdir(parents=True)
    fast20 = out / "fast20"
    subprocess.run([args.cc, "-O2", "-w", "-o", str(fast20), str(args.fast20_src)], check=True)
    image = out / "cat.mb"
    image.write_bytes(cat.image)

    startup = run_model(cat.image, b"", profile, loader="raw", max_steps=10**6, max_address=len(cat.image)).steps
    rows, passed = [], 0
    for label, stdin in inputs():
        steps = startup + cat.steps_per_byte * len(stdin)
        b_out, b_halt, b_steps = run_bolge19(args.engine, image, stdin, steps + 1)
        f_out, f_halt = run_fast20(fast20, image, stdin)
        got = {"bolge19": b_out, "fast20": f_out}
        halted = {"bolge19": b_halt and b_steps == steps, "fast20": f_halt}
        if len(stdin) <= MODEL_LIMIT:
            model = run_model(cat.image, stdin, profile, loader="raw", max_steps=steps + 1, max_address=len(cat.image))
            got["model"] = model.stdout
            halted["model"] = model.status is RunStatus.HALT and model.steps == steps
        ok = all(value == stdin for value in got.values()) and all(halted.values())
        passed += ok
        rows.append({"label": label, "stdin_bytes": len(stdin), "stdin_sha256": digest(stdin), "vm_steps": steps,
                     "stdout_sha256": {name: digest(value) for name, value in got.items()},
                     "halted_at_predicted_step": halted, "pass": ok})

    controls, controls_ok = [], True
    probe = b"HALT ME MAYBE"
    for name, cells in mutants(cat).items():
        path = out / name
        path.write_bytes(cells)
        limit = len(probe) + CONTROL_TAIL
        steps = startup + cat.steps_per_byte * limit
        b_out, b_halt, _ = run_bolge19(args.engine, path, probe, steps)
        f_out, f_halt = run_fast20(fast20, path, probe, limit)
        differs = (b_out, b_halt) != (probe, True) and (f_out, f_halt) != (probe, True)
        controls_ok &= differs
        controls.append({"image": name, "stdout_hex": {"bolge19": b_out.hex(), "fast20": f_out.hex()},
                         "halted": {"bolge19": b_halt, "fast20": f_halt}, "differs_from_cat": differs})

    fast20.unlink()
    with (out / "cases.jsonl").open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    status = "PASS" if passed == len(rows) and controls_ok else "FAIL"
    write_json(out / "report.json", {
        "status": status, "lowering": LOWERING, "cells": len(cat.image), "image_sha256": digest(cat.image),
        "largest_image_byte": max(cat.image),
        "loop": {"head": cat.loop_head, "end": cat.loop_end, "steps_per_byte": cat.steps_per_byte,
                 "startup_and_exit_steps": startup, "eof_word": EOF_WORD, "cells": cat.cells},
        "cases": len(rows), "pass": passed, "longest_input_bytes": max(r["stdin_bytes"] for r in rows),
        "longest_run_vm_steps": max(r["vm_steps"] for r in rows), "negative_controls": controls,
        "upstream_fast20": {"revision": UPSTREAM_REVISION, "sha256": UPSTREAM_SHA256},
        "host": {"python": platform.python_version(), "platform": platform.platform()},
        "not_demonstrated": [
            "Loop bodies other than this one: the layout is generated for `cat` only, not compiled from IR.",
            "Integration with the predicated compiler, which still unrolls IR loops.",
            "Loading with the canonical loader: the image contains inert cells that are not valid opcodes.",
            "A proof for all inputs: the campaign is a finite set of inputs, including every single byte.",
        ],
    })
    (out / "SHA256SUMS.txt").write_text(
        "".join(f"{digest(p.read_bytes())}  {p.name}\n" for p in sorted(out.iterdir())), encoding="utf-8")
    print(f"{status}: {passed}/{len(rows)} cases, negative controls {'differ' if controls_ok else 'DID NOT differ'}")
    print(f"evidence: {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Seal H13a: the native echo loop on upstream fast20.c, bolge19 and the Python model.

The loop never halts, so each run is cut after the input plus TAIL more bytes:
bolge19 by an exact step limit, fast20 by reading that many bytes and killing it.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import random
import subprocess
import sys
import threading
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from slopsynth.cycles import encrypt
from slopsynth.model import RunStatus, run_model
from slopsynth.native_loop import EOF_BYTE, LOWERING, build_echo_loop
from slopsynth.profile import load_profile
from tools.verify_h9_fast20 import UPSTREAM_REVISION, UPSTREAM_SHA256, digest, write_json

TAIL = 8  # iterations run past the end of input; each prints the EOF byte
TIMEOUT_S = 120
MODEL_LIMIT = 300  # the Python model checks inputs up to this many bytes


def inputs() -> list[tuple[str, bytes]]:
    rng = random.Random(13)
    cases = [("empty", b"")]
    cases += [("single", bytes([b])) for b in range(256)]
    cases += [("ramp", bytes(range(256))), ("text", b"(+ 1 2)\n" * 50), ("nul", b"\x00" * 500),
              ("eof_byte", bytes([EOF_BYTE]) * 500)]
    cases += [("random", rng.randbytes(n)) for n in (2, 3, 7, 64, 163, 164, 1000, 4096, 65536, 100_000)]
    cases += [("random_1m", rng.randbytes(1_000_000))]
    return cases


def run_bolge19(engine: Path, image: Path, stdin: bytes, steps: int) -> bytes:
    done = subprocess.run([str(engine), str(image), "--loader", "raw", "--max-steps", str(steps)],
                          input=stdin, capture_output=True, timeout=TIMEOUT_S)
    return done.stdout


def run_fast20(fast20: Path, image: Path, stdin: bytes, want: int) -> bytes:
    """First `want` output bytes of a run that would otherwise never end."""
    process = subprocess.Popen([str(fast20), str(image)], stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def feed():
        try:
            process.stdin.write(stdin)
            process.stdin.close()
        except BrokenPipeError:
            pass

    feeder = threading.Thread(target=feed, daemon=True)
    feeder.start()
    killer = threading.Timer(TIMEOUT_S, process.kill)
    killer.start()
    try:
        out = bytearray()
        while len(out) < want and (chunk := process.stdout.read(min(65536, want - len(out)))):
            out += chunk
    finally:
        killer.cancel()
        process.kill()
        process.wait()
        feeder.join()
    return bytes(out)


def mutants(loop) -> dict[str, bytes]:
    cells = bytearray(loop.image)
    same_phase = bytearray(cells)
    second_input = loop.head + 1 + 4
    same_phase[second_input] = encrypt(same_phase[second_input])  # both input cells now run on even passes
    wrong_target = bytearray(cells)
    wrong_target[min(loop.data)] ^= 1  # one jump-back target no longer points at the loop head
    return {"mutant-input-phase.mb": bytes(same_phase), "mutant-jump-target.mb": bytes(wrong_target)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "evidence/h13_echo_loop_v1/runs")
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
    loop = build_echo_loop()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.output_root / f"{stamp}-{uuid.uuid4().hex[:8]}"
    out.mkdir(parents=True)
    fast20 = out / "fast20"
    subprocess.run([args.cc, "-O2", "-w", "-o", str(fast20), str(args.fast20_src)], check=True)
    image = out / "echo_loop.mb"
    image.write_bytes(loop.image)

    rows, passed = [], 0
    for label, stdin in inputs():
        expected = stdin + bytes([EOF_BYTE]) * TAIL
        steps = loop.steps_for(len(expected))
        got = {"bolge19": run_bolge19(args.engine, image, stdin, steps),
               "fast20": run_fast20(fast20, image, stdin, len(expected))}
        if len(stdin) <= MODEL_LIMIT:
            model = run_model(loop.image, stdin, profile, loader="raw", max_steps=steps, max_address=4096)
            got["model"] = model.stdout if model.status is RunStatus.MAX_STEPS else b"<" + model.status.value.encode() + b">"
        ok = all(value == expected for value in got.values())
        passed += ok
        rows.append({"label": label, "stdin_bytes": len(stdin), "stdin_sha256": digest(stdin), "iterations": len(expected),
                     "vm_steps": steps, "expected_sha256": digest(expected),
                     "stdout_sha256": {name: digest(value) for name, value in got.items()}, "pass": ok})

    controls, controls_ok = [], True
    probe = bytes(range(65, 91))
    expected = probe + bytes([EOF_BYTE]) * TAIL
    for name, cells in mutants(loop).items():
        path = out / name
        path.write_bytes(cells)
        got = {"bolge19": run_bolge19(args.engine, path, probe, loop.steps_for(len(expected))),
               "fast20": run_fast20(fast20, path, probe, len(expected))}
        differs = all(value != expected for value in got.values())
        controls_ok &= differs
        controls.append({"image": name, "stdout_hex": {k: v.hex() for k, v in got.items()}, "differs_from_echo": differs})

    fast20.unlink()
    with (out / "cases.jsonl").open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    status = "PASS" if passed == len(rows) and controls_ok else "FAIL"
    write_json(out / "report.json", {
        "status": status, "lowering": LOWERING, "cells": len(loop.image), "image_sha256": digest(loop.image),
        "loop": {"head": loop.head, "jump": loop.jump, "steps_per_iteration": loop.steps_per_iteration, "data": loop.data},
        "cases": len(rows), "pass": passed, "longest_input_bytes": max(r["stdin_bytes"] for r in rows),
        "tail_iterations": TAIL, "negative_controls": controls,
        "upstream_fast20": {"revision": UPSTREAM_REVISION, "sha256": UPSTREAM_SHA256},
        "host": {"python": platform.python_version(), "platform": platform.platform()},
        "not_demonstrated": [
            "Termination: the loop has no end-of-input test and never halts.",
            "Loop bodies with arithmetic, memory or branches; the predicated compiler still unrolls IR loops.",
            "Loading with the canonical loader: the image contains inert cells that are not valid opcodes.",
        ],
    })
    (out / "SHA256SUMS.txt").write_text(
        "".join(f"{digest(p.read_bytes())}  {p.name}\n" for p in sorted(out.iterdir())), encoding="utf-8")
    print(f"{status}: {passed}/{len(rows)} cases, negative controls {'differ' if controls_ok else 'DID NOT differ'}")
    print(f"evidence: {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

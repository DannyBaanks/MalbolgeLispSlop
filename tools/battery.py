#!/usr/bin/env python3
"""Run an image on fast20 and bolge19 for many inputs in parallel; compare to the IR reference."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run(cmd, stdin):
    try:
        done = subprocess.run(cmd, input=stdin, capture_output=True, timeout=120)
        return done.stdout.hex(), done.returncode
    except subprocess.TimeoutExpired:
        return None, None


def battery(image: Path, module, inputs, width, bound, fast20: Path, engine: Path, jobs: int = 3):
    from slopsynth.predicated import reference

    def one(stdin):
        want = reference(module, stdin, width, bound)
        upstream = run([str(fast20), str(image)], stdin)
        ours = run([str(engine), str(image), "--loader", "canonical", "--max-steps", "400000000"], stdin)
        return {
            "stdin_hex": stdin.hex(),
            "expected_hex": want.hex(),
            "fast20": {"stdout_hex": upstream[0], "returncode": upstream[1]},
            "bolge19": {"stdout_hex": ours[0], "returncode": ours[1]},
            "pass": upstream[0] == want.hex() and ours[0] == want.hex(),
        }

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        return list(pool.map(one, inputs))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("module", help="module:function returning the IR Module")
    parser.add_argument("inputs", type=Path, help="JSON list of hex inputs")
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--bound", type=int, required=True)
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    mod, fn = args.module.split(":")
    module = getattr(__import__(mod, fromlist=[fn]), fn)()
    inputs = [bytes.fromhex(h) for h in json.loads(args.inputs.read_text())]
    rows = battery(args.image, module, inputs, args.width, args.bound, ROOT / "build/fast20", ROOT / "build/bolge19", args.jobs)
    bad = [r for r in rows if not r["pass"]]
    print(f"{len(rows) - len(bad)}/{len(rows)} pass")
    for r in bad[:10]:
        print(json.dumps(r))

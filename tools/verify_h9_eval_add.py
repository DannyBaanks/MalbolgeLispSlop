#!/usr/bin/env python3
"""Seal a fresh H9 v2 campaign: all 100 digit pairs, endings and negative controls."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.build_eval_add import generate_eval_add_image
from tools.guest_runner import RunConfig, run_guest
from tools.verify_lisp_conformance import orientation_control
from slopsynth.model import run_model
from slopsynth.profile import load_profile
from slopsynth.assemble import format_image
from slopsynth.encode import encode_dispatch_sequence


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "evidence/h9_eval_add_v2/runs")
    parser.add_argument("--engine", type=Path, default=ROOT / "build/bolge19")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_root.resolve() / (stamp + "-" + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    records = []
    failure = None
    engine = args.engine.resolve()
    profile = load_profile(ROOT / "profiles/fixed19.json")
    config = RunConfig("canonical", 10_000_000, 5.0, 512 * 1024 * 1024, 64)
    model_records = []
    image = b""
    try:
        write_json(output / "orientation.json", orientation_control())
        image, manifest = generate_eval_add_image()
        (output / "eval_add.mb").write_bytes(image)
        write_json(output / "manifest.json", manifest)
        (output / "eval_add-spaced.mb").write_bytes(format_image(image, 80))

        def execute(label, image_path, stdin, expected, must_match=True):
            result = run_guest(image_path, stdin, config, engine_path=engine)
            match = result.status.value == "HALT" and result.returncode == 0 and result.stdout == expected
            records.append({
                "label": label, "image": image_path.name, "stdin_hex": stdin.hex(),
                "expected_stdout_hex": expected.hex(), "stdout_hex": result.stdout.hex(),
                "stderr_hex": result.stderr.hex(), "status": result.status.value,
                "returncode": result.returncode, "matches_semantics": match,
                "expected_match": must_match, "passed_expectation": match == must_match,
            })
            if match != must_match:
                raise ValueError(f"{label}: {stdin!r} expected {expected!r}, got {result.stdout!r} ({result.status.value})")

        for a in range(10):
            for b in range(10):
                for ending in (b"", b"\n", b"\r\n"):
                    execute("all-digit-pairs", output / "eval_add.mb", f"(+ {a} {b})".encode() + ending, str(a+b).encode())
        for source in [b"", b"xxxxx2x", b"(- 1 2)", b"(+ a 2)", b"(+ 1 x)", b"(+ 1 2", b"(+ 12 2)", b"(+ 1 2)x", b" (+ 1 2)", b"(+ 1 2)\r"]:
            execute("malformed-frame", output / "eval_add.mb", source, b"")
        for source, expected in [(b"(+ 0 0)", b"0"), (b"(+ 1 1)\n", b"2"), (b"(+ 9 9)\r\n", b"18")]:
            execute("line-wrap-neutrality", output / "eval_add-spaced.mb", source, expected)

        # Independent native mutation controls: suppress either operand read or final output.
        labels = dict(manifest["labels"])
        for name, address in [("first-operand", labels["input_bytes"][3]), ("second-operand", labels["input_bytes"][5]), ("output", labels["decimal_output"][1])]:
            mutant = bytearray(image)
            mutant[address] = encode_dispatch_sequence(["nop"] * (address+1), profile)[address]
            path = output / ("mutant-" + name + ".mb")
            path.write_bytes(mutant)
            execute("mutant-" + name, path, b"(+ 1 1)", b"2", must_match=False)

        historical = ROOT / "evidence/h9_eval_add_v1/runs/20261019T072739Z-334da706/eval_add.mb"
        for source, expected in [(b"(+ 0 2)", b"2"), (b"(+ 1 1)", b"2"), (b"(+ 9 9)", b"18")]:
            execute("historical-v1-counterexample", historical, source, expected, must_match=False)

        for source, expected in [(b"(+ 1 1)", b"2"), (b"(+ 9 9)", b"18")]:
            result = run_model(image, source, profile, loader="canonical", max_steps=10_000_000, max_address=len(image)-1)
            record = {"stdin_hex": source.hex(), "stdout_hex": result.stdout.hex(), "status": result.status.value, "steps": result.steps}
            model_records.append(record)
            if result.status.value != "HALT" or result.stdout != expected:
                raise ValueError(f"independent transition model disagrees: {record}")
    except Exception as exc:
        failure = f"{type(exc).__name__}: {exc}"
    finally:
        with (output / "vm-raw.jsonl").open("x", encoding="utf-8") as stream:
            for record in records:
                stream.write(json.dumps(record, sort_keys=True) + "\n")
        write_json(output / "model-runs.json", model_records)
        sources = [ROOT / p for p in ["src/bolge19.zig", "slopsynth/_native_eval_add.py", "slopsynth/eval_add.py", "slopsynth/model.py", "slopsynth/ir.py", "profiles/fixed19.json", "tools/verify_h9_eval_add.py"]]
        write_json(output / "source-hashes.json", {str(p.relative_to(ROOT)): digest(p) for p in sources})
        report = {"protocol": "h9_eval_add_v2", "timestamp_utc": stamp, "platform": platform.platform(), "python": sys.version, "command": sys.argv, "cwd": str(Path.cwd()), "cells": len(image), "native_vm_sha256": digest(engine) if engine.is_file() else None, "native_runs": len(records), "passed_expectations": sum(r["passed_expectation"] for r in records), "model_runs": len(model_records), "failure": failure, "exit_status": 1 if failure else 0, "scope": "fixed (+ a b) frame, single decimal digits, optional LF/CRLF then EOF; general Lisp NOT_DEMONSTRATED"}
        write_json(output / "report.json", report)
        (output / "SHA256SUMS.txt").write_text("".join(f"{digest(p)}  {p.name}\n" for p in sorted(output.iterdir()) if p.is_file() and p.name != "SHA256SUMS.txt"), encoding="utf-8")
    print(f"H9 v2 evidence: {output}")
    if failure:
        print(failure, file=sys.stderr)
        return 1
    print(f"PASS: {len(records)} native runs, 2 independent model runs; {len(image)} canonical cells")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Seal a new H7 countdown lowering run; never overwrite a previous evidence directory."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from slopsynth.countdown import lower_countdown
from slopsynth.lang import parse_placed
from slopsynth.model import _crazy, run_model
from slopsynth.profile import load_profile
from tools.guest_runner import RunConfig, run_guest


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def require(condition: bool, detail: object) -> None:
    if not condition:
        raise ValueError(detail)


def orientation_control() -> dict:
    """T24: independently re-fill all Classic memory, without rewriting E2/E3."""
    oracle = ROOT.parent / "MALBOLGE-MB-DATABASE/tools/oracle_classic.py"
    specimen = ROOT.parent / "MALGAMES/vm/classic/pong_bounce_v0.mb"
    spec = importlib.util.spec_from_file_location("h7_orientation_oracle", oracle)
    reference = importlib.util.module_from_spec(spec)
    previous_bytecode_setting = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(reference)
    finally:
        sys.dont_write_bytecode = previous_bytecode_setting
    source = specimen.read_text(encoding="utf-8")
    expected = reference.load_memory(source)
    initial = [ord(char) for char in source if not char.isspace()]
    results = {}
    for swapped in (False, True):
        memory = initial + [0] * (59049 - len(initial))
        for i in range(len(initial), len(memory)):
            a, b = memory[i - 1], memory[i - 2]
            memory[i] = _crazy(b, a, 10) if swapped else _crazy(a, b, 10)
        results["swapped" if swapped else "correct"] = sum(
            a != b for a, b in zip(memory, expected)
        )
    require(results["correct"] == 0 and results["swapped"] > 0, results)
    return {
        "orientation": "crazy(ctrl, cell) = TABLE[cell][ctrl]",
        "memory_cells": 59049,
        "mismatches": results,
        "read_only_inputs": {str(p): digest(p) for p in (oracle, specimen)},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root", type=Path, default=ROOT / "evidence/h7_countdown_v1/runs"
    )
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_root.resolve() / (stamp + "-" + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    profile = load_profile(ROOT / "profiles/fixed19.json")
    write_json(output / "orientation.json", orientation_control())

    parsed = parse_placed((ROOT / "examples/countdown.slop").read_text(encoding="utf-8"))
    assert parsed.module is not None
    plain = lower_countdown(parsed.module, profile)
    spaced = lower_countdown(parsed.module, profile, line_width=20)
    (output / "countdown.mb").write_bytes(plain.image)
    (output / "countdown-spaced.mb").write_bytes(spaced.image)

    # Mutants remain canonical; they must break declared countdown semantics.
    # Mutant 1: corrupted discriminator seed at cell 80 (corrupts bootstrap identity mapping).
    mutant_discrim = bytearray(plain.image)
    mutant_discrim[80] = 66  # valid canonical opcode at pos 80, but invalid discriminator seed
    (output / "mutant-discrim.mb").write_bytes(mutant_discrim)

    # Mutant 2: corrupted Stage 3 move target at cell 84 (diverts Stage 3 away from data pointer).
    mutant_step = bytearray(plain.image)
    mutant_step[84] = 66  # valid canonical opcode at pos 84, but leads to D=67 instead of 50
    (output / "mutant-step.mb").write_bytes(mutant_step)

    config = RunConfig("canonical", 512, 5, 512 * 1024 * 1024, 64)
    records = []
    traces = []

    model_cases = [
        (b"\x00", b"\x00"),
        (b"\x01", b"\x01\x00"),
        (b"\x03", b"\x03\x02\x01\x00"),
    ]
    for stdin, expected in model_cases:
        observed = run_model(
            plain.image,
            stdin,
            profile,
            loader="canonical",
            max_steps=512,
            max_address=profile.end - 1,
            trace_instructions=True,
        )
        require(
            observed.status.value == "HALT" and observed.stdout == expected,
            f"model disagrees for stdin {stdin.hex()}: got {observed.stdout!r}",
        )
        traces.append({
            "stdin_hex": stdin.hex(),
            "steps": observed.steps,
            "events": [
                [e.address, e.operation, e.data_address]
                for e in observed.instruction_trace
                if e.operation in {"jump", "move", "crazy", "rotate", "input", "output", "halt"}
            ],
        })

    def execute(
        label: str,
        image: str,
        stdin: bytes,
        expected: bytes | None = None,
        must_match: bool = True,
    ) -> None:
        result = run_guest(output / image, stdin, config)
        record = {
            "label": label,
            "image": image,
            "stdin_hex": stdin.hex(),
            "stdout_hex": result.stdout.hex(),
            "stderr_hex": result.stderr.hex(),
            "returncode": result.returncode,
            "status": result.status.value,
            "expected_stdout_hex": None if expected is None else expected.hex(),
        }
        match = result.status.value == "HALT" and result.stdout == expected
        record["matches_semantics"] = match
        records.append(record)
        if expected is not None:
            require(match == must_match, record)

    failure = None
    try:
        # 1. Declared boundary cases:
        execute("declared-boundary", "countdown.mb", b"\x00", b"\x00")
        execute("declared-boundary", "countdown.mb", b"\x01", b"\x01\x00")
        execute("declared-boundary", "countdown.mb", b"\x03", b"\x03\x02\x01\x00")

        # 2. Spaced image neutrality:
        execute("spaced-neutrality", "countdown-spaced.mb", b"\x00", b"\x00")
        execute("spaced-neutrality", "countdown-spaced.mb", b"\x01", b"\x01\x00")
        execute("spaced-neutrality", "countdown-spaced.mb", b"\x03", b"\x03\x02\x01\x00")

        # 3. Repeated executions:
        for _ in range(50):
            execute("repeated-run", "countdown.mb", b"\x00", b"\x00")
            execute("repeated-run", "countdown.mb", b"\x01", b"\x01\x00")
            execute("repeated-run", "countdown.mb", b"\x03", b"\x03\x02\x01\x00")

        # 4. Negative controls:
        execute("mutant-discrim", "mutant-discrim.mb", b"\x03", b"\x03\x02\x01\x00", must_match=False)
        execute("mutant-step", "mutant-step.mb", b"\x03", b"\x03\x02\x01\x00", must_match=False)

    except Exception as exc:
        failure = str(exc)
        raise
    finally:
        with (output / "vm-raw.jsonl").open("x", encoding="utf-8") as stream:
            for record in records:
                stream.write(json.dumps(record, sort_keys=True) + "\n")
        write_json(output / "model-traces.json", traces)
        report = {
            "protocol": "h7_countdown_v1",
            "timestamp": stamp,
            "platform": platform.platform(),
            "python": sys.version,
            "compiler": plain.lowering,
            "cells": plain.cells,
            "runs_total": len(records),
            "runs_passed": sum(r["matches_semantics"] for r in records),
            "failure": failure,
            "native_vm_sha256": digest(ROOT / "build/bolge19"),
        }
        write_json(output / "report.json", report)
        manifest = [
            f"{digest(p)}  {p.name}\n"
            for p in sorted(output.iterdir())
            if p.name != "SHA256SUMS.txt"
        ]
        (output / "SHA256SUMS.txt").write_text("".join(manifest), encoding="utf-8")

    print(f"H7 verification sealed: {output} ({len(records)} native runs, all passed)")


if __name__ == "__main__":
    main()

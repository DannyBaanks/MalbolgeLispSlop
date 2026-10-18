#!/usr/bin/env python3
"""Seal a new H3 run; never overwrite a previous evidence directory."""

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

from slopsynth.loop import lower_loop
from slopsynth.encode import encode_dispatch_sequence
from slopsynth.lang import parse_placed
from slopsynth.model import _crazy, run_model
from slopsynth.profile import load_profile
from tools.guest_runner import RunConfig, run_guest


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def require(condition, detail):
    # Acceptance checks must survive python -O and PYTHONOPTIMIZE.
    if not condition:
        raise ValueError(detail)


def orientation_control():
    """T24: independently re-fill all Classic memory, without rewriting E2/E3."""
    oracle = ROOT.parent / "MALBOLGE-MB-DATABASE/tools/oracle_classic.py"
    specimen = ROOT.parent / "MALGAMES/vm/classic/pong_bounce_v0.mb"
    spec = importlib.util.spec_from_file_location("h3_orientation_oracle", oracle)
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
            a != b for a, b in zip(memory, expected))
    require(results["correct"] == 0 and results["swapped"] > 0, results)
    return {"orientation": "crazy(ctrl, cell) = TABLE[cell][ctrl]",
            "memory_cells": 59049, "mismatches": results,
            "read_only_inputs": {str(p): digest(p) for p in (oracle, specimen)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path,
                        default=ROOT / "evidence/h3_loop_v1/runs")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_root.resolve() / (stamp + "-" + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    profile = load_profile(ROOT / "profiles/fixed19.json")
    write_json(output / "orientation.json", orientation_control())
    parsed = parse_placed((ROOT / "examples/echo_loop.slop").read_text())
    plain = lower_loop(parsed.module, profile)
    spaced = lower_loop(parsed.module, profile, line_width=20)
    (output / "loop.mb").write_bytes(plain.image)
    (output / "loop-spaced.mb").write_bytes(spaced.image)

    # Mutants remain canonical; they must break declared semantics.
    for name, address in (("always-stop", 99), ("zero-falls-through", 1)):
        image = bytearray(plain.image)
        operation = "halt" if name == "always-stop" else "nop"
        image[address] = encode_dispatch_sequence(
            ["nop"] * address + [operation], profile)[address]
        (output / (name + ".mb")).write_bytes(image)

    config = RunConfig("canonical", 512, 5, 512 * 1024 * 1024, 8)
    records = []
    traces = []

    # Model traces for 0 iterations, 1 iteration, 2 iterations:
    model_cases = [
        (bytes((0,)), b""),
        (bytes((2, 65, 0)), b"A"),
        (bytes((2, 65, 2, 66, 0)), b"AB"),
        (b"", b""),
    ]
    for stdin, expected in model_cases:
        observed = run_model(plain.image, stdin, profile, loader="canonical",
                             max_steps=512, max_address=profile.end - 1,
                             trace_instructions=True)
        require(observed.status.value == "HALT" and observed.stdout == expected,
                f"model disagrees for stdin {stdin.hex()}: got {observed.stdout}")
        traces.append({"stdin_hex": stdin.hex(), "steps": observed.steps,
                       "events": [[e.address, e.operation, e.data_address]
                                  for e in observed.instruction_trace
                                  if e.operation in {"jump", "input", "output", "halt"}]})

    def execute(label, image, stdin, expected=None, must_match=True):
        result = run_guest(output / image, stdin, config)
        record = {"label": label, "image": image, "stdin_hex": stdin.hex(),
                  "stdout_hex": result.stdout.hex(), "stderr_hex": result.stderr.hex(),
                  "returncode": result.returncode, "status": result.status.value,
                  "expected_stdout_hex": None if expected is None else expected.hex()}
        match = result.status.value == "HALT" and result.stdout == expected
        record["matches_semantics"] = match
        records.append(record)
        if expected is not None:
            require(match == must_match, record)

    failure = None
    try:
        # 1. Zero input halts immediately:
        execute("zero", "loop.mb", bytes((0,)), b"")

        # 2. Exhaustive payload tests for single iteration (all 256 values):
        for payload in range(256):
            execute("single-iteration-payload", "loop.mb", bytes((2, payload, 0)), bytes((payload,)))

        # 3. Two iterations with representative payload pairs:
        two_iter_samples = [
            (ord("A"), ord("B")), (ord("0"), ord("9")), (0, 0), (255, 255),
            (10, 13), (127, 128), (42, 43), (1, 2),
        ]
        for p1, p2 in two_iter_samples:
            execute("two-iteration-sample", "loop.mb", bytes((2, p1, 2, p2, 0)), bytes((p1, p2)))

        # 4. Spacing neutrality:
        for stdin, expected in [
            (bytes((0,)), b""),
            (bytes((2, ord("A"), 0)), b"A"),
            (bytes((2, ord("A"), 2, ord("B"), 0)), b"AB"),
        ]:
            execute("spacing", "loop-spaced.mb", stdin, expected)

        # 5. Negative controls:
        execute("negative", "always-stop.mb", bytes((2, ord("A"), 0)), b"A", False)
        execute("negative", "zero-falls-through.mb", bytes((0,)), b"", False)

        # 6. EOF test:
        execute("eof", "loop.mb", b"", b"")

    except Exception as exc:
        failure = repr(exc)

    with (output / "vm-raw.jsonl").open("x") as stream:
        for record in records:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
    write_json(output / "model-traces.json", traces)

    sources = (
        "slopsynth/loop.py", "slopsynth/branch.py", "slopsynth/model.py", "slopsynth/encode.py",
        "slopsynth/canonical.py", "slopsynth/lang.py", "tools/assemble.py",
        "tools/guest_runner.py", "tools/verify_h3_loop.py", "tests/test_loop.py",
        "profiles/fixed19.json", "src/bolge19.zig", "build/bolge19", "examples/echo_loop.slop",
    )
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    write_json(output / "report.json", {
        "schema": "h3-loop-v1", "timestamp_utc": stamp,
        "base_revision": revision, "sources_sha256": {p: digest(ROOT / p) for p in sources},
        "command": [sys.executable, *sys.argv], "python": sys.version,
        "platform": platform.platform(), "config": config.__dict__ if hasattr(config, "__dict__") else
            {name: getattr(config, name) for name in config.__slots__},
        "image_cells": plain.cells, "image_sha256": digest(output / "loop.mb"),
        "actual_vm_runs": len(records), "model_traces": len(traces),
        "negative_controls": 2, "failure": failure,
        "claims": {"H3-SCOPED-LOOP": "DEMONSTRATED_SCOPED" if failure is None else "FAIL",
                   "GENERAL-BRZ": "NOT_DEMONSTRATED", "GENERAL-JUMP": "NOT_DEMONSTRATED",
                   "GENERAL-BOOTSTRAP": "NOT_DEMONSTRATED", "LISP-GUEST": "NOT_DEMONSTRATED"},
    })

    with (output / "SHA256SUMS.txt").open("x") as stream:
        for path in sorted(output.iterdir()):
            if path.name != "SHA256SUMS.txt":
                stream.write(f"{digest(path)}  {path.name}\n")

    print(f"H3 {'DEMONSTRATED_SCOPED' if failure is None else 'FAIL'}: "
          f"{plain.cells} cells, {len(records)} VM runs; {output}")
    return 0 if failure is None else 1


if __name__ == "__main__":
    raise SystemExit(main())

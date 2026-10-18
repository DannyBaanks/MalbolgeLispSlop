#!/usr/bin/env python3
"""Seal a bounded fixed19 both-arms branch run with raw VM results."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from slopsynth.branch import lower_branch
from slopsynth.encode import encode_dispatch_sequence
from slopsynth.lang import parse_placed
from slopsynth.model import run_model
from slopsynth.profile import load_profile
from tools.guest_runner import RunConfig, run_guest


def negative_control_detected(result, expected: bytes, model_result) -> bool:
    """The VM must halt and agree with the model on an incorrect mutant output."""
    return (
        model_result is not None
        and result.status.value == "HALT"
        and model_result.status.value == "HALT"
        and result.stdout == model_result.stdout
        and result.stdout != expected
    )


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes())


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def require(condition: bool, detail: object) -> None:
    # Acceptance must survive python -O.
    if not condition:
        raise ValueError(str(detail))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root", type=Path,
        default=ROOT / "evidence/both_arms_branch_v1/runs",
    )
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_root.resolve() / (stamp + "-" + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)

    profile_path = ROOT / "profiles/fixed19.json"
    source_path = ROOT / "examples/branch_both_arms.slop"
    engine_path = ROOT / "build/bolge19"
    profile = load_profile(profile_path)
    parsed = parse_placed(source_path.read_text(encoding="utf-8"))
    built = lower_branch(parsed.module, profile)
    spaced = lower_branch(parsed.module, profile, line_width=20)
    require(built.lowering == "fixed19-zero-double-read-else-echo-v1", built.lowering)
    (output / "branch.mb").write_bytes(built.image)
    (output / "branch-spaced.mb").write_bytes(spaced.image)

    mutants = {}
    for name, operation in (("zero-halts", "halt"), ("zero-skips-read", "nop")):
        image = bytearray(built.image)
        address = 1
        image[address] = encode_dispatch_sequence(
            ["nop"] * address + [operation], profile
        )[address]
        mutants[name] = bytes(image)
        (output / f"{name}.mb").write_bytes(image)

    config = RunConfig("canonical", 512, 5, 512 * 1024 * 1024, 8)
    payload_patterns = (b"", b"\x00", b"\x01", b"\xff", b"\x00\x01",
                        b"\x01\xff", b"\xff\x00")
    records: list[dict[str, object]] = []
    traces: list[dict[str, object]] = []
    landing_inputs: set[int] = set()
    failure: str | None = None

    def expected_output(stdin: bytes) -> bytes:
        index = 2 if stdin[:1] == b"\x00" else 1
        return stdin[index:index + 1] or bytes((profile.eof_value & 255,))

    def record_guest(label: str, image_name: str, image: Path, stdin: bytes,
                     expected: bytes, *, must_match: bool = True,
                     model_result=None) -> bool:
        result = run_guest(image, stdin, config, engine_path=engine_path)
        matches = result.status.value == "HALT" and result.stdout == expected
        negative_detected = negative_control_detected(result, expected, model_result)
        records.append({
            "expected_stdout_hex": expected.hex(),
            "image": image_name,
            "label": label,
            "model_status": (None if model_result is None else model_result.status.value),
            "model_stdout_hex": (None if model_result is None else model_result.stdout.hex()),
            "model_steps": (None if model_result is None else model_result.steps),
            "returncode": result.returncode,
            "status": result.status.value,
            "stderr_hex": result.stderr.hex(),
            "stdin_hex": stdin.hex(),
            "stdout_hex": result.stdout.hex(),
            "matches_semantics": matches,
            "negative_control_detected": negative_detected,
        })
        if must_match:
            require(matches, records[-1])
        else:
            require(negative_detected, records[-1])
        return matches

    try:
        for selector in range(256):
            trace_input = bytes((selector,)) + b"\x01\xff"
            trace_result = run_model(
                built.image, trace_input, profile, loader="canonical",
                max_steps=512, max_address=1024, trace_instructions=True,
            )
            require(trace_result.status.value == "HALT", (selector, trace_result.status))
            require(trace_result.stdout == expected_output(trace_input),
                    (selector, trace_result.stdout.hex()))
            input_addresses = [event.address for event in trace_result.instruction_trace
                               if event.operation == "input"]
            landing_inputs.update(address for address in input_addresses if address != 105)
            traces.append({
                "selector": selector,
                "steps": trace_result.steps,
                "input_addresses": input_addresses,
                "stdout_hex": trace_result.stdout.hex(),
            })

            for payload in payload_patterns:
                stdin = bytes((selector,)) + payload
                expected = expected_output(stdin)
                model = run_model(
                    built.image, stdin, profile, loader="canonical",
                    max_steps=512, max_address=1024,
                )
                require(model.status.value == "HALT" and model.stdout == expected,
                        {"selector": selector, "stdin_hex": stdin.hex(),
                         "model_status": model.status.value,
                         "model_stdout_hex": model.stdout.hex(),
                         "expected_stdout_hex": expected.hex()})
                record_guest("exhaustive-selector", "branch.mb", output / "branch.mb",
                             stdin, expected, model_result=model)

        require(landing_inputs == {1, 42, 96, 123, 256}, landing_inputs)
        for stdin in (b"\x00\x11\x22", b"\x01\x11\x22"):
            model = run_model(
                spaced.image, stdin, profile, loader="canonical",
                max_steps=512, max_address=1024,
            )
            require(model.status.value == "HALT" and model.stdout == expected_output(stdin),
                    ("spaced", stdin.hex(), model.status.value, model.stdout.hex()))
            record_guest("whitespace-image", "branch-spaced.mb",
                         output / "branch-spaced.mb", stdin, expected_output(stdin),
                         model_result=model)

        # The empty stream takes the nonzero arm through EOF's lazy-memory
        # trampoline. A small model address cap must not be called a halt.
        eof_model = run_model(
            built.image, b"", profile, loader="canonical", max_steps=512,
            max_address=profile.end - 1,
        )
        require(eof_model.status.value == "HALT" and eof_model.stdout == b"\xda",
                ("first-read EOF", eof_model.status.value, eof_model.stdout.hex()))
        record_guest("first-read-eof", "branch.mb", output / "branch.mb", b"",
                     b"\xda", model_result=eof_model)

        distinguishing_input = b"\x00\x41\x42"
        distinguishing_output = expected_output(distinguishing_input)
        for name, image in mutants.items():
            path = output / f"{name}.mb"
            model = run_model(
                image, distinguishing_input, profile, loader="canonical",
                max_steps=512, max_address=1024,
            )
            require(model.status.value == "HALT" and model.stdout != distinguishing_output,
                    (name, model.status.value, model.stdout.hex()))
            record_guest("negative-control", f"{name}.mb", path,
                         distinguishing_input, distinguishing_output, must_match=False,
                         model_result=model)
    except Exception as exc:
        failure = repr(exc)

    with (output / "vm-raw.jsonl").open("x", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
    write_json(output / "model-traces.json", traces)

    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
        text=True, check=True,
    ).stdout.strip()
    sources = (
        "slopsynth/branch.py", "slopsynth/model.py", "slopsynth/encode.py",
        "slopsynth/canonical.py", "slopsynth/symbolic.py", "slopsynth/lang.py",
        "tools/assemble.py", "tools/guest_runner.py",
        "tools/verify_both_arms_branch.py", "tests/test_branch.py",
        "profiles/fixed19.json", "src/bolge19.zig",
        "examples/branch_both_arms.slop",
    )
    write_json(output / "report.json", {
        "schema": "fixed19-both-arms-branch-v1",
        "timestamp_utc": stamp,
        "base_revision": revision,
        "command": [sys.executable, *sys.argv],
        "python": sys.version,
        "platform": platform.platform(),
        "source_sha256": {path: file_sha256(ROOT / path) for path in sources},
        "engine_sha256": file_sha256(engine_path),
        "profile_sha256": file_sha256(profile_path),
        "config": {name: getattr(config, name) for name in config.__slots__},
        "lowering": built.lowering,
        "image_cells": built.cells,
        "image_sha256": sha256(built.image),
        "model_selector_domain": 256,
        "model_payload_patterns_per_selector": len(payload_patterns),
        "native_vm_exhaustive_cases": 1792,
        "native_vm_additional_cases": len(records) - 1792,
        "native_vm_total_runs": len(records),
        "covered_input_landing_cells": sorted(landing_inputs),
        "negative_controls": 2,
        "failure": failure,
        "claims": {
            "FIXED19-ZERO-DOUBLE-READ-ELSE-ECHO":
                "DEMONSTRATED_SCOPED" if failure is None else "FAIL",
            "GENERAL-BRZ": "NOT_DEMONSTRATED",
            "GENERAL-CFG-COMPOSITION": "NOT_DEMONSTRATED",
            "GENERAL-MEMORY-ARITHMETIC-CALLS": "NOT_DEMONSTRATED",
            "MALBOLGELISP-GUEST": "NOT_DEMONSTRATED",
        },
    })
    with (output / "SHA256SUMS.txt").open("x", encoding="utf-8") as stream:
        for path in sorted(output.iterdir()):
            if path.name != "SHA256SUMS.txt":
                stream.write(f"{file_sha256(path)}  {path.name}\n")

    print(f"BOTH-ARMS {'DEMONSTRATED_SCOPED' if failure is None else 'FAIL'}: "
          f"{built.cells} cells, {len(records)} VM runs; {output}")
    return 0 if failure is None else 1


if __name__ == "__main__":
    raise SystemExit(main())

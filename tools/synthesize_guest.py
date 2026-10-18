#!/usr/bin/env python3
"""Synthesize a bounded guest, validate it in bolge19, and write a manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.ir import Halt, Program, ReadA, WriteA
from slopsynth.ir_json import load_program
from slopsynth.manifest import build_manifest, write_manifest
from slopsynth.profile import Profile, load_profile
from slopsynth.search import SearchBudget, SynthesisStatus, synthesize_program
from tools.guest_runner import GuestStatus, RunConfig, run_guest


def _git_revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return result.stdout.decode("ascii", errors="replace").strip() or "unknown"


def _generator_digest() -> str:
    digest = hashlib.sha256()
    for relative in (
        "slopsynth/encode.py",
        "slopsynth/search.py",
        "slopsynth/model.py",
        "slopsynth/profile.py",
        "slopsynth/ir.py",
        "slopsynth/ir_json.py",
        "slopsynth/manifest.py",
        "tools/synthesize_guest.py",
        "tools/guest_runner.py",
    ):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update((ROOT / relative).read_bytes())
    return digest.hexdigest()


def _expected_stdout(program: Program, stdin: bytes, profile: Profile) -> bytes:
    accumulator = 0
    input_position = 0
    stdout = bytearray()
    for operation in program.operations:
        if isinstance(operation, ReadA):
            if operation.destination != "A":
                raise ValueError("the direct M1 CLI supports only reads into A")
            if input_position < len(stdin):
                accumulator = stdin[input_position]
                input_position += 1
            else:
                accumulator = profile.eof_value
        elif isinstance(operation, WriteA):
            if operation.value != "A":
                raise ValueError("the direct M1 CLI supports only writes from A")
            stdout.append(accumulator & 0xFF)
        elif isinstance(operation, Halt):
            break
        else:
            raise ValueError(f"unsupported guest operation: {type(operation).__name__}")
    return bytes(stdout)


def _validation_inputs(program: Program) -> tuple[bytes, ...]:
    read_count = sum(isinstance(operation, ReadA) for operation in program.operations)
    length = max(1, read_count)
    samples = [
        bytes([value]) * length
        for value in (0x41, 0x7A, 0x00, 0xFF)
    ]
    samples.append(b"")
    return tuple(samples)


def _write_new(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(content)


def _write_guest_new(path: Path, image: bytes) -> None:
    _write_new(path, image)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("goal", type=Path, help="JSON straight-line guest program")
    parser.add_argument("--profile", type=Path, default=Path("profiles/fixed19.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--max-cells", type=int, required=True)
    parser.add_argument("--max-nodes", type=int, required=True)
    parser.add_argument("--max-steps", type=int, required=True)
    parser.add_argument("--max-address", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument("--address-space-bytes", type=int, default=536_870_912)
    parser.add_argument("--output-bytes", type=int, default=1_048_576)
    args = parser.parse_args()

    goal_path = args.goal.resolve()
    profile_path = args.profile.resolve()
    output_path = args.output.resolve()
    manifest_path = args.manifest.resolve()
    if output_path == manifest_path:
        parser.error("--output and --manifest must be different paths")
    existing = [str(path) for path in (output_path, manifest_path) if path.exists()]
    if existing:
        parser.error(f"refusing to overwrite existing path(s): {', '.join(existing)}")

    try:
        program = load_program(goal_path)
        profile = load_profile(profile_path)
        budget = SearchBudget(
            args.max_cells, args.max_nodes, args.max_steps, args.max_address
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    synthesis = synthesize_program(program, profile, budget)
    if (
        synthesis.status is not SynthesisStatus.FOUND
        or synthesis.image is None
        or synthesis.semantic_proof is None
    ):
        print(
            json.dumps(
                {
                    "status": synthesis.status.value,
                    "explored_nodes": synthesis.explored_nodes,
                    "bounds": {
                        "max_cells": budget.max_cells,
                        "max_nodes": budget.max_nodes,
                        "max_steps": budget.max_steps,
                        "max_address": budget.max_address,
                    },
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2

    run_config = RunConfig(
        loader="canonical",
        max_steps=budget.max_steps,
        timeout_seconds=args.timeout_seconds,
        address_space_bytes=args.address_space_bytes,
        output_bytes=args.output_bytes,
    )
    engine_path = ROOT / "build" / "bolge19"
    engine_sha256 = hashlib.sha256(engine_path.read_bytes()).hexdigest()
    validation_cases: list[dict[str, object]] = []
    validation_passed = True
    build_directory = ROOT / "build"
    build_directory.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="slopsynth-validate-", dir=build_directory
    ) as temporary:
        candidate_path = Path(temporary) / "candidate.mb"
        candidate_path.write_bytes(synthesis.image)
        for stdin in _validation_inputs(program):
            expected = _expected_stdout(program, stdin, profile)
            guest = run_guest(
                candidate_path,
                stdin,
                run_config,
                engine_path=engine_path,
            )
            matches = guest.status is GuestStatus.HALT and guest.stdout == expected
            validation_passed = validation_passed and matches
            validation_cases.append(
                {
                    "stdin_hex": stdin.hex(),
                    "expected_stdout_hex": expected.hex(),
                    "observed_stdout_hex": guest.stdout.hex(),
                    "guest_status": guest.status.value,
                    "returncode": guest.returncode,
                    "matches": matches,
                }
            )

    validation = {
        "status": "PASS" if validation_passed else "FAIL",
        "guest_status": "HALT" if validation_passed else "NOT_ALL_CASES_HALTED",
        "synthesis_status": synthesis.status.value,
        "semantic_proof": synthesis.semantic_proof.value,
        "cases": validation_cases,
        "loader": run_config.loader,
        "max_steps": run_config.max_steps,
        "timeout_seconds": run_config.timeout_seconds,
        "address_space_bytes": run_config.address_space_bytes,
        "output_bytes": run_config.output_bytes,
        "engine_sha256": engine_sha256,
    }
    manifest = build_manifest(
        profile_path=profile_path,
        program_path=goal_path,
        artifact=synthesis.image,
        generator_revision=_git_revision(),
        generator_sha256=_generator_digest(),
        algorithm="profile-derived-direct-lowering-v1",
        configuration={
            "loader": "canonical",
            "max_cells": budget.max_cells,
            "max_nodes": budget.max_nodes,
            "max_steps": budget.max_steps,
            "max_address": budget.max_address,
        },
        explored_nodes=synthesis.explored_nodes,
        validation=validation,
    )

    try:
        _write_guest_new(output_path, synthesis.image)
        write_manifest(manifest_path, manifest)
    except FileExistsError as exc:
        parser.error(f"refusing to overwrite existing path: {exc.filename}")

    print(
        json.dumps(
            {
                "status": synthesis.status.value,
                "artifact": str(output_path),
                "artifact_sha256": manifest["artifact_sha256"],
                "manifest": str(manifest_path),
                "semantic_proof": synthesis.semantic_proof.value,
                "validation": validation["status"],
                "guest_status": validation["guest_status"],
            },
            sort_keys=True,
        )
    )
    return 0 if validation_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

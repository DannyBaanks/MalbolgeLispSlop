#!/usr/bin/env python3
"""Run a bounded fixed-19 capability search and preserve VM evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.ir_json import load_module
from slopsynth.profile import load_profile
from slopsynth.search import SearchBudget, SynthesisStatus, compile_module


DEFAULT_MODULES = (
    "branch_zero",
    "store_load",
    "add_sub",
    "countdown",
    "call_return",
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _vm_status(returncode: int, stderr: bytes) -> tuple[str, int | None]:
    halt = re.search(rb"HALT steps=(\d+)", stderr)
    if halt:
        return "HALT", int(halt.group(1))
    max_steps = re.search(rb"MAX_STEPS (\d+)", stderr)
    if max_steps:
        return "MAX_STEPS", int(max_steps.group(1))
    if b"caracter invalido" in stderr or returncode == 2:
        return "LOAD_ERROR", None
    if returncode != 0:
        return "PROCESS_ERROR", None
    return "UNKNOWN", None


def _run_target(
    name: str,
    module_path: Path,
    profile_path: Path,
    engine_path: Path,
    budget: SearchBudget,
    run_dir: Path,
) -> dict[str, object]:
    profile = load_profile(profile_path)
    module = load_module(module_path)
    synthesis = compile_module(module, profile, budget)
    candidate = (
        synthesis.image
        or synthesis.observational_candidate
        or synthesis.last_candidate
    )
    target_dir = run_dir / name
    target_dir.mkdir()

    case_records: list[dict[str, object]] = []
    all_cases_match = candidate is not None
    candidate_path: Path | None = None
    candidate_digest: str | None = None
    if candidate is not None:
        candidate_path = target_dir / "candidate.mb"
        candidate_path.write_bytes(candidate)
        candidate_digest = _sha256(candidate)

    for index, case in enumerate(module.cases):
        case_dir = target_dir / f"case-{index:02d}"
        case_dir.mkdir()
        (case_dir / "stdin.bin").write_bytes(case.stdin)
        (case_dir / "expected.stdout").write_bytes(case.stdout)
        if candidate_path is None:
            case_records.append(
                {
                    "stdin_hex": case.stdin.hex(),
                    "expected_stdout_hex": case.stdout.hex(),
                    "expected_status": case.status,
                    "vm_status": "NOT_RUN_NO_CANDIDATE",
                    "matches": False,
                }
            )
            all_cases_match = False
            continue

        try:
            completed = subprocess.run(
                [
                    str(engine_path),
                    str(candidate_path),
                    "--loader",
                    "canonical",
                    "--max-steps",
                    str(budget.max_steps),
                ],
                input=case.stdin,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
                check=False,
            )
            stdout = completed.stdout
            stderr = completed.stderr
            returncode: int | None = completed.returncode
            status, steps = _vm_status(completed.returncode, stderr)
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or b""
            stderr = exc.stderr or b""
            returncode = None
            status, steps = "WALL_TIMEOUT", None

        (case_dir / "stdout.bin").write_bytes(stdout)
        (case_dir / "stderr.bin").write_bytes(stderr)
        matches = status == case.status and stdout == case.stdout
        all_cases_match = all_cases_match and matches
        case_records.append(
            {
                "stdin_hex": case.stdin.hex(),
                "expected_stdout_hex": case.stdout.hex(),
                "expected_status": case.status,
                "observed_stdout_hex": stdout.hex(),
                "vm_status": status,
                "steps": steps,
                "returncode": returncode,
                "matches": matches,
                "raw_stdout": f"{name}/case-{index:02d}/stdout.bin",
                "raw_stderr": f"{name}/case-{index:02d}/stderr.bin",
            }
        )

    demonstrated = (
        synthesis.status is SynthesisStatus.FOUND
        and synthesis.image is not None
        and synthesis.semantic_proof is not None
        and all_cases_match
    )
    if synthesis.image is not None and synthesis.semantic_proof is not None:
        candidate_role = "certified_candidate"
    elif synthesis.observational_candidate is not None:
        candidate_role = "unverified_observational_candidate"
    elif candidate is not None:
        candidate_role = "last_explored_candidate"
    else:
        candidate_role = "none"
    return {
        "target": name,
        "status": "DEMONSTRATED" if demonstrated else "NOT_DEMONSTRATED",
        "synthesis_status": synthesis.status.value,
        "search_method": (
            "ordered enumeration of canonical dispatch streams; I/O cases and "
            "structural trace guards filter observational candidates only"
        ),
        "bounds": {
            "max_cells": budget.max_cells,
            "max_nodes": budget.max_nodes,
            "max_steps": budget.max_steps,
            "max_address_inclusive": budget.max_address,
        },
        "explored_nodes": synthesis.explored_nodes,
        "candidate_role": candidate_role,
        "semantic_proof": (
            synthesis.semantic_proof.value
            if synthesis.semantic_proof is not None
            else None
        ),
        "candidate_path": f"{name}/candidate.mb" if candidate_path else None,
        "generated_image_sha256": candidate_digest,
        "vm_result": (
            "NOT_RUN_NO_CANDIDATE"
            if candidate is None
            else "ALL_CASES_MATCH_UNCERTIFIED"
            if all_cases_match and synthesis.semantic_proof is None
            else "ALL_CASES_MATCH_HALT"
            if all_cases_match
            else "CASES_DID_NOT_ALL_MATCH"
        ),
        "cases": case_records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=Path("profiles/fixed19.json"))
    parser.add_argument("--engine", type=Path, default=Path("build/bolge19"))
    parser.add_argument("--output-root", type=Path, default=Path("evidence/synthesis"))
    parser.add_argument("--max-cells", type=int, default=8)
    parser.add_argument("--max-nodes", type=int, default=1000)
    parser.add_argument("--max-steps", type=int, default=128)
    parser.add_argument("--max-address", type=int, default=64)
    parser.add_argument("modules", nargs="*", default=list(DEFAULT_MODULES))
    args = parser.parse_args()

    profile_path = args.profile.resolve()
    engine_path = args.engine.resolve()
    if not engine_path.is_file():
        parser.error(f"guest VM does not exist: {engine_path}; run ./tools/build.sh first")
    budget = SearchBudget(args.max_cells, args.max_nodes, args.max_steps, args.max_address)
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    run_dir = args.output_root.resolve() / f"capability-search-{run_id}"
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        run_dir.mkdir()
    except FileExistsError:
        parser.error(f"refusing to overwrite evidence run: {run_dir}")

    reports = [
        _run_target(
            name,
            ROOT / "examples" / f"{name}.json",
            profile_path,
            engine_path,
            budget,
            run_dir,
        )
        for name in args.modules
    ]
    input_paths = {
        "profile": profile_path,
        "engine": engine_path,
        "probe_tool": Path(__file__).resolve(),
        "search_backend": ROOT / "slopsynth" / "search.py",
        "encoder": ROOT / "slopsynth" / "encode.py",
        "semantic_model": ROOT / "slopsynth" / "model.py",
    }
    input_paths.update(
        {
            f"module:{name}": ROOT / "examples" / f"{name}.json"
            for name in args.modules
        }
    )
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    run_report = {
        "schema_version": 1,
        "run_id": run_id,
        "target_profile": "fixed-3^19",
        "loader": "canonical",
        "engine": str(engine_path),
        "profile": str(profile_path),
        "command": ["python3", *sys.argv],
        "seed": None,
        "repo_revision_at_run": (
            revision.stdout.decode("ascii", errors="replace").strip()
            if revision.returncode == 0
            else None
        ),
        "worktree_may_be_dirty": True,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "input_sha256": {
            label: _sha256(path.read_bytes()) for label, path in input_paths.items()
        },
        "bounds": {
            "max_cells": budget.max_cells,
            "max_nodes": budget.max_nodes,
            "max_steps": budget.max_steps,
            "max_address_inclusive": budget.max_address,
        },
        "targets": reports,
    }
    (run_dir / "report.json").write_text(
        json.dumps(run_report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    hash_rows = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            relative = path.relative_to(run_dir)
            hash_rows.append(f"{_sha256(path.read_bytes())}  {relative.as_posix()}")
    (run_dir / "SHA256SUMS.txt").write_text("\n".join(hash_rows) + "\n", encoding="utf-8")

    print(f"evidence_run={run_dir}")
    for target in reports:
        print(
            f"{target['target']}: {target['status']} "
            f"synthesis={target['synthesis_status']} "
            f"nodes={target['explored_nodes']} image_sha256={target['generated_image_sha256']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run byte-oriented LispSlop conformance tests against a fixed19 guest image."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.guest_runner import GuestResult, GuestStatus, RunConfig, run_guest


def run_matrix(
    matrix_path: Path,
    image: Path,
    evidence_root: Path,
    engine_path: Path | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Execute matrix cases against the guest image and record raw evidence."""
    if not matrix_path.is_file():
        raise FileNotFoundError(f"Matrix file not found: {matrix_path}")
    if not image.is_file():
        raise FileNotFoundError(f"Guest image not found: {image}")

    image_bytes = image.read_bytes()
    image_sha256 = hashlib.sha256(image_bytes).hexdigest()

    if run_id is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"{stamp}-{uuid.uuid4().hex[:8]}"

    run_dir = evidence_root / run_id
    if run_dir.exists():
        raise FileExistsError(f"Evidence directory already exists: {run_dir}")

    run_dir.mkdir(parents=True, exist_ok=False)

    matrix_data = json.loads(matrix_path.read_text(encoding="utf-8"))
    features = matrix_data.get("features", [])

    results: list[dict[str, Any]] = []
    total_cases = 0
    passed_cases = 0

    for feature in features:
        feat_id = feature.get("id", "unknown")
        for group_name, cases in (
            ("pos", feature.get("positive_cases", [])),
            ("neg", feature.get("negative_cases", [])),
        ):
            for idx, case in enumerate(cases):
                total_cases += 1
                case_name = case.get("name", f"case_{idx}")
                stdin_hex = case.get("stdin_hex", "")
                stdout_hex = case.get("stdout_hex", "")
                expected_status_str = case.get("status", "HALT")
                limits_dict = case.get("limits", {})

                stdin = bytes.fromhex(stdin_hex) if stdin_hex else b""
                expected_stdout = bytes.fromhex(stdout_hex) if stdout_hex else b""

                config = RunConfig(**limits_dict)

                case_dir = run_dir / feat_id / f"{group_name}_{idx}"
                case_dir.mkdir(parents=True, exist_ok=False)

                request_data = {
                    "feature_id": feat_id,
                    "case_group": group_name,
                    "case_index": idx,
                    "case_name": case_name,
                    "stdin_hex": stdin_hex,
                    "expected_stdout_hex": stdout_hex,
                    "expected_status": expected_status_str,
                    "limits": limits_dict,
                    "image_sha256": image_sha256,
                }
                (case_dir / "request.json").write_text(
                    json.dumps(request_data, indent=2, sort_keys=True), encoding="utf-8"
                )
                (case_dir / "stdin.bin").write_bytes(stdin)

                guest_result: GuestResult = run_guest(
                    image, stdin, config, engine_path=engine_path
                )

                (case_dir / "stdout.bin").write_bytes(guest_result.stdout)
                (case_dir / "stderr.bin").write_bytes(guest_result.stderr)

                observed_status = guest_result.status.value
                passed = (observed_status == expected_status_str) and (
                    guest_result.stdout == expected_stdout
                )
                if passed:
                    passed_cases += 1

                result_record = {
                    "status": observed_status,
                    "returncode": guest_result.returncode,
                    "passed": passed,
                    "stdout_sha256": hashlib.sha256(guest_result.stdout).hexdigest(),
                    "stderr_sha256": hashlib.sha256(guest_result.stderr).hexdigest(),
                    "stdout_bytes": len(guest_result.stdout),
                    "stderr_bytes": len(guest_result.stderr),
                    "image_sha256": image_sha256,
                }
                (case_dir / "result.json").write_text(
                    json.dumps(result_record, indent=2, sort_keys=True), encoding="utf-8"
                )

                results.append(
                    {
                        "feature_id": feat_id,
                        "case_name": case_name,
                        "group": group_name,
                        "index": idx,
                        "passed": passed,
                        "expected_status": expected_status_str,
                        "observed_status": observed_status,
                        "stdout_match": guest_result.stdout == expected_stdout,
                    }
                )

    summary = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "image_sha256": image_sha256,
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "failed_cases": total_cases - passed_cases,
        "results": results,
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, required=True, help="Path to matrix JSON")
    parser.add_argument("--image", type=Path, required=True, help="Path to guest image .mb")
    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=ROOT / "evidence/lisp_conformance",
        help="Root directory for sealed evidence",
    )
    parser.add_argument("--engine", type=Path, default=None, help="Custom engine executable")
    parser.add_argument("--run-id", type=str, default=None, help="Explicit unique run ID")
    args = parser.parse_args(argv)

    try:
        report = run_matrix(
            args.matrix,
            args.image,
            args.evidence_root,
            engine_path=args.engine,
            run_id=args.run_id,
        )
        print(f"Conformance run completed: {report['run_id']}")
        print(
            f"  Total: {report['total_cases']}, Passed: {report['passed_cases']}, Failed: {report['failed_cases']}"
        )
        print(f"  Evidence: {report['run_dir']}")
        return 0 if report["failed_cases"] == 0 else 1
    except Exception as exc:
        print(f"Conformance runner error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

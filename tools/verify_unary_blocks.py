#!/usr/bin/env python3
"""Build immutable certificates and replay reusable native OPR/ROT controls."""
from dataclasses import asdict
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from slopsynth.profile import load_profile
from slopsynth.proofs import Z3_VERSION
from slopsynth.model import _crazy, _rotate
from slopsynth.unary_blocks import (make_certificate, raw_two_call_probe,
                                    replay_certificate, synthesize_unary)
from tools.guest_runner import RunConfig, run_guest
from tools.probe_language_contract import sha256_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "evidence/unary_blocks_v1/runs")
    parser.add_argument("--placement-timeout-ms", type=int, default=5000)
    parser.add_argument("--placement-resource-limit", type=int, default=100000)
    parser.add_argument("--placement-max-queries", type=int, default=100)
    parser.add_argument("--proof-timeout-ms", type=int, default=5000)
    parser.add_argument("--proof-resource-limit", type=int, default=1000000)
    args = parser.parse_args()
    out = args.output_root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                              + "-" + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    profile_path = ROOT / "profiles/fixed19.json"
    profile = load_profile(profile_path)
    cases = []
    blocks = {}
    for operation in ("crazy", "rotate"):
        search = synthesize_unary(
            operation, profile, timeout_ms=args.placement_timeout_ms,
            resource_limit=args.placement_resource_limit,
            max_queries=args.placement_max_queries)
        if search.status != "FOUND":
            cases.append({"operation": operation, "status": search.status,
                          "reason": search.reason, "queries": search.queries})
            continue
        certificate = make_certificate(
            search, profile, data_address=500, exit_address=700,
            proof_timeout_ms=args.proof_timeout_ms,
            proof_resource_limit=args.proof_resource_limit)
        replay = replay_certificate(certificate, profile)
        certificate_path = out / f"{operation}.certificate.json"
        certificate_path.write_text(json.dumps(certificate, sort_keys=True, indent=2) + "\n")
        blocks[operation] = search.block
        cases.append({"operation": operation, "status": replay["status"],
                      "entry": search.block.entry, "code_hex": search.block.code.hex(),
                      "placement_queries": search.queries,
                      "placement_statuses": [step.status for step in search.transcript],
                      "proof_status": certificate["proof"]["status"],
                      "certificate": certificate_path.name,
                      "certificate_sha256": sha256_file(certificate_path)})

    native_dir = out / "native_vm"
    native_dir.mkdir()
    native_config = RunConfig("raw", 32, 5, 536870912, 8)
    native_cases = []

    def save_request(run_id, operation, image_path, stdin, expected_hex, **details):
        request = {
            "schema_version": 1, "purpose": "native VM evidence for a reusable unary block",
            "run_id": run_id, "operation": operation, **details,
            "image_sha256": sha256_file(image_path), "vm_sha256": sha256_file(ROOT / "build/bolge19"),
            "vm_source_sha256": sha256_file(ROOT / "src/bolge19.zig"),
            "profile_sha256": sha256_file(profile_path), "stdin_hex": stdin.hex(),
            "expected_stdout_hex": expected_hex, "config": asdict(native_config),
            "exact_command": [str(ROOT / "build/bolge19"), str(image_path),
                              "--loader", native_config.loader,
                              "--max-steps", str(native_config.max_steps)],
        }
        path = native_dir / f"{run_id}.request.json"
        path.write_text(json.dumps(request, indent=2) + "\n")
        return path.name

    for operation, block in blocks.items():
        for case_index, (first, second, initial_a) in enumerate(
                (first, second, initial_a)
                for first, second in ((0, 0), (82, 112), (255, 141))
                for initial_a in (0, 1, 127, 243, 255)):
            run_id = f"{operation}-{case_index:02d}"
            image = raw_two_call_probe(block, first, second)
            image_path = native_dir / f"{run_id}.mb"
            image_path.write_bytes(image)
            stdin = bytes((initial_a,))
            result = run_guest(image_path, stdin, native_config)
            if operation == "crazy":
                first_value = _crazy(initial_a, first, profile.trits)
                final_value = _crazy(first_value, second, profile.trits)
            else:
                first_value = _rotate(first, profile.end)
                final_value = _rotate(second, profile.end)
            expected = bytes((first_value & 255, final_value & 255))
            request_name = save_request(run_id, operation, image_path, stdin, expected.hex(),
                                        first_data=first, second_data=second,
                                        initial_a=initial_a)
            stdout_path, stderr_path = native_dir / f"{run_id}.stdout", native_dir / f"{run_id}.stderr"
            stdin_path, result_path = native_dir / f"{run_id}.stdin", native_dir / f"{run_id}.result.json"
            stdout_path.write_bytes(result.stdout)
            stderr_path.write_bytes(result.stderr)
            stdin_path.write_bytes(stdin)
            observed = {"status": result.status.value, "returncode": result.returncode,
                        "stdout_hex": result.stdout.hex(), "expected_stdout_hex": expected.hex(),
                        "steps_marker": "HALT steps=12 " in result.stderr.decode("utf-8", "replace")}
            result_path.write_text(json.dumps(observed, indent=2) + "\n")
            accepted = (result.status.value == "HALT" and result.stdout == expected
                        and observed["steps_marker"])
            native_cases.append({"id": run_id, "operation": operation,
                                 "input_hex": stdin.hex(), "first_data": first,
                                 "second_data": second, **observed,
                                 "request": request_name, "passed": accepted})

    negative_cases = []
    for operation, block in blocks.items():
        run_id = f"mutated-{operation}"
        image = bytearray(raw_two_call_probe(block, 82, 112))
        image[block.entry] ^= 1
        image_path = native_dir / f"{run_id}.mb"
        image_path.write_bytes(image)
        stdin = b"\x7f"
        result = run_guest(image_path, stdin, native_config)
        first_value = (_crazy(127, 82, profile.trits) if operation == "crazy"
                       else _rotate(82, profile.end))
        final_value = (_crazy(first_value, 112, profile.trits) if operation == "crazy"
                       else _rotate(112, profile.end))
        expected = (first_value & 255, final_value & 255)
        request_name = save_request(run_id, operation, image_path, stdin,
                                    bytes(expected).hex(), mutated_byte_address=block.entry,
                                    mutation="xor 1")
        stdout_path, stderr_path = native_dir / f"{run_id}.stdout", native_dir / f"{run_id}.stderr"
        stdin_path, result_path = native_dir / f"{run_id}.stdin", native_dir / f"{run_id}.result.json"
        stdout_path.write_bytes(result.stdout)
        stderr_path.write_bytes(result.stderr)
        stdin_path.write_bytes(stdin)
        changed = (result.status.value, result.stdout) != ("HALT", bytes(expected))
        observed = {"status": result.status.value, "returncode": result.returncode,
                    "stdout_hex": result.stdout.hex(), "reference_stdout_hex": bytes(expected).hex(),
                    "negative_control_changed": changed}
        result_path.write_text(json.dumps(observed, indent=2) + "\n")
        negative_cases.append({"id": run_id, "operation": operation, **observed,
                               "request": request_name})

    sources = [Path(__file__), ROOT / "slopsynth/unary_blocks.py",
               ROOT / "slopsynth/symbolic.py", ROOT / "slopsynth/proofs.py",
               ROOT / "slopsynth/model.py", ROOT / "slopsynth/profile.py",
               ROOT / "tools/guest_runner.py", ROOT / "tests/test_unary_blocks.py",
               ROOT / "tests/test_proofs.py", ROOT / "src/bolge19.zig",
               ROOT / "build/bolge19", profile_path, ROOT / "requirements-dev.txt"]
    source_hashes = {str(path.relative_to(ROOT)): sha256_file(path) for path in sources}
    runs = []
    for label, flags in (("normal", []), ("optimized", ["-O"])):
        command = [sys.executable, *flags, "-m", "unittest",
                   "tests.test_unary_blocks", "tests.test_proofs", "-q"]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=120)
        (out / f"{label}.stdout").write_bytes(result.stdout)
        (out / f"{label}.stderr").write_bytes(result.stderr)
        runs.append({"label": label, "command": command, "returncode": result.returncode})
    source_drift = [str(path.relative_to(ROOT)) for path in sources
                    if sha256_file(path) != source_hashes[str(path.relative_to(ROOT))]]
    accepted = (not source_drift and len(cases) == 2 and len(native_cases) == 30
                and all(case["passed"] for case in native_cases)
                and len(negative_cases) == 2
                and all(case["negative_control_changed"] for case in negative_cases)
                and all(case.get("status") == "VERIFIED_BLOCK"
                        and case.get("proof_status") == "VERIFIED" for case in cases)
                and all(run["returncode"] == 0 for run in runs))
    report = {
        "schema_version": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(), "z3_version": Z3_VERSION,
        "status": "REUSABLE_BLOCKS_DEMONSTRATED" if accepted else "FAILED",
        "scope": "preinstalled code/data/pad unary crazy/rotate blocks, exact all-memory-frame proof and two-call native VM controls",
        "limits": {"placement_timeout_ms": args.placement_timeout_ms,
                   "placement_resource_limit": args.placement_resource_limit,
                   "placement_max_queries": args.placement_max_queries,
                   "proof_timeout_ms": args.proof_timeout_ms,
                   "proof_resource_limit": args.proof_resource_limit},
        "blocks": cases, "runs": runs, "sources": source_hashes,
        "native_vm_runs": native_cases, "negative_controls": negative_cases,
        "source_drift": source_drift,
        "not_demonstrated": ["bootstrap", "general control-flow compiler",
                             "general arithmetic/memory/call blocks", "guest Lisp"],
    }
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    from tools.probe_language_contract import sha256_file as digest
    (out / "hashes.json").write_text(json.dumps({
        str(path.relative_to(out)): digest(path) for path in sorted(out.rglob("*"))
        if path.is_file() and path.name != "hashes.json"
    }, indent=2) + "\n")
    print(report["status"] + ": " + str(out))
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())

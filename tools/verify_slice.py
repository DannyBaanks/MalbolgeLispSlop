#!/usr/bin/env python3
"""Bounded, byte-oriented conformance checks for the fixed-3^19 M1 slice."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime
import hashlib
import json
import platform
import resource
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "build" / "bolge19"
ADDRESS_SPACE_LIMIT = 512 * 1024 * 1024
FILE_SIZE_LIMIT = 4 * 1024 * 1024
CPU_LIMIT_SECONDS = 2


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def set_child_limits(address_space_limit: int = ADDRESS_SPACE_LIMIT) -> None:
    resource.setrlimit(resource.RLIMIT_AS, (address_space_limit, address_space_limit))
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT_SECONDS, CPU_LIMIT_SECONDS))
    resource.setrlimit(resource.RLIMIT_FSIZE, (FILE_SIZE_LIMIT, FILE_SIZE_LIMIT))


def summarize_case(
    name: str,
    image: bytes,
    stdin: bytes,
    loader: str,
    max_steps: int | None = None,
    timeout_seconds: float = 2.0,
    address_space_bytes: int = ADDRESS_SPACE_LIMIT,
) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="malbolgelispslop-") as temporary:
        image_path = Path(temporary) / "guest.mb"
        image_path.write_bytes(image)
        command = [str(ENGINE), str(image_path), "--loader", loader]
        if max_steps is not None:
            command.extend(["--max-steps", str(max_steps)])

        try:
            completed = subprocess.run(
                command,
                input=stdin,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds,
                check=False,
                preexec_fn=lambda: set_child_limits(address_space_bytes),
            )
            stdout = completed.stdout
            stderr = completed.stderr
            returncode = completed.returncode
            status = "HALT" if b"HALT steps=" in stderr else (
                "MAX_STEPS" if b"MAX_STEPS" in stderr else (
                    "MEMORY_ERROR" if b"oom" in stderr.lower() else "EXIT"
                )
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or b""
            stderr = exc.stderr or b""
            returncode = None
            status = "WALL_TIMEOUT"

    return {
        "name": name,
        "loader": loader,
        "max_steps": max_steps,
        "wall_timeout_seconds": timeout_seconds,
        "address_space_limit_bytes": address_space_bytes,
        "image_bytes": len(image),
        "image_sha256": sha256(image),
        "stdin_bytes": len(stdin),
        "stdin_sha256": sha256(stdin),
        "stdout_bytes": len(stdout),
        "stdout_sha256": sha256(stdout),
        "stdout_base64": base64.b64encode(stdout).decode("ascii"),
        "stderr_sha256": sha256(stderr),
        "stderr_base64": base64.b64encode(stderr).decode("ascii"),
        "returncode": returncode,
        "status": status,
    }


def check(name: str, result: dict[str, object], predicate: bool) -> bool:
    outcome = "PASS" if predicate else "FAIL"
    print(f"{outcome} {name}: status={result['status']} rc={result['returncode']} "
          f"stdout_sha256={result['stdout_sha256']}")
    return predicate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, help="write a JSON evidence report; refuses to overwrite")
    args = parser.parse_args()

    if not ENGINE.is_file():
        parser.error("build/bolge19 is missing; run ./tools/build.sh first")

    engine_bytes = ENGINE.read_bytes()
    echo = (ROOT / "fixtures" / "echo.mb").read_bytes()
    checks: list[bool] = []
    cases: list[dict[str, object]] = []

    def run(*args: object, **kwargs: object) -> dict[str, object]:
        result = summarize_case(*args, **kwargs)  # type: ignore[arg-type]
        cases.append(result)
        return result

    for label, value in [("A", b"A"), ("z", b"z"), ("nul", b"\x00"), ("ff", b"\xff")]:
        result = run(f"binary_echo_{label}", echo, value, "canonical")
        checks.append(check(f"binary echo {label}", result,
                            result["status"] == "HALT" and result["stdout_base64"] == base64.b64encode(value).decode("ascii")))

    repeat = run("deterministic_repeat_A", echo, b"A", "canonical")
    first_a = next(case for case in cases if case["name"] == "binary_echo_A")
    checks.append(check("deterministic repeat", repeat,
                        repeat["status"] == "HALT" and repeat["stdout_sha256"] == first_a["stdout_sha256"]))

    halt = run("clean_halt", echo, b"Q", "canonical")
    checks.append(check("clean halt in two guest steps", halt,
                        halt["status"] == "HALT" and b"HALT steps=2" in base64.b64decode(halt["stderr_base64"])))

    invalid = run("canonical_loader_rejects_invalid", b"!", b"", "canonical")
    checks.append(check("canonical loader error", invalid,
                        invalid["status"] == "EXIT" and invalid["returncode"] == 2 and
                        b"caracter invalido" in base64.b64decode(invalid["stderr_base64"])))

    spaced = b"u bO"
    canonical = run("canonical_loader_skips_whitespace", spaced, b"x", "canonical")
    raw = run("raw_loader_counts_whitespace", spaced, b"x", "raw", max_steps=4)
    checks.append(check("loader conventions diverge", raw,
                        canonical["status"] == "HALT" and canonical["stdout_base64"] == base64.b64encode(b"x").decode("ascii") and
                        raw["status"] == "MAX_STEPS" and raw["stdout_bytes"] == 0))

    limited = run("guest_step_limit", echo, b"A", "canonical", max_steps=1)
    checks.append(check("guest step limit", limited,
                        limited["status"] == "MAX_STEPS" and limited["stdout_bytes"] == 0))

    mutated = run("guest_mutation_b_to_C", b"uCO", b"A", "canonical")
    checks.append(check("guest mutation changes output", mutated,
                        mutated["status"] == "HALT" and mutated["stdout_bytes"] == 0 and
                        mutated["stdout_sha256"] != first_a["stdout_sha256"]))

    memory_pressure_image = b"!" * (16 * 1024 * 1024)
    memory_error = run("loader_memory_allocation_limit", memory_pressure_image, b"", "canonical",
                       timeout_seconds=2.0, address_space_bytes=64 * 1024 * 1024)
    checks.append(check("memory allocation limit", memory_error,
                        memory_error["status"] == "MEMORY_ERROR" and memory_error["returncode"] != 0))

    deadline = run("supervisor_wall_timeout_self_check", echo, b"A", "canonical", timeout_seconds=0.0)
    checks.append(check("supervisor wall-timeout path", deadline, deadline["status"] == "WALL_TIMEOUT"))

    report = {
        "profile": "fixed-3^19 bolge19 forensic runtime",
        "runtime_sha256": sha256(engine_bytes),
        "runtime_bytes": len(engine_bytes),
        "runtime_source_sha256": sha256((ROOT / "src" / "bolge19.zig").read_bytes()),
        "fixture_sha256": sha256(echo),
        "captured_at_local": datetime.now().astimezone().isoformat(timespec="seconds"),
        "host_platform": platform.platform(),
        "python_version": sys.version,
        "zig_version": subprocess.check_output(["zig", "version"], text=True).strip(),
        "build_command": "./tools/build.sh",
        "verify_command": "python3 tools/verify_slice.py --output <new-evidence-path>",
        "suite_exit_status": 0 if all(checks) else 1,
        "limits": {
            "address_space_bytes": ADDRESS_SPACE_LIMIT,
            "cpu_seconds": CPU_LIMIT_SECONDS,
            "output_file_bytes": FILE_SIZE_LIMIT,
        },
        "claim_limit": "This suite does not demonstrate original-Unshackled parity, Lisp evaluation, an infinite guest, an independent backend, or a quine.",
        "controls": [
            "four distinct byte inputs, including NUL and 0xff",
            "repeat of the A input to compare deterministic output digest",
            "valid guest mutation from output opcode to no-op opcode",
            "same whitespace-bearing tape under canonical and raw loaders",
            "step-limited valid guest and immediate supervisor deadline self-check",
        ],
        "checks_passed": sum(checks),
        "checks_total": len(checks),
        "cases": cases,
    }

    if args.output:
        output_path = args.output if args.output.is_absolute() else ROOT / args.output
        if output_path.exists():
            parser.error(f"refusing to overwrite existing evidence: {output_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"evidence: {output_path.relative_to(ROOT) if output_path.is_relative_to(ROOT) else output_path}")

    print(f"SUMMARY {report['checks_passed']}/{report['checks_total']} checks")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())

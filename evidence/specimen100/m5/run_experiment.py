#!/usr/bin/env python3
"""Capture immutable raw outputs for the preregistered M5 eligibility test."""
import datetime
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SPECIMEN = "/tmp/opencode/specimen100-m1-lisp.mb"
MODEL = "/tmp/opencode/m4/model_v1.m4g"


def digest(b):
    return hashlib.sha256(b).hexdigest()


def main():
    outputs = [HERE / f"{name}.{ext}" for name in ("gate_run1", "gate_run2", "g_check")
               for ext in ("stdout.json", "stderr.bin")]
    outputs.append(HERE / "execution.json")
    if any(p.exists() for p in outputs):
        raise SystemExit("Refusing reuse of evidence output paths")
    gate = [sys.executable, str(HERE / "suffix_gate.py"),
            "--specimen", SPECIMEN, "--model", MODEL]
    check = [sys.executable, "tools/specimen100/generate.py", "check",
             "--specimen", SPECIMEN, "--model", MODEL]
    runs = []
    results = {}
    for name, command in [("gate_run1", gate), ("gate_run2", gate), ("g_check", check)]:
        cp = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=120)
        (HERE / f"{name}.stdout.json").write_bytes(cp.stdout)
        (HERE / f"{name}.stderr.bin").write_bytes(cp.stderr)
        runs.append({"name": name, "command": command, "cwd": str(ROOT),
                     "exit": cp.returncode, "stdout_sha256": digest(cp.stdout),
                     "stderr_sha256": digest(cp.stderr)})
        assert cp.returncode == 0, runs[-1]
        results[name] = json.loads(cp.stdout)
    equal = (HERE / "gate_run1.stdout.json").read_bytes() == (HERE / "gate_run2.stdout.json").read_bytes()
    g, c = results["gate_run1"], results["g_check"]
    assert equal
    assert g["covered_bytes"] == c["covered_bytes"]
    assert g["gap_count"] == c["deviation_spans"]
    assert g["first_gap"][0] == c["first_deviation"]
    assert c["covered_mismatches"] == 0
    assert c["byte_exact"] is False  # partial artifact, not a successful full regeneration
    out = {"schema": "specimen100.m5.execution.v1",
           "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "python": sys.version, "platform": platform.platform(),
           "runs": runs, "gate_outputs_bit_identical": equal,
           "independent_interval_union_matches_g_check": True,
           "behavioral_runs_executed": 0,
           "strict_m5_acceptance": "NOT_MET_PRECONDITION",
           "milestone_status": "PARTIAL",
           "verdict": g["verdict"]}
    (HERE / "execution.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()

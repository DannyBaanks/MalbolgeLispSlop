#!/usr/bin/env python3
"""Seal a fresh model-conformance run, including the T24 negative control."""
from datetime import datetime, timezone
import argparse
import importlib.util
import json
from pathlib import Path
import platform
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from slopsynth.model import _crazy
from slopsynth.proofs import Z3_VERSION
from tools.probe_language_contract import sha256_file


def orientation_control(source_root):
    oracle = source_root / "MALBOLGE-MB-DATABASE/tools/oracle_classic.py"
    specimen = source_root / "MALGAMES/vm/classic/pong_bounce_v0.mb"
    spec = importlib.util.spec_from_file_location("symbolic_orientation_oracle", oracle)
    reference = importlib.util.module_from_spec(spec)
    old = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(reference)
    finally:
        sys.dont_write_bytecode = old
    text = specimen.read_text()
    expected = reference.load_memory(text)
    loaded = [ord(char) for char in text if not char.isspace()]
    mismatches = {}
    for swapped in (False, True):
        memory = loaded + [0] * (59049 - len(loaded))
        for i in range(len(loaded), 59049):
            control, cell = memory[i - 1], memory[i - 2]
            memory[i] = _crazy(cell, control, 10) if swapped else _crazy(control, cell, 10)
        mismatches["swapped" if swapped else "correct"] = sum(a != b for a, b in zip(memory, expected))
    return {"memory_cells": len(expected), "mismatches": mismatches,
            "read_only_inputs": {str(p): sha256_file(p) for p in (oracle, specimen)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True, help="ISyCo Git sibling source directory")
    parser.add_argument("--output-root", type=Path, default=ROOT / "evidence/symbolic_model_v1/runs")
    args = parser.parse_args()
    out = args.output_root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    orientation = orientation_control(args.source_root)
    (out / "orientation.json").write_text(json.dumps(orientation, indent=2) + "\n")
    sources = [Path(__file__), ROOT / "slopsynth/symbolic.py", ROOT / "slopsynth/proofs.py",
               ROOT / "slopsynth/model.py", ROOT / "slopsynth/canonical.py", ROOT / "slopsynth/profile.py",
               ROOT / "tests/test_symbolic.py", ROOT / "tests/test_proofs.py", ROOT / "src/bolge19.zig",
               ROOT / "build/bolge19", ROOT / "profiles/fixed19.json", ROOT / "requirements-dev.txt"]
    source_hashes = {str(p.relative_to(ROOT)): sha256_file(p) for p in sources}
    runs = []
    for label, flags in (("normal", []), ("optimized", ["-O"])):
        command = [sys.executable, *flags, "-m", "unittest", "tests.test_symbolic", "tests.test_proofs", "-q"]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=120)
        (out / (label + ".stdout")).write_bytes(result.stdout)
        (out / (label + ".stderr")).write_bytes(result.stderr)
        runs.append({"command": command, "returncode": result.returncode, "label": label})
    source_drift = [str(p.relative_to(ROOT)) for p in sources
                    if sha256_file(p) != source_hashes[str(p.relative_to(ROOT))]]
    accepted = (not source_drift and orientation["mismatches"]["correct"] == 0
                and orientation["mismatches"]["swapped"] > 0
                and all(run["returncode"] == 0 for run in runs))
    report = {"schema_version": 1, "timestamp": datetime.now(timezone.utc).isoformat(),
              "platform": platform.platform(), "z3_version": Z3_VERSION,
              "status": "MODEL_CONFORMANCE_DEMONSTRATED" if accepted else "FAILED",
              "scope": "bounded differential model tests, not a proof of the VM implementation",
              "not_demonstrated": ["general compiler", "bootstrap", "guest Lisp"],
              "runs": runs, "sources": source_hashes, "source_drift": source_drift}
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    (out / "hashes.json").write_text(json.dumps({p.name: sha256_file(p) for p in sorted(out.iterdir())
                                              if p.is_file()}, indent=2) + "\n")
    print(report["status"] + ": " + str(out))
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Gate L1: does the vendored fixed-3^19 VM load and run an opcode-aligned-text
image produced by the HeLL/LMFAO line, identically to the canonical engine?

Three legs per input, five inputs:
  canonical  our bolge19 --loader canonical   (the candidate)
  raw        our bolge19 --loader raw         (negative control, default path)
  unshackled upstream canonical Unshackled VM (independent backend)

Every external specimen is re-hashed before use and the run aborts as DRIFTED
rather than produce a number against a moved input.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"

SPECIMEN_DIR = Path(
    os.environ.get(
        "EXT_SPECIMEN_DIR",
        "/home/danny/Development/ISyCo Git/MALDOOM/evidence/M0_KILLER_UNSHACKLED_V0",
    )
)
UNSHACKLED = Path(
    os.environ.get(
        "UNSHACKLED_VM", "/home/danny/Development/ISyCo Git/MALDOOM/vendor/Unshackled"
    )
)
VM = REPO / "build" / "bolge19"
ARTIFACT = SPECIMEN_DIR / "artifact.mu"
SOURCE = REPO / "src" / "bolge19.zig"

# Pinned at probe design time. A mismatch is a drift, not a result.
PINS = {
    "artifact.mu": "3b9bdf37eb708ec751d10f0dea32edde4375e526ce56fd2dd440f5a22819ba10",
    "src/bolge19.zig": "47758a3f667f4089f6029d86130b94f14f082d4c113a212b8ff571d84113e8a3",
}

INPUTS = {  # input byte -> sealed expected stdout, from run.json 2n+1
    "0": b"1\n",
    "1": b"3\n",
    "2": b"5\n",
    "3": b"7\n",
    "4": b"9\n",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(cmd: list[str], stdin: bytes) -> dict:
    p = subprocess.run(cmd, input=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return {
        "command": cmd,
        "exit": p.returncode,
        "stdout": p.stdout,
        "stderr": p.stderr,
        "stdout_sha256": hashlib.sha256(p.stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(p.stderr).hexdigest(),
    }


def main() -> int:
    for label, path in (("artifact.mu", ARTIFACT), ("src", SOURCE)):
        if not path.is_file():
            print(f"DRIFTED: {label} missing at {path}", file=sys.stderr)
            return 2
        if sha(path) != PINS[label if label != "src" else "src/bolge19.zig"]:
            print(f"DRIFTED: {label} hash moved; refusing to measure", file=sys.stderr)
            return 2
    if not VM.is_file() or not UNSHACKLED.is_file():
        print("DRIFTED: a required executable is missing", file=sys.stderr)
        return 2

    RAW.mkdir(parents=True, exist_ok=True)
    legs = {
        "canonical": [str(VM), str(ARTIFACT), "--loader", "canonical"],
        "raw": [str(VM), str(ARTIFACT), "--loader", "raw"],
        "unshackled": [str(UNSHACKLED), str(ARTIFACT)],
    }
    results: dict[str, dict] = {}
    for n, expected in INPUTS.items():
        case: dict[str, dict] = {"expected": expected.decode()}
        for leg, cmd in legs.items():
            r = run(cmd, (n + "\n").encode())
            out = r.pop("stdout")
            err = r.pop("stderr")
            (RAW / f"{leg}_{n}.out").write_bytes(out)
            (RAW / f"{leg}_{n}.err").write_bytes(err)
            sealed = SPECIMEN_DIR / f"observed_{n}.bin"
            r["match_expected"] = out == expected
            r["match_sealed_observed"] = out == sealed.read_bytes()
            r["stderr_tail"] = err.decode(errors="replace").strip().splitlines()[-1:]
            case[leg] = r
        results[n] = case

    canon_ok = all(results[n]["canonical"]["match_sealed_observed"] for n in INPUTS)
    raw_ok = all(results[n]["raw"]["match_sealed_observed"] for n in INPUTS)
    unsh_ok = all(results[n]["unshackled"]["match_sealed_observed"] for n in INPUTS)
    agree = all(
        results[n]["canonical"]["stdout_sha256"] == results[n]["unshackled"]["stdout_sha256"]
        for n in INPUTS
    )
    raw_deterministic = len({results[n]["raw"]["stdout_sha256"] for n in INPUTS}) == 1

    execution = {
        "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "question": (
            "Can the vendored fixed-3^19 VM load an opcode-aligned-text image from the "
            "HeLL/LMFAO line through --loader canonical and reproduce the canonical engine?"
        ),
        "environment": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "zig": subprocess.run(["zig", "version"], capture_output=True, text=True).stdout.strip(),
            "cwd": str(REPO),
        },
        "pins": {
            "artifact.mu": PINS["artifact.mu"],
            "src/bolge19.zig": PINS["src/bolge19.zig"],
            "vm_binary_built": sha(VM),
            "unshackled_binary": sha(UNSHACKLED),
        },
        "inputs": {n: (n + "\n").encode().decode() for n in INPUTS},
        "results": results,
        "verdicts": {
            "canonical_matches_sealed_5_of_5": canon_ok,
            "unshackled_matches_sealed_5_of_5": unsh_ok,
            "canonical_agrees_with_unshackled": agree,
            "raw_control_matches_sealed": raw_ok,
            "raw_control_identical_garbage_across_inputs": raw_deterministic,
        },
        "external_specimens_not_redistributed": {
            "artifact.mu": str(ARTIFACT),
            "observed_n_bin_oracles": str(SPECIMEN_DIR),
            "unshackled_vm": str(UNSHACKLED),
        },
    }
    (HERE / "execution.json").write_text(
        json.dumps(execution, indent=1, ensure_ascii=False) + "\n"
    )
    print(json.dumps(execution["verdicts"], indent=1))
    return 0 if (canon_ok and unsh_ok and agree and not raw_ok) else 1


if __name__ == "__main__":
    sys.exit(main())

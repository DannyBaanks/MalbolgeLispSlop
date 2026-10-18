#!/usr/bin/env python3
"""Verify one fixed-3^19 quine candidate byte-for-byte in the guest VM."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quine.evidence import load_contract
from quine.search import load_budget
from quine.verify import verify_candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--budget", type=Path, required=True)
    args = parser.parse_args()

    try:
        contract = load_contract(args.contract.resolve())
        budget = load_budget(args.budget.resolve())
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    try:
        report = verify_candidate(args.candidate, contract, budget)
    except ValueError as exc:
        print(f"verification failed: {exc}", file=sys.stderr)
        return 1

    sys.stdout.buffer.write(report.to_bytes())
    return 0 if report.status == "DEMONSTRATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())

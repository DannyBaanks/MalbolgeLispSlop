#!/usr/bin/env python3
"""Run a bounded search for a guest-native fixed-3^19 Malbolge quine."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quine.evidence import load_contract
from quine.search import QuineSearchBudget, load_budget, search


def _append_index(output_root: Path, run_dir: Path) -> None:
    report_path = run_dir / "report.json"
    manifest_path = run_dir / "search-manifest.json"
    entry = {
        "run_id": run_dir.name,
        "report_path": report_path.relative_to(output_root).as_posix(),
        "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        "search_manifest_path": manifest_path.relative_to(output_root).as_posix(),
        "search_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    }
    index_path = output_root / "index.jsonl"
    with index_path.open("ab") as stream:
        stream.write(
            (json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n").encode(
                "utf-8"
            )
        )
        stream.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--budget", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    try:
        contract = load_contract(args.contract.resolve())
        budget: QuineSearchBudget = load_budget(args.budget.resolve())
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base_name = f"{timestamp}-seed-{budget.seed}"
    suffix = 0
    while True:
        run_name = base_name if suffix == 0 else f"{base_name}-{suffix:03d}"
        run_dir = output_root / run_name
        try:
            report = search(contract, budget, run_dir)
            break
        except FileExistsError:
            suffix += 1

    _append_index(output_root, run_dir)
    sys.stdout.buffer.write(report.to_bytes())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

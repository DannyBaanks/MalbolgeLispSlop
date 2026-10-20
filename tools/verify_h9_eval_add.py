#!/usr/bin/env python3
"""Refuse H9 certification while native addition remains NOT_DEMONSTRATED.

Historical evidence is preserved; see docs/H9_CORRECTION.md.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from guest_ir.lisp.evaluator import build_eval_add_module
from slopsynth.assemble import AssemblyError
from slopsynth.eval_add import lower_eval_add
from slopsynth.profile import load_profile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "evidence/h9_eval_add_v1/runs")
    parser.parse_args()
    try:
        lower_eval_add(build_eval_add_module(), load_profile(ROOT / "profiles/fixed19.json"))
    except AssemblyError as exc:
        print(f"H9 verification refused: {exc}", file=sys.stderr)
        return 1
    # Re-enabling a lowering must also replace this retired certification gate
    # with independent varying-result and first-operand sensitivity controls.
    print("H9 verification requires a new protocol", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

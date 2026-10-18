#!/usr/bin/env python3
"""Check inventory integrity; declared surface is not guest implementation."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from slopsynth.feature_matrix import validate_matrix


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=ROOT / "spec/lisp-feature-matrix.json")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    try:
        counts = validate_matrix(json.loads(args.matrix.read_text()), require_complete=args.require_complete)
    except (ValueError, OSError, TypeError) as exc:
        print(f"matrix refused: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(counts, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

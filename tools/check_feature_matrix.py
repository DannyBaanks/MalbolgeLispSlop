"""Check inventory integrity; declared surface is not guest implementation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from slopsynth.feature_matrix import validate_matrix


def validate_matrix_ids(matrix: dict[str, Any]) -> list[str]:
    """Validate uniqueness and presence of feature IDs."""
    errors: list[str] = []
    features = matrix.get("features")
    if not isinstance(features, list):
        return ["matrix must contain a 'features' array"]

    seen_ids: set[str] = set()
    for index, item in enumerate(features):
        if not isinstance(item, dict):
            errors.append(f"feature at index {index} is not an object")
            continue
        feat_id = item.get("id")
        if not isinstance(feat_id, str) or not feat_id.strip():
            errors.append(f"feature at index {index} has invalid or missing 'id'")
            continue
        if feat_id in seen_ids:
            errors.append(f"duplicate feature id: {feat_id}")
        seen_ids.add(feat_id)
    return errors


def validate_feature_structure(matrix: dict[str, Any]) -> list[str]:
    """Validate structure of features against matrix contract."""
    try:
        validate_matrix(matrix)
        return []
    except Exception as exc:
        return [str(exc)]


def validate_guest_test_references(matrix: dict[str, Any]) -> list[str]:
    """Validate test references for implemented features."""
    errors: list[str] = []
    features = matrix.get("features", [])
    if not isinstance(features, list):
        return ["'features' must be an array"]
    for row in features:
        if not isinstance(row, dict):
            continue
        if row.get("state") in {"IMPLEMENTED", "DEMONSTRATED"} and not row.get("guest_test_ids"):
            errors.append(f"feature {row.get('id')}: missing guest_test_ids")
    return errors


def check_matrix_file(path: Path) -> dict[str, Any]:
    """Check a matrix file for validity."""
    if not path.is_file():
        return {"valid": False, "feature_count": 0, "errors": [f"file not found: {path}"]}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        counts = validate_matrix(data)
        feature_count = len(data.get("features", []))
        return {
            "valid": True,
            "feature_count": feature_count,
            "counts": counts,
            "errors": [],
        }
    except Exception as exc:
        return {
            "valid": False,
            "feature_count": 0,
            "errors": [str(exc)],
        }


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

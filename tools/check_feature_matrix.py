#!/usr/bin/env python3
"""Validation tool and CLI for LispSlop language feature matrix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REQUIRED_CATEGORIES = frozenset({
    "arithmetic",
    "special_form",
    "list_core",
    "combinator",
    "dot_command",
    "syntax",
    "error",
})

REQUIRED_CASE_FIELDS = (
    "case_id",
    "stdin",
    "expected_stdout",
    "terminal_status",
    "max_steps",
    "timeout_seconds",
    "address_space_bytes",
    "output_bytes",
)


def validate_matrix_ids(matrix: dict[str, Any]) -> list[str]:
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
    errors: list[str] = []
    features = matrix.get("features", [])
    if not isinstance(features, list) or not features:
        return ["'features' must be a non-empty array"]

    for index, item in enumerate(features):
        if not isinstance(item, dict):
            continue
        feat_id = item.get("id", f"index_{index}")
        surface = item.get("surface")
        if not isinstance(surface, str) or not surface.strip():
            errors.append(f"feature {feat_id}: missing or empty 'surface'")

        category = item.get("category")
        if category not in REQUIRED_CATEGORIES:
            errors.append(f"feature {feat_id}: category {category!r} not in {sorted(REQUIRED_CATEGORIES)}")

        semantics = item.get("semantics")
        if not isinstance(semantics, str) or not semantics.strip():
            errors.append(f"feature {feat_id}: missing or empty 'semantics'")

        pos_cases = item.get("positive_cases")
        if not isinstance(pos_cases, list) or not pos_cases:
            errors.append(f"feature {feat_id}: 'positive_cases' must be a non-empty list")
        else:
            for c_idx, case in enumerate(pos_cases):
                if not isinstance(case, dict):
                    errors.append(f"feature {feat_id}: positive_case[{c_idx}] must be a dict")
                    continue
                for field in REQUIRED_CASE_FIELDS:
                    if field not in case:
                        errors.append(f"feature {feat_id}: positive_case[{c_idx}] missing field {field!r}")
                if case.get("max_steps", 0) <= 0:
                    errors.append(f"feature {feat_id}: positive_case[{c_idx}] max_steps must be positive")
                if case.get("timeout_seconds", 0) <= 0:
                    errors.append(f"feature {feat_id}: positive_case[{c_idx}] timeout_seconds must be positive")

        neg_cases = item.get("negative_cases")
        if not isinstance(neg_cases, list):
            errors.append(f"feature {feat_id}: 'negative_cases' must be a list")
        elif category == "error" and not neg_cases:
            errors.append(f"feature {feat_id}: category 'error' must provide negative_cases")

    return errors


def validate_guest_test_references(matrix: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    features = matrix.get("features", [])
    if not isinstance(features, list):
        return ["'features' must be an array"]

    for index, item in enumerate(features):
        if not isinstance(item, dict):
            continue
        feat_id = item.get("id", f"index_{index}")
        test_ids = item.get("guest_test_ids")
        if not isinstance(test_ids, list) or not test_ids:
            errors.append(f"feature {feat_id}: 'guest_test_ids' must be a non-empty list of test names")
        else:
            for t_idx, t_name in enumerate(test_ids):
                if not isinstance(t_name, str) or not t_name.strip():
                    errors.append(f"feature {feat_id}: guest_test_ids[{t_idx}] must be a non-empty string")
    return errors


def check_matrix_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"valid": False, "feature_count": 0, "errors": [f"file not found: {path}"]}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"valid": False, "feature_count": 0, "errors": [f"invalid json: {exc}"]}

    errors: list[str] = []
    errors.extend(validate_matrix_ids(data))
    errors.extend(validate_feature_structure(data))
    errors.extend(validate_guest_test_references(data))

    feature_count = len(data.get("features", [])) if isinstance(data.get("features"), list) else 0
    return {
        "valid": len(errors) == 0,
        "feature_count": feature_count,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("matrix_path", type=Path, nargs="?", default=Path("spec/lisp-feature-matrix.json"))
    args = parser.parse_args(argv)

    report = check_matrix_file(args.matrix_path)
    if report["valid"]:
        print(f"OK: {args.matrix_path} is valid ({report['feature_count']} features).")
        return 0
    else:
        print(f"FAIL: {args.matrix_path} has {len(report['errors'])} errors:", file=sys.stderr)
        for err in report["errors"]:
            print(f"  - {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""Validate a frozen language inventory without inventing guest progress."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "spec/lisp-inventory-v1.json"
STATES = ("DECLARED", "SPECIFIED", "IMPLEMENTED", "DEMONSTRATED")
REQUIRED_SEMANTIC_IDS = frozenset({
    "semantics:global-lookup-shadowing",
    "semantics:lexical-closure-lifetime",
    "semantics:equality-structural-and-identity",
    "semantics:argument-evaluation-order",
    "semantics:let-binding-order",
    "semantics:macro-argument-evaluation",
    "semantics:lazy-force-and-memoization",
    "semantics:short-circuit",
    "semantics:synthetic-value-printing",
    "semantics:reader-token-boundaries",
    "semantics:invalid-type-combinations",
    "semantics:eof",
    "semantics:error-termination-or-continuation",
    "semantics:unknown-dot-command",
    "semantics:repl-persistence-reset",
    "semantics:state-export-import-validation",
    "semantics:resource-limits",
    "semantics:numeric-boundaries",
    "semantics:recursion",
})


def validate_matrix(matrix, *, require_complete=False, verify_guest_evidence=None):
    if not isinstance(matrix, dict) or matrix.get("schema_version") != 1:
        raise ValueError("unsupported matrix schema")
    raw = INVENTORY.read_bytes()
    if matrix.get("inventory_sha256") != hashlib.sha256(raw).hexdigest():
        raise ValueError("inventory digest mismatch")
    inventory = {f["id"]: f for f in json.loads(raw)["features"]}
    semantic_ids = {feature_id for feature_id, feature in inventory.items()
                    if feature.get("category") == "semantic"}
    if not REQUIRED_SEMANTIC_IDS <= semantic_ids:
        raise ValueError("frozen inventory omits required cross-cutting semantics")
    rows = matrix.get("features")
    if not isinstance(rows, list):
        raise ValueError("features must be a list")
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("id") not in inventory or row["id"] in seen:
            raise ValueError("unknown or duplicate feature")
        seen.add(row["id"])
        declared = inventory[row["id"]]
        if any(row.get(k) != declared[k] for k in ("surface", "category", "source")):
            raise ValueError("feature identity differs from frozen inventory")
        state = row.get("state")
        if state not in STATES:
            raise ValueError("unknown feature state")
        if state != "DECLARED":
            if not isinstance(row.get("semantics"), str) or not row["semantics"].strip():
                raise ValueError("specified feature needs explicit semantics")
            for name in ("positive_cases", "negative_cases"):
                if not isinstance(row.get(name), list) or not row[name]:
                    raise ValueError("specified feature needs positive and negative fixtures")
                for case in row[name]:
                    if not isinstance(case, dict):
                        raise ValueError("invalid case")
                    for key in ("stdin_hex", "stdout_hex"):
                        if not isinstance(case.get(key), str):
                            raise ValueError("case requires raw bytes")
                        try:
                            bytes.fromhex(case[key])
                        except ValueError as exc:
                            raise ValueError("invalid case hex") from exc
                    if case.get("status") not in {"HALT", "MAX_STEPS", "LOAD_ERROR", "WALL_TIMEOUT", "OUTPUT_LIMIT", "PROCESS_ERROR"}:
                        raise ValueError("case requires a supported guest status")
                    from tools.guest_runner import RunConfig
                    RunConfig(**case.get("limits", {}))
        if state in {"IMPLEMENTED", "DEMONSTRATED"} and not row.get("guest_test_ids"):
            raise ValueError("implementation needs actual guest tests")
        if state == "DEMONSTRATED":
            if (not row.get("guest_evidence") or verify_guest_evidence is None
                    or verify_guest_evidence(row) is not True):
                raise ValueError("guest claim requires replay-verified execution evidence")
        if require_complete and state != "DEMONSTRATED":
            raise ValueError(f"incomplete feature: {row['id']}")
    if seen != set(inventory):
        raise ValueError("promised features are missing")
    return {state: sum(row["state"] == state for row in rows) for state in STATES}

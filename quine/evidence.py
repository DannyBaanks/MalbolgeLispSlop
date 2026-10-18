"""Versioned quine contract and deterministic evidence report types."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping


_CONTRACT_SCHEMA_VERSION = 1
_REPORT_SCHEMA_VERSION = 1
_ALLOWED_PROFILES = frozenset({"fixed-3^19"})
_ALLOWED_LOADERS = frozenset({"canonical"})
_ALLOWED_NEWLINE_POLICIES = frozenset({"final-newline", "no-final-newline"})
_ALLOWED_STATUSES = frozenset(
    {"DEMONSTRATED", "NOT_DEMONSTRATED", "BUDGET_EXHAUSTED"}
)
_REQUIRED_BOUNDS = frozenset(
    {
        "max_nodes",
        "wall_seconds",
        "candidate_steps",
        "candidate_timeout_seconds",
        "candidate_memory_bytes",
        "max_candidate_bytes",
    }
)
_POSITIVE_INTEGER_BOUNDS = frozenset(
    {"max_nodes", "candidate_steps", "candidate_memory_bytes", "max_candidate_bytes"}
)
_POSITIVE_NUMBER_BOUNDS = frozenset({"wall_seconds", "candidate_timeout_seconds"})
_EXPECTED_WHITESPACE_BYTES = [9, 10, 13, 32]
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True, slots=True)
class QuineContract:
    profile: str
    loader: str
    newline_policy: str

    def __post_init__(self) -> None:
        if not isinstance(self.profile, str) or self.profile not in _ALLOWED_PROFILES:
            raise ValueError("profile must be fixed-3^19")
        if not isinstance(self.loader, str) or self.loader not in _ALLOWED_LOADERS:
            raise ValueError("loader must be canonical")
        if (
            not isinstance(self.newline_policy, str)
            or self.newline_policy not in _ALLOWED_NEWLINE_POLICIES
        ):
            raise ValueError("newline_policy must be final-newline or no-final-newline")


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def load_contract(path: Path) -> QuineContract:
    """Load the fixed-profile contract, rejecting weaker comparison rules."""
    try:
        data = _object(json.loads(path.read_text(encoding="utf-8")), "contract")
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read quine contract: {exc}") from exc

    required_fields = {
        "schema_version",
        "profile",
        "loader",
        "newline_policy",
        "ignored_loader_bytes",
        "stdout_comparison",
        "required_guest_status",
    }
    if set(data) != required_fields:
        raise ValueError(f"contract fields must be {sorted(required_fields)}")
    if type(data["schema_version"]) is not int or data["schema_version"] != _CONTRACT_SCHEMA_VERSION:
        raise ValueError("unsupported contract schema_version")
    if not isinstance(data["profile"], str) or data["profile"] not in _ALLOWED_PROFILES:
        raise ValueError("profile must be fixed-3^19")
    if not isinstance(data["loader"], str) or data["loader"] not in _ALLOWED_LOADERS:
        raise ValueError("loader must be canonical")
    if (
        not isinstance(data["newline_policy"], str)
        or data["newline_policy"] not in _ALLOWED_NEWLINE_POLICIES
    ):
        raise ValueError("newline_policy must be final-newline or no-final-newline")
    if data["ignored_loader_bytes"] != _EXPECTED_WHITESPACE_BYTES:
        raise ValueError("ignored_loader_bytes must match the fixed19 canonical loader")
    if data["stdout_comparison"] != "byte-exact":
        raise ValueError("stdout_comparison must be byte-exact")
    if data["required_guest_status"] != "HALT":
        raise ValueError("required_guest_status must be HALT")

    return QuineContract(
        profile=data["profile"],
        loader=data["loader"],
        newline_policy=data["newline_policy"],
    )


def _validate_bounds(bounds: Mapping[str, object]) -> dict[str, int | float]:
    if not isinstance(bounds, Mapping):
        raise ValueError("bounds must be a mapping")
    missing = _REQUIRED_BOUNDS - set(bounds)
    if missing:
        raise ValueError(f"bounds missing required fields: {', '.join(sorted(missing))}")
    extra = set(bounds) - _REQUIRED_BOUNDS
    if extra:
        raise ValueError(f"bounds have unknown fields: {', '.join(sorted(extra))}")

    normalized: dict[str, int | float] = {}
    for name in sorted(_REQUIRED_BOUNDS):
        value = bounds[name]
        if name in _POSITIVE_INTEGER_BOUNDS:
            if type(value) is not int or value <= 0:
                raise ValueError(f"bounds.{name} must be a positive integer")
            normalized[name] = value
        else:
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"bounds.{name} must be finite and positive")
            normalized[name] = value
    return normalized


@dataclass(frozen=True, slots=True)
class QuineReport:
    status: str
    candidate_path: str | None
    source_sha256: str | None
    stdout_sha256: str | None
    steps: int | None
    bounds: Mapping[str, object]
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.status, str) or self.status not in _ALLOWED_STATUSES:
            raise ValueError("status must be DEMONSTRATED, NOT_DEMONSTRATED, or BUDGET_EXHAUSTED")
        if self.candidate_path is not None and not isinstance(self.candidate_path, str):
            raise ValueError("candidate_path must be a string or null")
        for field_name, digest in (
            ("source_sha256", self.source_sha256),
            ("stdout_sha256", self.stdout_sha256),
        ):
            if digest is not None and (
                not isinstance(digest, str) or _SHA256_PATTERN.fullmatch(digest) is None
            ):
                raise ValueError(f"{field_name} must be a lowercase SHA-256 or null")
        if self.steps is not None and (type(self.steps) is not int or self.steps < 0):
            raise ValueError("steps must be a nonnegative integer or null")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("reason must be nonempty")

        normalized_bounds = _validate_bounds(self.bounds)
        object.__setattr__(self, "bounds", MappingProxyType(normalized_bounds))
        if self.status == "DEMONSTRATED":
            if (
                self.candidate_path is None
                or self.source_sha256 is None
                or self.stdout_sha256 is None
                or self.source_sha256 != self.stdout_sha256
                or self.steps is None
            ):
                raise ValueError("DEMONSTRATED requires matching source/stdout digests and guest steps")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": _REPORT_SCHEMA_VERSION,
            "status": self.status,
            "candidate_path": self.candidate_path,
            "source_sha256": self.source_sha256,
            "stdout_sha256": self.stdout_sha256,
            "steps": self.steps,
            "bounds": dict(self.bounds),
            "reason": self.reason,
        }

    def to_bytes(self) -> bytes:
        return (json.dumps(self.to_dict(), sort_keys=True, indent=2) + "\n").encode("utf-8")

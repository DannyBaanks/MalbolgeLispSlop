"""Bounded deterministic candidate search for the fixed-3^19 guest quine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math
from pathlib import Path
import re
import time
from typing import Iterator

from slopsynth.encode import encode_dispatch_sequence
from slopsynth.profile import Profile, load_profile
from tools.guest_runner import GuestStatus, RunConfig, run_guest

from .evidence import QuineContract, QuineReport


ROOT = Path(__file__).resolve().parents[1]
ALGORITHM = "fixed19-profile-dispatch-product-v1"
_DEFAULT_MAX_TIMEOUT_SECONDS = 5.0
_DEFAULT_MAX_MEMORY_BYTES = 536_870_912
_DEFAULT_MAX_OUTPUT_BYTES = 1_048_576


@dataclass(frozen=True, slots=True)
class QuineSearchBudget:
    max_nodes: int
    wall_seconds: float
    candidate_steps: int
    candidate_timeout_seconds: float
    candidate_memory_bytes: int
    max_candidate_bytes: int
    seed: int = 0

    def __post_init__(self) -> None:
        if type(self.max_nodes) is not int or self.max_nodes < 0:
            raise ValueError("max_nodes must be a nonnegative integer")
        if type(self.candidate_steps) is not int or self.candidate_steps <= 0:
            raise ValueError("candidate_steps must be a positive integer")
        if type(self.candidate_memory_bytes) is not int or self.candidate_memory_bytes <= 0:
            raise ValueError("candidate_memory_bytes must be a positive integer")
        if type(self.max_candidate_bytes) is not int or self.max_candidate_bytes <= 0:
            raise ValueError("max_candidate_bytes must be a positive integer")
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("seed must be a nonnegative integer")
        for name, value in (
            ("wall_seconds", self.wall_seconds),
            ("candidate_timeout_seconds", self.candidate_timeout_seconds),
        ):
            try:
                valid = (
                    not isinstance(value, bool)
                    and isinstance(value, (int, float))
                    and math.isfinite(value)
                    and value > 0
                )
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError(f"{name} must be finite and positive")

    def bounds(self) -> dict[str, int | float]:
        return {
            "max_nodes": self.max_nodes,
            "wall_seconds": self.wall_seconds,
            "candidate_steps": self.candidate_steps,
            "candidate_timeout_seconds": self.candidate_timeout_seconds,
            "candidate_memory_bytes": self.candidate_memory_bytes,
            "max_candidate_bytes": self.max_candidate_bytes,
        }

    def to_dict(self) -> dict[str, int | float]:
        return {**self.bounds(), "seed": self.seed}


def load_budget(path: Path) -> QuineSearchBudget:
    """Load a versioned JSON budget without silently defaulting missing limits."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read quine search budget: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("quine search budget must be an object")
    required = {
        "schema_version",
        "max_nodes",
        "wall_seconds",
        "candidate_steps",
        "candidate_timeout_seconds",
        "candidate_memory_bytes",
        "max_candidate_bytes",
        "seed",
    }
    if set(data) != required:
        raise ValueError(f"budget fields must be {sorted(required)}")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("unsupported budget schema_version")
    return QuineSearchBudget(
        max_nodes=data["max_nodes"],
        wall_seconds=data["wall_seconds"],
        candidate_steps=data["candidate_steps"],
        candidate_timeout_seconds=data["candidate_timeout_seconds"],
        candidate_memory_bytes=data["candidate_memory_bytes"],
        max_candidate_bytes=data["max_candidate_bytes"],
        seed=data["seed"],
    )


def _load_fixed_profile(contract: QuineContract) -> Profile:
    profile = load_profile(ROOT / "profiles" / "fixed19.json")
    if profile.name != contract.profile:
        raise ValueError("contract profile does not match bundled fixed19 profile")
    if contract.loader not in profile.loaders:
        raise ValueError("contract loader is not defined by the fixed profile")
    return profile


def _dispatch_order(profile: Profile, seed: int) -> tuple[str, ...]:
    names = tuple(name for name, _ in sorted(profile.dispatch.items(), key=lambda item: item[1]))
    if not names:
        raise ValueError("fixed profile has no dispatch operations")
    direction = 1 if seed // len(names) % 2 == 0 else -1
    offset = seed % len(names)
    return tuple(names[(offset + direction * index) % len(names)] for index in range(len(names)))


def _source_suffix(contract: QuineContract) -> bytes:
    return b"\n" if contract.newline_policy == "final-newline" else b""


def iter_candidates(
    contract: QuineContract, budget: QuineSearchBudget
) -> Iterator[bytes]:
    """Yield profile-derived dispatch streams in a reproducible seeded order.

    The seed rotates or reverses the profile's dispatch-name order. Every
    candidate byte is then derived by the shared position-aware encoder; this
    function contains no instruction-byte corpus or opcode source templates.
    """
    profile = _load_fixed_profile(contract)
    dispatch_names = _dispatch_order(profile, budget.seed)
    suffix = _source_suffix(contract)
    max_body_bytes = budget.max_candidate_bytes - len(suffix)
    explored = 0
    for length in range(1, max_body_bytes + 1):
        for sequence in itertools.product(dispatch_names, repeat=length):
            if explored >= budget.max_nodes:
                return
            yield encode_dispatch_sequence(sequence, profile) + suffix
            explored += 1


def _space_exceeds_nodes(
    profile: Profile, contract: QuineContract, budget: QuineSearchBudget
) -> bool:
    total = 0
    alphabet_size = len(profile.dispatch)
    max_body_bytes = budget.max_candidate_bytes - len(_source_suffix(contract))
    # Newline bytes count toward the source-size budget but are discarded by
    # canonical loading, so only dispatch-derived body bytes consume cells.
    for length in range(1, max_body_bytes + 1):
        total += alphabet_size**length
        if total > budget.max_nodes:
            return True
    return False


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256(path.read_bytes())


def _write_new(path: Path, value: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(value)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode(
        "utf-8"
    )


def _json_line(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode(
        "utf-8"
    )


def _guest_steps(stderr: bytes) -> int | None:
    match = re.search(rb"(?:^|\n)HALT steps=([0-9]+)(?:\n|$)", stderr)
    return int(match.group(1)) if match is not None else None


def _candidate_reason(status: GuestStatus, stdout: bytes, candidate: bytes) -> str:
    if status is not GuestStatus.HALT:
        return f"guest ended with {status.value}"
    if stdout != candidate:
        return "guest halted but stdout did not equal candidate source bytes"
    return "guest halted and stdout matched candidate source bytes"


def search(
    contract: QuineContract,
    budget: QuineSearchBudget,
    output_dir: Path,
) -> QuineReport:
    """Search candidates and preserve every attempted image and VM result.

    ``output_dir`` must be new. Each attempted candidate has a source file,
    raw stdout and stderr files, plus a digest/status record. A bounded failure
    never claims that no quine exists.
    """
    profile = _load_fixed_profile(contract)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(exist_ok=False)
    candidates_dir = output_dir / "candidates"
    candidates_dir.mkdir()
    records_path = output_dir / "candidate-records.jsonl"
    report: QuineReport | None = None
    attempted = 0
    global_exhausted = False
    last_candidate_path: str | None = None
    last_source_sha256: str | None = None
    last_stdout_sha256: str | None = None
    last_steps: int | None = None
    started = time.monotonic()

    with records_path.open("xb") as records:
        if budget.max_nodes == 0:
            report = QuineReport(
                status="BUDGET_EXHAUSTED",
                candidate_path=None,
                source_sha256=None,
                stdout_sha256=None,
                steps=None,
                bounds=budget.bounds(),
                reason="max_nodes is zero, so no candidate node could be explored",
            )
        else:
            for candidate in iter_candidates(contract, budget):
                elapsed = time.monotonic() - started
                remaining = budget.wall_seconds - elapsed
                if remaining <= 0:
                    global_exhausted = True
                    break

                attempted += 1
                stem = f"{attempted:06d}"
                source_path = candidates_dir / f"{stem}.mb"
                stdout_path = candidates_dir / f"{stem}.stdout"
                stderr_path = candidates_dir / f"{stem}.stderr"
                _write_new(source_path, candidate)
                candidate_relative = source_path.relative_to(output_dir).as_posix()
                last_candidate_path = candidate_relative
                last_source_sha256 = _sha256(candidate)

                run_config = RunConfig(
                    loader=contract.loader,
                    max_steps=budget.candidate_steps,
                    timeout_seconds=min(budget.candidate_timeout_seconds, remaining),
                    address_space_bytes=min(
                        budget.candidate_memory_bytes, _DEFAULT_MAX_MEMORY_BYTES
                    ),
                    output_bytes=min(
                        budget.max_candidate_bytes, _DEFAULT_MAX_OUTPUT_BYTES
                    ),
                )
                guest = run_guest(source_path, b"", run_config)
                _write_new(stdout_path, guest.stdout)
                _write_new(stderr_path, guest.stderr)
                last_stdout_sha256 = _sha256(guest.stdout)
                last_steps = _guest_steps(guest.stderr) if guest.status is GuestStatus.HALT else None
                reason = _candidate_reason(guest.status, guest.stdout, candidate)
                record = {
                    "node": attempted,
                    "candidate_path": candidate_relative,
                    "candidate_sha256": last_source_sha256,
                    "stdout_path": stdout_path.relative_to(output_dir).as_posix(),
                    "stdout_sha256": last_stdout_sha256,
                    "stderr_path": stderr_path.relative_to(output_dir).as_posix(),
                    "stderr_sha256": _sha256(guest.stderr),
                    "guest_status": guest.status.value,
                    "returncode": guest.returncode,
                    "steps": last_steps,
                    "reason": reason,
                }
                records.write(_json_line(record))
                records.flush()

                if guest.status is GuestStatus.HALT and guest.stdout == candidate:
                    report = QuineReport(
                        status="DEMONSTRATED",
                        candidate_path=candidate_relative,
                        source_sha256=last_source_sha256,
                        stdout_sha256=last_stdout_sha256,
                        steps=last_steps,
                        bounds=budget.bounds(),
                        reason="guest halted and stdout matched source bytes exactly",
                    )
                    break

                if guest.status is GuestStatus.WALL_TIMEOUT:
                    elapsed = time.monotonic() - started
                    if elapsed >= budget.wall_seconds:
                        global_exhausted = True
                        break

    if report is None:
        elapsed = time.monotonic() - started
        if elapsed >= budget.wall_seconds:
            global_exhausted = True
        if (
            budget.max_nodes == 0
            or global_exhausted
            or _space_exceeds_nodes(profile, contract, budget)
        ):
            status = "BUDGET_EXHAUSTED"
            if global_exhausted:
                reason = "global wall_seconds budget exhausted before search completion"
            else:
                reason = "max_nodes budget reached before the bounded candidate space was exhausted"
        else:
            status = "NOT_DEMONSTRATED"
            reason = (
                "completed the declared finite candidate space without a byte-exact quine; "
                "this does not prove that no quine exists"
            )
        report = QuineReport(
            status=status,
            candidate_path=last_candidate_path,
            source_sha256=last_source_sha256,
            stdout_sha256=last_stdout_sha256,
            steps=last_steps,
            bounds=budget.bounds(),
            reason=reason,
        )

    candidate_records_sha256 = _sha256_file(records_path)
    search_manifest = {
        "schema_version": 1,
        "algorithm": ALGORITHM,
        "seed": budget.seed,
        "seed_rule": "rotate-by-dispatch-count; reverse-on-odd-quotient-v1",
        "profile": contract.profile,
        "loader": contract.loader,
        "newline_policy": contract.newline_policy,
        "bounds": budget.to_dict(),
        "candidates_attempted": attempted,
        "candidate_records_path": records_path.name,
        "candidate_records_sha256": candidate_records_sha256,
        "report_status": report.status,
        "report_reason": report.reason,
    }
    _write_new(output_dir / "report.json", report.to_bytes())
    _write_new(output_dir / "search-manifest.json", _json_bytes(search_manifest))
    return report

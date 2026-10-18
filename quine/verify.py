"""Byte-exact in-guest verification of a fixed-3^19 quine candidate."""

from __future__ import annotations

import hashlib
from pathlib import Path

from tools.guest_runner import GuestStatus, RunConfig, run_guest

from .evidence import QuineContract, QuineReport
from .search import QuineSearchBudget, parse_halt_steps


_SINGLE_IMPLEMENTATION_NOTE = "single-implementation verification"


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _run_config(contract: QuineContract, budget: QuineSearchBudget) -> RunConfig:
    return RunConfig(
        loader=contract.loader,
        max_steps=budget.candidate_steps,
        timeout_seconds=budget.candidate_timeout_seconds,
        address_space_bytes=budget.candidate_memory_bytes,
        output_bytes=budget.max_candidate_bytes,
    )


def _failed(
    candidate_path: str,
    source_sha256: str,
    stdout_sha256: str | None,
    steps: int | None,
    bounds: dict[str, int | float],
    reason: str,
    status: str = "NOT_DEMONSTRATED",
) -> QuineReport:
    return QuineReport(
        status=status,
        candidate_path=candidate_path,
        source_sha256=source_sha256,
        stdout_sha256=stdout_sha256,
        steps=steps,
        bounds=bounds,
        reason=reason,
    )


def verify_candidate(
    source: Path,
    contract: QuineContract,
    budget: QuineSearchBudget,
    *,
    engine_path: Path | None = None,
) -> QuineReport:
    """Run ``source`` in the guest and decide byte-exact quine validity.

    The source bytes are captured before the run and the file is re-read after
    it, so a candidate whose bytes change during verification can never be
    reported ``DEMONSTRATED``. The guest runs with empty stdin under the
    contract's canonical loader and the budget's step, wall-time, address-space,
    and output-capture limits. The image path is passed directly to ``bolge19``
    through ``run_guest``; the host never copies candidate bytes into the
    compared output. Stderr is telemetry only: it is parsed for the halt step
    count and never compared as quine output. ``engine_path`` exists for
    controlled test engines; the CLI always uses the bundled ``build/bolge19``.
    """
    source = Path(source)
    candidate_path = str(source)
    bounds = budget.bounds()
    try:
        captured = source.read_bytes()
    except OSError as exc:
        raise ValueError(f"cannot read candidate source: {exc}") from exc
    source_sha256 = _sha256(captured)

    if not captured:
        return _failed(
            candidate_path,
            source_sha256,
            None,
            None,
            bounds,
            "candidate source is empty; an empty image has no bytes to emit "
            "as a guest quine and is not admissible under this contract",
        )

    if len(captured) > budget.max_candidate_bytes:
        return _failed(
            candidate_path,
            source_sha256,
            None,
            None,
            bounds,
            "candidate source is larger than the declared "
            f"max_candidate_bytes={budget.max_candidate_bytes}; byte-exact "
            "stdout comparison cannot succeed under the declared output budget",
        )

    guest = run_guest(source, b"", _run_config(contract, budget), engine_path=engine_path)

    try:
        current = source.read_bytes()
    except OSError:
        current = None

    stdout_sha256 = _sha256(guest.stdout)
    steps = parse_halt_steps(guest.stderr) if guest.status is GuestStatus.HALT else None

    if current != captured:
        return _failed(
            candidate_path,
            source_sha256,
            stdout_sha256,
            steps,
            bounds,
            "candidate source bytes changed during verification; the captured "
            "bytes no longer match the artifact on disk and cannot be reported "
            "as verified",
        )

    if guest.status is GuestStatus.HALT:
        if guest.stdout == captured:
            return QuineReport(
                status="DEMONSTRATED",
                candidate_path=candidate_path,
                source_sha256=source_sha256,
                stdout_sha256=stdout_sha256,
                steps=steps,
                bounds=bounds,
                reason=(
                    "guest halted under canonical loading and stdout matched "
                    "the captured source bytes exactly; "
                    f"{_SINGLE_IMPLEMENTATION_NOTE}"
                ),
            )
        return _failed(
            candidate_path,
            source_sha256,
            stdout_sha256,
            steps,
            bounds,
            "guest halted but stdout did not match the captured source bytes "
            "byte-for-byte",
        )

    if guest.status is GuestStatus.MAX_STEPS:
        return _failed(
            candidate_path,
            source_sha256,
            stdout_sha256,
            None,
            bounds,
            f"candidate did not halt within candidate_steps={budget.candidate_steps}; "
            "the step budget was exhausted before a verdict",
            status="BUDGET_EXHAUSTED",
        )

    if guest.status is GuestStatus.WALL_TIMEOUT:
        return _failed(
            candidate_path,
            source_sha256,
            stdout_sha256,
            None,
            bounds,
            "candidate did not halt within "
            f"candidate_timeout_seconds={budget.candidate_timeout_seconds}; "
            "the wall-time budget was exhausted before a verdict",
            status="BUDGET_EXHAUSTED",
        )

    if guest.status is GuestStatus.LOAD_ERROR:
        return _failed(
            candidate_path,
            source_sha256,
            stdout_sha256,
            None,
            bounds,
            "the canonical loader rejected the candidate image; no guest "
            "execution to verify",
        )

    if guest.status is GuestStatus.OUTPUT_LIMIT:
        return _failed(
            candidate_path,
            source_sha256,
            stdout_sha256,
            None,
            bounds,
            "guest stdout exceeded the declared "
            f"max_candidate_bytes={budget.max_candidate_bytes} capture limit "
            "and cannot equal the source bytes",
        )

    return _failed(
        candidate_path,
        source_sha256,
        stdout_sha256,
        None,
        bounds,
        "the guest process failed before producing a verifiable result",
    )

"""Bounded deterministic search for straight-line fixed-3^19 guest programs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .encode import encode_program
from .ir import Halt, Program, ReadA, WriteA
from .model import RunStatus, run_model
from .profile import Profile


class SynthesisStatus(str, Enum):
    FOUND = "FOUND"
    NOT_FOUND_WITHIN_BOUNDS = "NOT_FOUND_WITHIN_BOUNDS"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


@dataclass(frozen=True, slots=True)
class SearchBudget:
    max_cells: int
    max_nodes: int
    max_steps: int
    max_address: int

    def __post_init__(self) -> None:
        values = {
            "max_cells": self.max_cells,
            "max_nodes": self.max_nodes,
            "max_steps": self.max_steps,
            "max_address": self.max_address,
        }
        for name, value in values.items():
            if type(value) is not int:
                raise ValueError(f"{name} must be an integer")
        if self.max_cells < 0:
            raise ValueError("max_cells must not be negative")
        if self.max_nodes < 0:
            raise ValueError("max_nodes must not be negative")
        if self.max_steps <= 0:
            raise ValueError("max_steps must be positive")
        if self.max_address < 0:
            raise ValueError("max_address must not be negative")


@dataclass(frozen=True, slots=True)
class SynthesisResult:
    status: SynthesisStatus
    image: bytes | None
    explored_nodes: int
    bounds: SearchBudget


def _interpret(program: Program, stdin: bytes, profile: Profile) -> bytes:
    """Evaluate the current straight-line guest IR for a model-check probe."""
    accumulator = 0
    input_position = 0
    stdout = bytearray()
    for operation in program.operations:
        if isinstance(operation, ReadA):
            if input_position < len(stdin):
                accumulator = stdin[input_position]
                input_position += 1
            else:
                accumulator = profile.eof_value
        elif isinstance(operation, WriteA):
            stdout.append(accumulator & 0xFF)
        elif isinstance(operation, Halt):
            break
        else:  # Program validates its operations, but fail closed if extended.
            raise ValueError(f"unsupported guest operation: {type(operation).__name__}")
    return bytes(stdout)


def _probe_inputs(read_count: int) -> tuple[bytes, ...]:
    """Return deterministic probes spanning EOF and byte-boundary values."""
    probes: list[bytes] = [b""]
    for value in (0x00, 0x01, 0x7F, 0x80, 0xFE, 0xFF):
        probes.append(bytes((value,)) * max(1, read_count))
    if read_count > 1:
        probes.append(bytes(range(min(read_count, 256))))
        probes.append(bytes(reversed(range(min(read_count, 256)))))
    return tuple(probes)


def synthesize_program(
    program: Program, profile: Profile, budget: SearchBudget
) -> SynthesisResult:
    """Synthesize and model-check the one-cell-per-op straight-line candidate.

    This backend is deterministic, so its search graph currently has one
    candidate node. ``NOT_FOUND_WITHIN_BOUNDS`` records a configured bound
    that rejects that candidate; ``BUDGET_EXHAUSTED`` means no candidate node
    could be explored and is not an unsatisfiability proof.
    """
    if budget.max_address >= profile.end:
        raise ValueError("max_address must be below the profile end value")
    if budget.max_nodes == 0:
        return SynthesisResult(SynthesisStatus.BUDGET_EXHAUSTED, None, 0, budget)
    if len(program.operations) > budget.max_cells:
        return SynthesisResult(
            SynthesisStatus.NOT_FOUND_WITHIN_BOUNDS, None, 0, budget
        )

    candidate = encode_program(program, profile)
    explored = 1
    reads = sum(isinstance(operation, ReadA) for operation in program.operations)
    for stdin in _probe_inputs(reads):
        expected = _interpret(program, stdin, profile)
        actual = run_model(
            candidate,
            stdin,
            profile,
            loader="canonical",
            max_steps=budget.max_steps,
            max_address=budget.max_address,
        )
        if actual.status is RunStatus.LOAD_ERROR:
            raise RuntimeError("encoder produced an image rejected by the model loader")
        if actual.status is not RunStatus.HALT or actual.stdout != expected:
            return SynthesisResult(
                SynthesisStatus.NOT_FOUND_WITHIN_BOUNDS, None, explored, budget
            )

    return SynthesisResult(SynthesisStatus.FOUND, candidate, explored, budget)

"""Bounded deterministic search for fixed-3^19 guest programs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from itertools import product

from .encode import encode_dispatch_sequence, encode_program
from .ir import (
    Add,
    BranchZero,
    Call,
    Function,
    Halt,
    Jump,
    Load,
    Module,
    ModuleOperation,
    Program,
    ReadA,
    Return,
    Store,
    Sub,
    WriteA,
)
from .model import RunResult, RunStatus, run_model
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
    last_candidate: bytes | None = None


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
                SynthesisStatus.NOT_FOUND_WITHIN_BOUNDS,
                None,
                explored,
                budget,
                candidate,
            )

    return SynthesisResult(
        SynthesisStatus.FOUND, candidate, explored, budget, candidate
    )


def _direct_program(module: Module) -> Program | None:
    """Recognize the only module lowering implemented by the M1 backend."""
    if len(module.functions) != 1:
        return None
    function: Function = module.functions[0]
    if len(function.blocks) != 1 or function.entry_block != function.blocks[0].name:
        return None
    operations = function.blocks[0].operations
    if any(not isinstance(operation, (ReadA, WriteA, Halt)) for operation in operations):
        return None
    if any(
        isinstance(operation, ReadA) and operation.destination != "A"
        or isinstance(operation, WriteA) and operation.value != "A"
        for operation in operations
    ):
        return None
    return Program(module.name, tuple(operations))  # type: ignore[arg-type]


def compile_module(
    module: Module, profile: Profile, budget: SearchBudget
) -> SynthesisResult:
    """Compile direct M1 modules or search bounded dispatch streams for others.

    Advanced candidates are enumerated in increasing cell count and profile
    dispatch order. A successful result matches every declared I/O case and
    carries the structural trace checks for the requested IR features. Search
    exhaustion is not a proof that no Malbolge implementation exists.
    """
    if budget.max_address >= profile.end:
        raise ValueError("max_address must be below the profile end value")
    if budget.max_nodes == 0:
        return SynthesisResult(SynthesisStatus.BUDGET_EXHAUSTED, None, 0, budget)

    function_operations = sum(
        len(block.operations)
        for function in module.functions
        for block in function.blocks
    )
    if function_operations > budget.max_cells:
        return SynthesisResult(
            SynthesisStatus.NOT_FOUND_WITHIN_BOUNDS, None, 0, budget
        )

    program = _direct_program(module)
    if program is not None:
        result = synthesize_program(program, profile, budget)
        if result.status is not SynthesisStatus.FOUND or result.image is None:
            return result
        for case in module.cases:
            observed = run_model(
                result.image,
                case.stdin,
                profile,
                loader="canonical",
                max_steps=budget.max_steps,
                max_address=budget.max_address,
            )
            if observed.status.value != case.status or observed.stdout != case.stdout:
                return SynthesisResult(
                    SynthesisStatus.NOT_FOUND_WITHIN_BOUNDS,
                    None,
                    result.explored_nodes,
                    budget,
                    result.image,
                )
        return result

    dispatch_names = tuple(
        name for name, _ in sorted(profile.dispatch.items(), key=lambda pair: pair[1])
    )
    requires_branch = any(
        isinstance(operation, BranchZero) for operation in _module_operations(module)
    )
    requires_memory = any(
        isinstance(operation, (Load, Store)) for operation in _module_operations(module)
    )
    requires_arithmetic = any(
        isinstance(operation, (Add, Sub)) for operation in _module_operations(module)
    )
    requires_call = any(
        isinstance(operation, (Call, Return)) for operation in _module_operations(module)
    )
    requires_loop = _has_back_edge(module)

    explored = 0
    last_candidate: bytes | None = None
    for cell_count in range(1, budget.max_cells + 1):
        for sequence in product(dispatch_names, repeat=cell_count):
            if explored >= budget.max_nodes:
                return SynthesisResult(
                    SynthesisStatus.BUDGET_EXHAUSTED,
                    None,
                    explored,
                    budget,
                    last_candidate,
                )
            candidate = encode_dispatch_sequence(sequence, profile)
            explored += 1
            last_candidate = candidate
            observations = [
                run_model(
                    candidate,
                    case.stdin,
                    profile,
                    loader="canonical",
                    max_steps=budget.max_steps,
                    max_address=budget.max_address,
                    trace_writes=requires_memory,
                    trace_instructions=True,
                    trace_accesses=requires_memory,
                )
                for case in module.cases
            ]
            if not all(
                observation.status.value == case.status
                and observation.stdout == case.stdout
                for observation, case in zip(observations, module.cases)
            ):
                continue
            if not _has_required_trace(
                observations,
                image_size=len(candidate),
                requires_branch=requires_branch,
                requires_memory=requires_memory,
                requires_arithmetic=requires_arithmetic,
                requires_call=requires_call,
                requires_loop=requires_loop,
            ):
                continue
            return SynthesisResult(
                SynthesisStatus.FOUND, candidate, explored, budget, candidate
            )

    return SynthesisResult(
        SynthesisStatus.NOT_FOUND_WITHIN_BOUNDS,
        None,
        explored,
        budget,
        last_candidate,
    )


def _module_operations(module: Module) -> tuple[ModuleOperation, ...]:
    return tuple(
        operation
        for function in module.functions
        for block in function.blocks
        for operation in block.operations
    )


def _has_back_edge(module: Module) -> bool:
    for function in module.functions:
        order = {block.name: index for index, block in enumerate(function.blocks)}
        for block in function.blocks:
            for operation in block.operations:
                if isinstance(operation, Jump) and order[operation.target] <= order[block.name]:
                    return True
                if isinstance(operation, BranchZero) and any(
                    order[target] <= order[block.name]
                    for target in (operation.zero_target, operation.nonzero_target)
                ):
                    return True
    return False


def _has_required_trace(
    observations: list[RunResult],
    *,
    image_size: int,
    requires_branch: bool,
    requires_memory: bool,
    requires_arithmetic: bool,
    requires_call: bool,
    requires_loop: bool,
) -> bool:
    for observation in observations:
        operations = [event.operation for event in observation.instruction_trace]
        output_steps = [
            event.step
            for event in observation.instruction_trace
            if event.operation == "output"
        ]
        final_step = observation.instruction_trace[-1].step if observation.instruction_trace else -1
        first_output = min(output_steps, default=final_step + 1)
        before_output = [
            event
            for event in observation.instruction_trace
            if event.step < first_output
        ]
        prior_operations = [event.operation for event in before_output]
        if requires_branch and "jump" not in prior_operations:
            return False
        if requires_memory:
            guest_writes = [
                write
                for write in observation.memory_writes
                if write.address >= image_size and write.step < first_output
            ]
            guest_reads = [
                access
                for access in observation.memory_accesses
                if access.address >= image_size
                and access.purpose
                in {"crazy_source", "rotate_source", "move_source", "jump_target"}
                and access.step < first_output
            ]
            if not any(
                access.address == write.address and access.step > write.step
                for access in guest_reads
                for write in guest_writes
            ):
                return False
        if requires_arithmetic:
            if not any(
                operation in {"crazy", "rotate"} for operation in prior_operations
            ) or prior_operations.count("input") < 2:
                return False
        if requires_call and prior_operations.count("jump") < 2:
            return False
        if requires_loop:
            prior_addresses = [event.address for event in before_output]
            if (
                prior_operations.count("jump") < 2
                or len(set(prior_addresses)) == len(prior_addresses)
            ):
                return False
    return True

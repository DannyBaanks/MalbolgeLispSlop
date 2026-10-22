"""Typed, declarative operations accepted by the fixed-3^19 synthesizer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class ReadA:
    """Read one input byte into a named guest value; EOF uses the profile sentinel."""

    destination: str = "A"

    def __post_init__(self) -> None:
        if not self.destination:
            raise ValueError("read destination must not be empty")


@dataclass(frozen=True, slots=True)
class WriteA:
    """Write the low byte of a named guest value to stdout."""

    value: str = "A"

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("write value must not be empty")


@dataclass(frozen=True, slots=True)
class WriteDecimal:
    """Write a nonnegative guest integer as decimal ASCII (module backend only)."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value:
            raise ValueError("decimal output value must be a non-empty name")


@dataclass(frozen=True, slots=True)
class Halt:
    """Terminate the guest normally."""


Operation: TypeAlias = ReadA | WriteA | Halt


ValueRef: TypeAlias = str | int


@dataclass(frozen=True, slots=True)
class BranchZero:
    value: ValueRef
    zero_target: str
    nonzero_target: str


@dataclass(frozen=True, slots=True)
class Jump:
    target: str


@dataclass(frozen=True, slots=True)
class Load:
    destination: str
    address: ValueRef


@dataclass(frozen=True, slots=True)
class Store:
    address: ValueRef
    value: ValueRef


@dataclass(frozen=True, slots=True)
class Add:
    destination: str
    left: ValueRef
    right: ValueRef


@dataclass(frozen=True, slots=True)
class Sub:
    destination: str
    left: ValueRef
    right: ValueRef


@dataclass(frozen=True, slots=True)
class Mul:
    destination: str
    left: ValueRef
    right: ValueRef


@dataclass(frozen=True, slots=True)
class Lt:
    """destination = 1 if left < right else 0 (unsigned)."""

    destination: str
    left: ValueRef
    right: ValueRef


@dataclass(frozen=True, slots=True)
class Eq:
    """destination = 1 if left == right else 0."""

    destination: str
    left: ValueRef
    right: ValueRef


@dataclass(frozen=True, slots=True)
class And:
    """destination = 1 if both operands are nonzero else 0."""

    destination: str
    left: ValueRef
    right: ValueRef


@dataclass(frozen=True, slots=True)
class Or:
    """destination = 1 if either operand is nonzero else 0."""

    destination: str
    left: ValueRef
    right: ValueRef


@dataclass(frozen=True, slots=True)
class Call:
    function: str
    arguments: tuple[ValueRef, ...] = ()
    destination: str | None = None


@dataclass(frozen=True, slots=True)
class Return:
    value: ValueRef | None = None


ModuleOperation: TypeAlias = (
    Operation | WriteDecimal | BranchZero | Jump | Load | Store | Add | Sub | Mul | Lt | Eq | And | Or | Call | Return
)


@dataclass(frozen=True, slots=True)
class BasicBlock:
    name: str
    operations: tuple[ModuleOperation, ...]

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("basic block name must not be empty")
        if not isinstance(self.operations, tuple) or not self.operations:
            raise ValueError("basic block operations must be a non-empty tuple")
        if any(
            not isinstance(
                operation,
                (ReadA, WriteA, WriteDecimal, Halt, BranchZero, Jump, Load, Store, Add, Sub, Mul, Lt, Eq, And, Or, Call, Return),
            )
            for operation in self.operations
        ):
            raise ValueError(f"basic block {self.name} contains an unknown operation")


@dataclass(frozen=True, slots=True)
class Function:
    name: str
    parameters: tuple[str, ...]
    entry_block: str
    blocks: tuple[BasicBlock, ...]

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("function name must not be empty")
        if not isinstance(self.parameters, tuple) or any(
            not isinstance(parameter, str) or not parameter for parameter in self.parameters
        ):
            raise ValueError(f"function {self.name} parameters must be non-empty names")
        if len(set(self.parameters)) != len(self.parameters):
            raise ValueError(f"function {self.name} has duplicate parameters")
        if not self.entry_block:
            raise ValueError(f"function {self.name} must name an entry block")
        if not isinstance(self.blocks, tuple) or not self.blocks:
            raise ValueError(f"function {self.name} must have at least one block")
        names = [block.name for block in self.blocks]
        if len(set(names)) != len(names):
            raise ValueError(f"function {self.name} has duplicate block names")
        if self.entry_block not in names:
            raise ValueError(f"function {self.name} entry block does not exist")
        labels = set(names)
        for block in self.blocks:
            for operation in block.operations:
                if isinstance(operation, Jump) and operation.target not in labels:
                    raise ValueError(f"jump target {operation.target!r} does not exist")
                if isinstance(operation, BranchZero) and (
                    operation.zero_target not in labels
                    or operation.nonzero_target not in labels
                ):
                    raise ValueError("branch-zero targets must name blocks in the function")


@dataclass(frozen=True, slots=True)
class ModuleCase:
    stdin: bytes
    stdout: bytes
    status: str = "HALT"

    def __post_init__(self) -> None:
        if not isinstance(self.stdin, bytes) or not isinstance(self.stdout, bytes):
            raise ValueError("module case input and output must be bytes")
        if self.status != "HALT":
            raise ValueError("module cases currently require the HALT status")


@dataclass(frozen=True, slots=True)
class Module:
    name: str
    entry_function: str
    functions: tuple[Function, ...]
    cases: tuple[ModuleCase, ...]

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("module name must not be empty")
        if not isinstance(self.functions, tuple) or not self.functions:
            raise ValueError("module must contain at least one function")
        if not isinstance(self.cases, tuple) or not self.cases:
            raise ValueError("module must contain at least one input/output case")
        function_names = [function.name for function in self.functions]
        if len(set(function_names)) != len(function_names):
            raise ValueError("module has duplicate function names")
        if self.entry_function not in function_names:
            raise ValueError("module entry function does not exist")
        function_set = set(function_names)
        for function in self.functions:
            for block in function.blocks:
                for operation in block.operations:
                    if isinstance(operation, Call) and operation.function not in function_set:
                        raise ValueError(
                            f"called function {operation.function!r} does not exist"
                        )


@dataclass(frozen=True, slots=True)
class Program:
    name: str
    operations: tuple[Operation, ...]

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("program name must not be empty")
        if not isinstance(self.operations, tuple) or not self.operations:
            raise ValueError("program operations must be a non-empty tuple")
        if any(not isinstance(op, (ReadA, WriteA, Halt)) for op in self.operations):
            raise ValueError("program contains an unknown operation")
        if self.operations[-1] != Halt():
            raise ValueError("program must end with a terminal halt")
        if any(isinstance(op, Halt) for op in self.operations[:-1]):
            raise ValueError("halt may appear only as the terminal operation")

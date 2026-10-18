"""Typed, declarative operations accepted by the fixed-3^19 synthesizer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class ReadA:
    """Read one input byte into accumulator A; EOF uses the profile sentinel."""


@dataclass(frozen=True, slots=True)
class WriteA:
    """Write the low byte of accumulator A to guest stdout."""


@dataclass(frozen=True, slots=True)
class Halt:
    """Terminate the guest normally."""


Operation: TypeAlias = ReadA | WriteA | Halt


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

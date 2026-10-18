"""JSON reader for the small, typed synthesis IR."""

from __future__ import annotations

import json
from pathlib import Path

from .ir import Halt, Operation, Program, ReadA, WriteA


_OPERATION_TYPES: dict[str, type[Operation]] = {
    "read_a": ReadA,
    "write_a": WriteA,
    "halt": Halt,
}


def load_program(path: Path) -> Program:
    """Load a program contract and reject syntax outside the current IR."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not load program {path}: {exc}") from exc
    if not isinstance(data, dict) or set(data) != {"name", "operations"}:
        raise ValueError("program must contain exactly name and operations")
    name = data["name"]
    if not isinstance(name, str) or not name:
        raise ValueError("program name must be a non-empty string")
    raw_operations = data["operations"]
    if not isinstance(raw_operations, list) or not raw_operations:
        raise ValueError("program operations must be a non-empty array")

    operations: list[Operation] = []
    for position, raw_operation in enumerate(raw_operations):
        if not isinstance(raw_operation, dict) or set(raw_operation) != {"op"}:
            raise ValueError(f"operation {position} must contain exactly op")
        operation_name = raw_operation["op"]
        operation_type = _OPERATION_TYPES.get(operation_name) if isinstance(operation_name, str) else None
        if operation_type is None:
            raise ValueError(f"unknown operation at index {position}: {operation_name!r}")
        operations.append(operation_type())
    return Program(name=name, operations=tuple(operations))

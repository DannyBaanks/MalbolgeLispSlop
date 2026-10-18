"""JSON reader for the small, typed synthesis IR."""

from __future__ import annotations

import json
from pathlib import Path

from .ir import (
    Add,
    BasicBlock,
    BranchZero,
    Call,
    Function,
    Halt,
    Jump,
    Load,
    Module,
    ModuleCase,
    ModuleOperation,
    Operation,
    Program,
    ReadA,
    Return,
    Store,
    Sub,
    WriteA,
)


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


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _value_ref(value: object, label: str) -> str | int:
    if isinstance(value, str) and value:
        return value
    if type(value) is int:
        return value
    raise ValueError(f"{label} must be a non-empty name or integer")


def _module_operation(raw: object, label: str) -> ModuleOperation:
    operation = _object(raw, label)
    name = operation.get("op")
    if not isinstance(name, str):
        raise ValueError(f"{label}.op must be a string")

    if name in {"read_a", "write_a", "halt"}:
        if name == "read_a":
            if set(operation) not in ({"op"}, {"op", "destination"}):
                raise ValueError(f"{label} read_a accepts op and optional destination")
            destination = operation.get("destination", "A")
            return ReadA(_string(destination, f"{label}.destination"))
        if name == "write_a":
            if set(operation) not in ({"op"}, {"op", "value"}):
                raise ValueError(f"{label} write_a accepts op and optional value")
            value = operation.get("value", "A")
            return WriteA(_string(value, f"{label}.value"))
        if set(operation) != {"op"}:
            raise ValueError(f"{label} halt operation accepts only the op field")
        return Halt()
    if name == "branch_zero":
        required = {"op", "value", "zero_target", "nonzero_target"}
        if set(operation) != required:
            raise ValueError(f"{label} branch_zero fields must be {sorted(required)}")
        return BranchZero(
            _value_ref(operation["value"], f"{label}.value"),
            _string(operation["zero_target"], f"{label}.zero_target"),
            _string(operation["nonzero_target"], f"{label}.nonzero_target"),
        )
    if name == "jump":
        if set(operation) != {"op", "target"}:
            raise ValueError(f"{label} jump fields must be op and target")
        return Jump(_string(operation["target"], f"{label}.target"))
    if name == "load":
        required = {"op", "destination", "address"}
        if set(operation) != required:
            raise ValueError(f"{label} load fields must be {sorted(required)}")
        return Load(
            _string(operation["destination"], f"{label}.destination"),
            _value_ref(operation["address"], f"{label}.address"),
        )
    if name == "store":
        required = {"op", "address", "value"}
        if set(operation) != required:
            raise ValueError(f"{label} store fields must be {sorted(required)}")
        return Store(
            _value_ref(operation["address"], f"{label}.address"),
            _value_ref(operation["value"], f"{label}.value"),
        )
    if name in {"add", "sub"}:
        required = {"op", "destination", "left", "right"}
        if set(operation) != required:
            raise ValueError(f"{label} {name} fields must be {sorted(required)}")
        constructor = Add if name == "add" else Sub
        return constructor(
            _string(operation["destination"], f"{label}.destination"),
            _value_ref(operation["left"], f"{label}.left"),
            _value_ref(operation["right"], f"{label}.right"),
        )
    if name == "call":
        required = {"op", "function", "arguments"}
        allowed = required | {"destination"}
        if not required <= set(operation) or not set(operation) <= allowed:
            raise ValueError(f"{label} call fields must contain {sorted(required)}")
        raw_arguments = operation["arguments"]
        if not isinstance(raw_arguments, list):
            raise ValueError(f"{label}.arguments must be an array")
        arguments = tuple(
            _value_ref(value, f"{label}.arguments[{index}]")
            for index, value in enumerate(raw_arguments)
        )
        raw_destination = operation.get("destination")
        destination = (
            None
            if raw_destination is None
            else _string(raw_destination, f"{label}.destination")
        )
        return Call(
            _string(operation["function"], f"{label}.function"),
            arguments,
            destination,
        )
    if name == "return":
        if set(operation) not in ({"op"}, {"op", "value"}):
            raise ValueError(f"{label} return accepts op and optional value")
        raw_value = operation.get("value")
        value = None if raw_value is None else _value_ref(raw_value, f"{label}.value")
        return Return(value)
    raise ValueError(f"unknown module operation at {label}: {name!r}")


def load_module(path: Path) -> Module:
    """Load a typed multi-function guest module and its observable cases."""
    try:
        data = _object(json.loads(path.read_text(encoding="utf-8")), "module")
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not load module {path}: {exc}") from exc
    required = {
        "schema_version",
        "name",
        "entry_function",
        "functions",
        "cases",
    }
    if set(data) != required:
        raise ValueError(f"module fields must be {sorted(required)}")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("unsupported module schema_version")

    raw_functions = data["functions"]
    if not isinstance(raw_functions, list) or not raw_functions:
        raise ValueError("module functions must be a non-empty array")
    functions: list[Function] = []
    for function_index, raw_function in enumerate(raw_functions):
        label = f"functions[{function_index}]"
        function_data = _object(raw_function, label)
        function_fields = {"name", "parameters", "entry_block", "blocks"}
        if set(function_data) != function_fields:
            raise ValueError(f"{label} fields must be {sorted(function_fields)}")
        raw_parameters = function_data["parameters"]
        raw_blocks = function_data["blocks"]
        if not isinstance(raw_parameters, list) or not isinstance(raw_blocks, list):
            raise ValueError(f"{label}.parameters and blocks must be arrays")
        blocks: list[BasicBlock] = []
        for block_index, raw_block in enumerate(raw_blocks):
            block_label = f"{label}.blocks[{block_index}]"
            block_data = _object(raw_block, block_label)
            if set(block_data) != {"name", "operations"}:
                raise ValueError(f"{block_label} fields must be name and operations")
            raw_operations = block_data["operations"]
            if not isinstance(raw_operations, list):
                raise ValueError(f"{block_label}.operations must be an array")
            operations = tuple(
                _module_operation(operation, f"{block_label}.operations[{operation_index}]")
                for operation_index, operation in enumerate(raw_operations)
            )
            blocks.append(
                BasicBlock(
                    _string(block_data["name"], f"{block_label}.name"), operations
                )
            )
        functions.append(
            Function(
                _string(function_data["name"], f"{label}.name"),
                tuple(
                    _string(parameter, f"{label}.parameters[{index}]")
                    for index, parameter in enumerate(raw_parameters)
                ),
                _string(function_data["entry_block"], f"{label}.entry_block"),
                tuple(blocks),
            )
        )

    raw_cases = data["cases"]
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("module cases must be a non-empty array")
    cases: list[ModuleCase] = []
    for index, raw_case in enumerate(raw_cases):
        label = f"cases[{index}]"
        case_data = _object(raw_case, label)
        allowed = {"stdin_hex", "stdout_hex", "status"}
        if set(case_data) not in (allowed, allowed - {"status"}):
            raise ValueError(f"{label} fields must be {sorted(allowed)}")
        try:
            stdin = bytes.fromhex(_string(case_data["stdin_hex"], f"{label}.stdin_hex"))
            stdout = bytes.fromhex(_string(case_data["stdout_hex"], f"{label}.stdout_hex"))
        except ValueError as exc:
            raise ValueError(f"{label} contains invalid hexadecimal bytes: {exc}") from exc
        status = case_data.get("status", "HALT")
        cases.append(ModuleCase(stdin, stdout, _string(status, f"{label}.status")))

    return Module(
        _string(data["name"], "module.name"),
        _string(data["entry_function"], "module.entry_function"),
        tuple(functions),
        tuple(cases),
    )

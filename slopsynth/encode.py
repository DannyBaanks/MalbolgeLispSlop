"""Position-aware byte emission for the fixed-3^19 canonical loader."""

from __future__ import annotations

from .ir import Halt, Program, ReadA, WriteA
from .profile import Profile


def encode_program(program: Program, profile: Profile) -> bytes:
    """Encode supported guest operations as canonical Malbolge source bytes.

    Each byte is derived from the profile's dispatch index, printable range,
    and canonical source position. No instruction-byte templates are stored.
    """
    rule = profile.loaders.get("canonical")
    if rule is None or not rule.validate_opcodes or rule.position_cycle is None:
        raise ValueError("profile must define a validated canonical loader")
    modulus = rule.byte_max_exclusive - rule.byte_min
    if modulus <= 0:
        raise ValueError("canonical byte range must not be empty")

    operation_names = {ReadA: "input", WriteA: "output", Halt: "halt"}
    dispatch_names: list[str] = []
    for address, operation in enumerate(program.operations):
        if isinstance(operation, ReadA) and operation.destination != "A":
            raise ValueError("the direct M1 backend can read only into accumulator A")
        if isinstance(operation, WriteA) and operation.value != "A":
            raise ValueError("the direct M1 backend can write only accumulator A")
        operation_name = operation_names.get(type(operation))
        if operation_name is None:
            raise ValueError(f"unsupported guest operation at address {address}")
        dispatch_names.append(operation_name)

    return encode_dispatch_sequence(dispatch_names, profile)


def encode_dispatch_sequence(dispatch_names: list[str] | tuple[str, ...], profile: Profile) -> bytes:
    """Encode a sequence of profile dispatch names for bounded search."""
    rule = profile.loaders.get("canonical")
    if rule is None or not rule.validate_opcodes or rule.position_cycle is None:
        raise ValueError("profile must define a validated canonical loader")
    modulus = rule.byte_max_exclusive - rule.byte_min
    if modulus <= 0:
        raise ValueError("canonical byte range must not be empty")

    image = bytearray()
    valid_opcodes = set(profile.dispatch.values())
    for address, operation_name in enumerate(dispatch_names):
        try:
            opcode = profile.dispatch[operation_name]
        except KeyError as exc:
            raise ValueError(f"profile has no dispatch index for {operation_name}") from exc
        position = address % rule.position_cycle
        byte = rule.byte_min + ((opcode - position - rule.byte_min) % modulus)
        if not rule.byte_min <= byte < rule.byte_max_exclusive:
            raise ValueError(f"encoder produced non-canonical byte at address {address}")
        if byte in rule.whitespace_bytes:
            raise ValueError(f"encoder produced whitespace at address {address}")
        if (byte + position) % modulus != opcode:
            raise ValueError(f"encoder failed to encode opcode at address {address}")
        if opcode not in valid_opcodes:
            raise ValueError(f"profile opcode at address {address} is not dispatchable")
        image.append(byte)

    return bytes(image)

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
    image = bytearray()
    for address, operation in enumerate(program.operations):
        operation_name = operation_names.get(type(operation))
        if operation_name is None:
            raise ValueError(f"unsupported guest operation at address {address}")
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
        image.append(byte)

    return bytes(image)

"""Loader-side acceptance for canonical images, independent of the encoder.

The encoder derives bytes from a dispatch sequence; this module walks an image
the way the loader does and reports where it would abort. The two agree only if
the encoder is correct, so the check is a real control and not a tautology.
"""

from __future__ import annotations

from dataclasses import dataclass

from .profile import Profile


@dataclass(frozen=True, slots=True)
class CanonicalWalk:
    """Result of replaying the canonical loader over an image.

    ``accepted_cells`` counts cells the loader would create; whitespace is
    skipped without advancing the position, matching the loader's own walk.
    ``opcodes`` are the profile dispatch indices the loader would decode, in
    cell order, so a caller can compare them against what it meant to emit.
    """

    accepted_cells: int
    opcodes: tuple[int, ...]
    rejected_byte: int | None
    rejected_offset: int | None
    reason: str | None

    @property
    def accepted(self) -> bool:
        return self.rejected_byte is None


def canonical_accept_set(profile: Profile) -> frozenset[int]:
    """Opcode indices the canonical loader recognizes for this profile."""
    rule = profile.loaders.get("canonical")
    if rule is None or not rule.validate_opcodes or rule.position_cycle is None:
        raise ValueError("profile must define a validated canonical loader")
    return frozenset(profile.dispatch.values())


def walk_canonical(image: bytes, profile: Profile) -> CanonicalWalk:
    """Replay the canonical loader rule over ``image`` and report the outcome."""
    rule = profile.loaders.get("canonical")
    if rule is None or not rule.validate_opcodes or rule.position_cycle is None:
        raise ValueError("profile must define a validated canonical loader")

    modulus = rule.byte_max_exclusive - rule.byte_min
    accept = canonical_accept_set(profile)
    whitespace = set(rule.whitespace_bytes)

    position = 0
    opcodes: list[int] = []
    for offset, byte in enumerate(image):
        if byte in whitespace:
            continue
        if not rule.byte_min <= byte < rule.byte_max_exclusive:
            return CanonicalWalk(
                accepted_cells=len(opcodes),
                opcodes=tuple(opcodes),
                rejected_byte=byte,
                rejected_offset=offset,
                reason=(
                    f"byte {byte} at offset {offset} is outside the printable range "
                    f"[{rule.byte_min}, {rule.byte_max_exclusive})"
                ),
            )
        opcode = (byte + position) % modulus
        if opcode not in accept:
            return CanonicalWalk(
                accepted_cells=len(opcodes),
                opcodes=tuple(opcodes),
                rejected_byte=byte,
                rejected_offset=offset,
                reason=(
                    f"byte {byte} at offset {offset} decodes to opcode {opcode}, "
                    "which is not dispatchable"
                ),
            )
        opcodes.append(opcode)
        position = (position + 1) % rule.position_cycle

    return CanonicalWalk(
        accepted_cells=len(opcodes),
        opcodes=tuple(opcodes),
        rejected_byte=None,
        rejected_offset=None,
        reason=None,
    )


def opcode_names(opcodes: tuple[int, ...], profile: Profile) -> tuple[str, ...]:
    """Name each decoded opcode with the profile's own dispatch labels."""
    names = {index: name for name, index in profile.dispatch.items()}
    return tuple(names.get(opcode, f"unknown-{opcode}") for opcode in opcodes)

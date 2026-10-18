"""Bounded transition model for the repository's fixed-3^19 ``bolge19`` VM."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .profile import Profile


_PAGE_SIZE = 65_536
_CRAZY_TABLE = ((1, 0, 0), (1, 0, 2), (2, 2, 1))
_TRANSLATION = (
    "SOMEBODY MAKE ME FEEL ALIVE"
    "[hj9>,5z]&gqtyfr$(we4{WP)H-Zn,[%\\3dL+Q;>U!pJS72FhOA1CB6v^=I_0/8|jsb9m<.TVac`uY*MK'X~xDl}REokN:#?G\"i@"
    "AND SHATTER ME"
)


class RunStatus(str, Enum):
    HALT = "HALT"
    MAX_STEPS = "MAX_STEPS"
    LOAD_ERROR = "LOAD_ERROR"
    MODEL_BOUND = "MODEL_BOUND"


@dataclass(frozen=True, slots=True)
class MemoryWrite:
    address: int
    before: int
    after: int
    step: int = 0


@dataclass(frozen=True, slots=True)
class MemoryAccess:
    address: int
    purpose: str
    step: int = 0


@dataclass(frozen=True, slots=True)
class InstructionEvent:
    address: int
    operation: str
    data_address: int | None
    step: int = 0


@dataclass(frozen=True, slots=True)
class RunResult:
    stdout: bytes
    status: RunStatus
    steps: int
    final_a: int
    final_c: int
    final_d: int
    memory_writes: tuple[MemoryWrite, ...] = ()
    instruction_trace: tuple[InstructionEvent, ...] = ()
    memory_accesses: tuple[MemoryAccess, ...] = ()


class _ModelBound(Exception):
    pass


def _crazy(a_value: int, d_value: int, trits: int) -> int:
    result = 0
    place = 1
    a = a_value
    d = d_value
    for _ in range(trits):
        result += place * _CRAZY_TABLE[d % 3][a % 3]
        a //= 3
        d //= 3
        place *= 3
    return result


def _rotate(value: int, end: int) -> int:
    third = end // 3
    low = value % third
    low_trit = low % 3
    quotient = low // 3
    return quotient + low_trit * (third // 3) + (value - low)


def _dispatch_offsets(end: int) -> tuple[int, int, int]:
    third = end // 3
    first = 94 - (((end - 1) // 6 - 29_524) % 94)
    second = 94 - (((end - 1) // 3 - 59_048) % 94)
    offset_one = ((first - third) % 94) + 94
    offset_two = second - ((2 * third) % 94) + 94
    return 0, offset_one, offset_two


def _load_image(image: bytes, profile: Profile, loader: str) -> list[int] | None:
    rule = profile.loaders.get(loader)
    if rule is None or not image or len(image) > profile.end:
        return None

    valid_opcodes = set(profile.dispatch.values())
    cells: list[int] = []
    position = 0
    for byte in image:
        if rule.skip_whitespace and byte in rule.whitespace_bytes:
            continue
        if rule.validate_opcodes:
            if not rule.byte_min <= byte < rule.byte_max_exclusive:
                return None
            opcode_index = (byte + position) % (rule.byte_max_exclusive - rule.byte_min)
            if opcode_index not in valid_opcodes:
                return None
        cells.append(byte)
        if rule.position_cycle is not None:
            position = (position + 1) % rule.position_cycle
    return cells


class _Memory:
    def __init__(
        self,
        image: list[int],
        profile: Profile,
        max_address: int,
        writes: list[MemoryWrite] | None,
        accesses: list[MemoryAccess] | None,
    ) -> None:
        self.image = image
        self.profile = profile
        self.max_address = max_address
        self.overlay: dict[int, int] = {}
        self.writes = writes
        self.accesses = accesses
        self.current_step = 0
        self.zone_start = ((len(image) + _PAGE_SIZE - 1) // _PAGE_SIZE) * _PAGE_SIZE
        self.chain: list[int] = []
        self.p2 = image[-2] if len(image) >= 2 else 0
        self.p1 = image[-1] if image else 0
        self.pattern: tuple[int, ...] | None = None

    def _check_address(self, address: int) -> None:
        if address < 0 or address > self.max_address or address >= self.profile.end:
            raise _ModelBound

    def _extend_chain(self, count: int) -> None:
        while len(self.chain) < count:
            next_value = _crazy(self.p1, self.p2, self.profile.trits)
            self.chain.append(next_value)
            self.p2, self.p1 = self.p1, next_value

    def _ensure_pattern(self) -> None:
        if self.pattern is not None:
            return
        self._extend_chain(self.zone_start - len(self.image))
        values: list[int] = []
        for _ in range(6):
            next_value = _crazy(self.p1, self.p2, self.profile.trits)
            values.append(next_value)
            self.p2, self.p1 = self.p1, next_value
        self.pattern = tuple(values)

    def get(self, address: int, purpose: str = "data") -> int:
        self._check_address(address)
        if self.accesses is not None:
            self.accesses.append(MemoryAccess(address, purpose, self.current_step))
        if address < len(self.image):
            return self.image[address]
        if address in self.overlay:
            return self.overlay[address]
        if address < self.zone_start:
            self._extend_chain(address - len(self.image) + 1)
            return self.chain[address - len(self.image)]
        self._ensure_pattern()
        page_base = address & ~(_PAGE_SIZE - 1)
        third = self.profile.end // 3
        phase = (page_base % third + address - page_base) % 6
        return self.pattern[phase]  # type: ignore[index]

    def set(self, address: int, value: int) -> None:
        self._check_address(address)
        before = self.get(address, "write_before")
        if address < len(self.image):
            self.image[address] = value
        else:
            self.overlay[address] = value
        if self.writes is not None:
            self.writes.append(MemoryWrite(address, before, value, self.current_step))


def _result(
    stdout: bytearray,
    status: RunStatus,
    steps: int,
    a: int,
    c: int,
    d: int,
    writes: list[MemoryWrite] | None,
    instructions: list[InstructionEvent] | None,
    accesses: list[MemoryAccess] | None,
) -> RunResult:
    return RunResult(
        stdout=bytes(stdout),
        status=status,
        steps=steps,
        final_a=a,
        final_c=c,
        final_d=d,
        memory_writes=tuple(writes) if writes is not None else (),
        instruction_trace=tuple(instructions) if instructions is not None else (),
        memory_accesses=tuple(accesses) if accesses is not None else (),
    )


def run_model(
    image: bytes,
    stdin: bytes,
    profile: Profile,
    *,
    loader: str,
    max_steps: int,
    max_address: int,
    trace_writes: bool = False,
    trace_instructions: bool = False,
    trace_accesses: bool = False,
) -> RunResult:
    """Run a byte-oriented fixed-profile image within explicit model bounds.

    ``max_address`` is inclusive. It limits all guest memory reads and writes;
    exceeding it returns ``MODEL_BOUND`` rather than assuming the bound is the
    VM's complete memory.
    """
    if max_steps <= 0:
        raise ValueError("max_steps must be positive")
    if not 0 <= max_address < profile.end:
        raise ValueError("max_address must be inside the target profile")

    memory_image = _load_image(image, profile, loader)
    if memory_image is None:
        return RunResult(b"", RunStatus.LOAD_ERROR, 0, 0, 0, 0)

    writes: list[MemoryWrite] | None = [] if trace_writes else None
    instructions: list[InstructionEvent] | None = [] if trace_instructions else None
    accesses: list[MemoryAccess] | None = [] if trace_accesses else None
    memory = _Memory(memory_image, profile, max_address, writes, accesses)
    stdout = bytearray()
    a = 0
    c = 0
    d = 0
    steps = 0
    input_position = 0
    third = profile.end // 3
    dispatch = {value: name for name, value in profile.dispatch.items()}
    offsets = _dispatch_offsets(profile.end)
    opcode_modulus = (
        profile.loaders["canonical"].byte_max_exclusive
        - profile.loaders["canonical"].byte_min
    )

    while True:
        if steps >= max_steps:
            return _result(
                stdout, RunStatus.MAX_STEPS, steps, a, c, d, writes, instructions, accesses
            )
        try:
            memory.current_step = steps
            region = c // third
            offset = offsets[region] if region < 3 else 0
            opcode_index = (c + memory.get(c, "instruction") + offset) % opcode_modulus
            operation = dispatch.get(opcode_index)
            operation_name = operation or "invalid"
            data_address = int(d) if operation in {"jump", "rotate", "move", "crazy"} else None
            if instructions is not None:
                instructions.append(
                    InstructionEvent(int(c), operation_name, data_address, steps)
                )

            if operation == "halt":
                return _result(
                    stdout, RunStatus.HALT, steps, a, c, d, writes, instructions, accesses
                )
            if operation == "jump":
                c = memory.get(d, "jump_target")
            elif operation == "output":
                stdout.append(a & 0xFF)
            elif operation == "input":
                if input_position < len(stdin):
                    a = stdin[input_position]
                    input_position += 1
                else:
                    a = profile.eof_value
            elif operation == "rotate":
                rotated = _rotate(memory.get(d, "rotate_source"), profile.end)
                memory.set(d, rotated)
                a = rotated
            elif operation == "move":
                d = memory.get(d, "move_source")
            elif operation == "crazy":
                transformed = _crazy(a, memory.get(d, "crazy_source"), profile.trits)
                memory.set(d, transformed)
                a = transformed

            encoded_cell = memory.get(c, "encryption")
            if encoded_cell < len(_TRANSLATION):
                memory.set(c, ord(_TRANSLATION[encoded_cell]))
            c = (c + 1) % profile.end
            d = (d + 1) % profile.end
            steps += 1
        except _ModelBound:
            return _result(
                stdout, RunStatus.MODEL_BOUND, steps, a, c, d, writes, instructions, accesses
            )

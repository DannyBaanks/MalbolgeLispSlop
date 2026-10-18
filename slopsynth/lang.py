"""Textual front-end for the fixed-3^19 guest language.

Two shapes parse. A *straight-line guest* is the subset the certified lowering
actually emits today: ``read``, ``write`` and ``halt``, optionally annotated with
labels and absolute-address anchors. A *module* carries control flow: it parses
into the same typed IR the search back-end uses, but nothing lowers it, so the
assembler must refuse to emit rather than invent bytes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TypeAlias

from .ir import (
    Add,
    BasicBlock,
    BranchZero,
    Function,
    Halt,
    Jump,
    Load,
    Module,
    ModuleCase,
    Operation,
    Program,
    ReadA,
    Store,
    Sub,
    ValueRef,
    WriteA,
)

MAX_LINE = 4096
MAX_ADDRESS = 1_162_261_467
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
_INTEGER_RE = re.compile(r"^-?(0|[1-9][0-9]*)$")
_HEX_RE = re.compile(r"^[0-9A-Fa-f]*$")
_MODULE_MNEMONICS = frozenset({"jump", "brz", "ld", "st", "add", "sub"})
_DECLINED_MNEMONICS = frozenset({"call", "ret", "return"})


class LangError(ValueError):
    """A diagnostic tied to one source line of a guest text."""

    def __init__(self, line: int, message: str) -> None:
        super().__init__(f"line {line}: {message}")
        self.line = line
        self.message = message


@dataclass(frozen=True, slots=True)
class Placed:
    """A parsed guest plus the placement annotations the front-end collected.

    ``labels`` and ``anchors`` are keyed by operation index: a label records the
    address its operation will occupy, an anchor demands an absolute address.
    They are only meaningful for a straight-line guest, which is what
    :mod:`slopsynth.assemble` emits.
    """

    name: str
    program: Program | None
    module: Module | None
    labels: tuple[tuple[int, str], ...] = ()
    anchors: tuple[tuple[int, int], ...] = ()

    @property
    def operations(self) -> tuple[Operation, ...]:
        if self.program is not None:
            return self.program.operations
        assert self.module is not None
        return tuple(
            operation
            for function in self.module.functions
            for block in function.blocks
            for operation in block.operations
        )


Parsed: TypeAlias = Program | Module


def _strip_comment(text: str) -> str:
    return text.split(";", 1)[0].strip()


def _is_identifier(value: str) -> bool:
    return bool(_NAME_RE.match(value))


def _parse_value(token: str, line: int, role: str) -> ValueRef:
    if _INTEGER_RE.match(token):
        return int(token)
    if _is_identifier(token):
        return token
    raise LangError(line, f"{role} must be an identifier or an integer, got {token!r}")


def _parse_bytes(token: str, line: int, role: str) -> bytes:
    if not _HEX_RE.match(token):
        raise LangError(line, f"{role} must be a hex string, got {token!r}")
    if len(token) % 2:
        raise LangError(line, f"{role} must have an even number of hex digits")
    return bytes.fromhex(token)


def _split_operands(operand_text: str, line: int) -> list[str]:
    if not operand_text:
        return []
    parts = [part.strip() for part in operand_text.split(",")]
    if any(not part for part in parts):
        raise LangError(line, "operands must be comma separated and non-empty")
    return parts


def _parse_operation(mnemonic: str, operands: list[str], line: int) -> object:
    if mnemonic == "read":
        if len(operands) > 1:
            raise LangError(line, "read takes at most one destination")
        destination = operands[0] if operands else "A"
        if not _is_identifier(destination):
            raise LangError(line, f"read destination must be an identifier, got {destination!r}")
        return ReadA(destination=destination)
    if mnemonic == "write":
        if len(operands) > 1:
            raise LangError(line, "write takes at most one value")
        value = operands[0] if operands else "A"
        return WriteA(value=_parse_value(value, line, "write value"))
    if mnemonic == "halt":
        if operands:
            raise LangError(line, "halt takes no operands")
        return Halt()
    if mnemonic == "jump":
        if len(operands) != 1 or not _is_identifier(operands[0]):
            raise LangError(line, "jump takes one label")
        return Jump(target=operands[0])
    if mnemonic == "brz":
        if len(operands) != 3:
            raise LangError(line, "brz takes a value, a zero label and a nonzero label")
        if not _is_identifier(operands[1]) or not _is_identifier(operands[2]):
            raise LangError(line, "brz targets must be labels")
        return BranchZero(
            value=_parse_value(operands[0], line, "brz value"),
            zero_target=operands[1],
            nonzero_target=operands[2],
        )
    if mnemonic == "ld":
        if len(operands) != 2 or not _is_identifier(operands[0]):
            raise LangError(line, "ld takes an identifier destination and one address")
        return Load(destination=operands[0], address=_parse_value(operands[1], line, "address"))
    if mnemonic == "st":
        if len(operands) != 2:
            raise LangError(line, "st takes one address and one value")
        return Store(
            address=_parse_value(operands[0], line, "address"),
            value=_parse_value(operands[1], line, "stored value"),
        )
    if mnemonic in ("add", "sub"):
        if len(operands) != 3 or not _is_identifier(operands[0]):
            raise LangError(line, f"{mnemonic} takes an identifier destination and two values")
        left = _parse_value(operands[1], line, "left operand")
        right = _parse_value(operands[2], line, "right operand")
        return (
            Add(destination=operands[0], left=left, right=right)
            if mnemonic == "add"
            else Sub(destination=operands[0], left=left, right=right)
        )
    raise LangError(line, f"unknown mnemonic {mnemonic!r}")


def parse_placed(text: str) -> Placed:
    """Parse guest source into a :class:`Placed` document.

    Raises :class:`LangError` with the offending line number for every rejected
    form; nothing in this function invents a lowering for an operation the IR
    cannot already carry.
    """
    name: str | None = None
    entry: str | None = None
    cases: list[ModuleCase] = []
    operations: list[object] = []
    label_positions: list[tuple[int, str]] = []
    anchor_positions: list[tuple[int, int]] = []
    pending_labels: list[str] = []
    pending_anchor: int | None = None
    control_flow = False

    for number, raw_line in enumerate(text.splitlines(), start=1):
        if len(raw_line) > MAX_LINE:
            raise LangError(number, f"line exceeds {MAX_LINE} characters")
        statement = _strip_comment(raw_line)
        if not statement:
            continue
        head, _, rest = statement.partition(" ")
        head = head.lower()
        operands = _split_operands(rest.strip(), number)

        if head == "name":
            if name is not None:
                raise LangError(number, "name may appear only once")
            if len(operands) != 1 or not _is_identifier(operands[0]):
                raise LangError(number, "name takes one identifier")
            name = operands[0]
            continue
        if head == "at":
            if len(operands) != 1 or not _INTEGER_RE.match(operands[0]):
                raise LangError(number, "at takes one absolute cell address")
            address = int(operands[0])
            if not 0 <= address < MAX_ADDRESS:
                raise LangError(number, f"address {address} is outside the 3^19 tape")
            if pending_anchor is not None:
                raise LangError(number, "an address was already pending for this operation")
            pending_anchor = address
            continue
        if head == "entry":
            if len(operands) != 1 or not _is_identifier(operands[0]):
                raise LangError(number, "entry takes one label")
            entry = operands[0]
            control_flow = True
            continue
        if head == "case":
            if len(operands) != 2:
                raise LangError(number, "case takes an input hex string and an output hex string")
            cases.append(
                ModuleCase(
                    stdin=_parse_bytes(operands[0], number, "case input"),
                    stdout=_parse_bytes(operands[1], number, "case output"),
                )
            )
            control_flow = True
            continue
        if head.endswith(":") and not operands:
            label = head[:-1]
            if not _is_identifier(label):
                raise LangError(number, f"invalid label {label!r}")
            if any(label == known for _, known in label_positions):
                raise LangError(number, f"label {label!r} is already defined")
            pending_labels.append(label)
            continue

        if head in _DECLINED_MNEMONICS:
            raise LangError(
                number,
                f"{head} is not accepted by this front-end; the IR has no lowering for it",
            )

        operation = _parse_operation(head, operands, number)
        if head in _MODULE_MNEMONICS:
            control_flow = True
        index = len(operations)
        if pending_anchor is not None:
            anchor_positions.append((index, pending_anchor))
            pending_anchor = None
        for label in pending_labels:
            label_positions.append((index, label))
        pending_labels.clear()
        operations.append(operation)

    if pending_labels or pending_anchor is not None:
        raise LangError(0, "a label or address was left without an operation after it")
    if name is None:
        raise LangError(0, "source has no name directive")
    if not operations:
        raise LangError(0, "source has no operations")

    if not control_flow:
        typed: list[Operation] = []
        for operation in operations:
            if not isinstance(operation, (ReadA, WriteA, Halt)):
                raise LangError(0, "straight-line guests allow only read, write and halt")
            typed.append(operation)
        return Placed(
            name=name,
            program=Program(name=name, operations=tuple(typed)),
            module=None,
            labels=tuple(label_positions),
            anchors=tuple(anchor_positions),
        )

    if anchor_positions:
        raise LangError(0, "at anchors a straight-line guest, not a module")
    if not label_positions:
        raise LangError(0, "a module needs at least one labeled block")
    if label_positions[0][0] != 0:
        raise LangError(0, "operations before the first label are not allowed in a module")
    starts = [index for index, _ in label_positions]
    if len(set(starts)) != len(starts):
        raise LangError(0, "two labels cannot start the same block")
    if not cases:
        raise LangError(0, "a module needs at least one case directive")
    if entry is None:
        raise LangError(0, "a module needs an entry label")

    basic_blocks: list[BasicBlock] = []
    for position, (start, label) in enumerate(label_positions):
        end = label_positions[position + 1][0] if position + 1 < len(label_positions) else len(
            operations
        )
        block_operations = operations[start:end]
        if not block_operations:
            raise LangError(0, f"block {label!r} is empty")
        for operation in block_operations:
            if not isinstance(
                operation,
                (ReadA, WriteA, Halt, BranchZero, Jump, Load, Store, Add, Sub),
            ):
                raise LangError(0, f"{operation!r} cannot be a module operation")
        basic_blocks.append(BasicBlock(name=label, operations=tuple(block_operations)))

    try:
        function = Function(
            name="main",
            parameters=(),
            entry_block=entry,
            blocks=tuple(basic_blocks),
        )
        module = Module(
            name=name,
            entry_function=function.name,
            functions=(function,),
            cases=tuple(cases),
        )
    except ValueError as exc:
        raise LangError(0, f"module is not well formed: {exc}") from exc
    return Placed(name=name, program=None, module=module)


def parse(text: str) -> Parsed:
    """Parse guest source and return just its IR shape."""
    placed = parse_placed(text)
    if placed.program is not None:
        return placed.program
    assert placed.module is not None
    return placed.module


def format_placed(placed: Placed) -> str:
    """Render a parsed document back to source; ``parse_placed`` must accept it."""
    lines = [f"name {placed.name}"]
    labels_by_index = {}
    for index, label in placed.labels:
        labels_by_index.setdefault(index, []).append(label)
    anchors_by_index = {index: address for index, address in placed.anchors}

    if placed.program is None:
        assert placed.module is not None
        for case in placed.module.cases:
            lines.append(f"case {case.stdin.hex()},{case.stdout.hex()}")
        lines.append(f"entry {placed.module.functions[0].entry_block}")
        for function in placed.module.functions:
            for block in function.blocks:
                lines.append(f"{block.name}:")
                lines.extend(f"    {line}" for line in _format_operations(block.operations))
        return "\n".join(lines) + "\n"

    for index, operation in enumerate(placed.program.operations):
        for label in labels_by_index.get(index, ()):
            lines.append(f"{label}:")
        if index in anchors_by_index:
            lines.append(f"at {anchors_by_index[index]}")
        lines.extend(_format_operations((operation,)))
    return "\n".join(lines) + "\n"


def _format_operations(operations: tuple[object, ...]) -> list[str]:
    lines: list[str] = []
    for operation in operations:
        if isinstance(operation, ReadA):
            lines.append("read" if operation.destination == "A" else f"read {operation.destination}")
        elif isinstance(operation, WriteA):
            lines.append("write" if operation.value == "A" else f"write {operation.value}")
        elif isinstance(operation, Halt):
            lines.append("halt")
        elif isinstance(operation, Jump):
            lines.append(f"jump {operation.target}")
        elif isinstance(operation, BranchZero):
            lines.append(
                f"brz {operation.value},{operation.zero_target},{operation.nonzero_target}"
            )
        elif isinstance(operation, Load):
            lines.append(f"ld {operation.destination},{operation.address}")
        elif isinstance(operation, Store):
            lines.append(f"st {operation.address},{operation.value}")
        elif isinstance(operation, Add):
            lines.append(f"add {operation.destination},{operation.left},{operation.right}")
        elif isinstance(operation, Sub):
            lines.append(f"sub {operation.destination},{operation.left},{operation.right}")
        else:  # pragma: no cover - the IR type already rejects anything else
            raise LangError(0, f"cannot render operation {operation!r}")
    return lines


def format_program(program: Program) -> str:
    """Render a straight-line program back to source."""
    return format_placed(
        Placed(name=program.name, program=program, module=None)
    )

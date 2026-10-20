"""Scoped H9 v2 lowering: fixed-frame single-digit addition with decimal output."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .assemble import AssemblyError, format_image
from .canonical import CanonicalWalk, walk_canonical
from .ir import Add, Halt, Module, ReadA, Sub, WriteDecimal
from .profile import Profile, load_profile
from ._native_eval_add import build_native_digit_adder

_FRAME = re.compile(rb"\(\+ ([0-9]) ([0-9])\)(?:\n|\r\n)?")
LOWERING = "fixed19-framed-digit-add-v2"


@dataclass(frozen=True, slots=True)
class EvalAddImage:
    image: bytes
    walk: CanonicalWalk
    labels: tuple[tuple[str, tuple[int, ...]], ...]
    lowering: str = LOWERING

    @property
    def cells(self) -> int:
        return self.walk.accepted_cells


def lower_eval_add(
    module: Module,
    profile: Profile,
    *,
    line_width: int | None = None,
) -> EvalAddImage:
    """Compile only the explicit framed digit-adder module.

    The grammar is exactly '(+ a b)' with one decimal digit per operand and
    optional LF/CRLF, followed by EOF. Output is decimal ASCII 0..18. Invalid
    frames up to nine bytes halt without output. Longer/streamed inputs are
    outside this backend's contract. This does not lower arbitrary Lisp/IR.
    """
    bundled = load_profile(
        Path(__file__).resolve().parents[1] / "profiles/fixed19.json"
    )
    if profile != bundled:
        raise AssemblyError("H9 v2 requires the exact bundled fixed19 profile")
    if len(module.functions) != 1:
        raise AssemblyError("H9 v2 requires one parameterless function and one block")
    function = module.functions[0]
    if function.parameters or len(function.blocks) != 1:
        raise AssemblyError("H9 v2 requires one parameterless function and one block")
    block = function.blocks[0]
    ops = block.operations
    if (
        len(ops) != 11
        or not all(isinstance(op, ReadA) for op in ops[:7])
        or not (
            isinstance(ops[7], Add)
            and isinstance(ops[8], Sub)
            and isinstance(ops[9], WriteDecimal)
            and isinstance(ops[10], Halt)
        )
    ):
        raise AssemblyError(
            "H9 v2 requires seven reads, add, sub 96, write_decimal, halt; the v1 byte-output template is unsupported"
        )
    destinations = [op.destination for op in ops[:9]]
    if not all(isinstance(name, str) and name for name in destinations) or len(set(destinations)) != len(destinations):
        raise AssemblyError("H9 v2 requires distinct read and arithmetic destinations")
    if {ops[7].left, ops[7].right} != {ops[3].destination, ops[5].destination}:
        raise AssemblyError(
            "H9 v2 add operands must be the fourth and sixth input bytes"
        )
    if ops[8].left != ops[7].destination or ops[8].right != 96:
        raise AssemblyError("H9 v2 must subtract 96 from the ASCII operand sum")
    if ops[9].value != ops[8].destination:
        raise AssemblyError("H9 v2 decimal output must use the subtraction result")
    for case in module.cases:
        if len(case.stdin) > 9:
            raise AssemblyError(
                "H9 v2 input cases must fit the nine-byte frame contract"
            )
        match = _FRAME.fullmatch(case.stdin)
        expected = str(int(match[1]) + int(match[2])).encode("ascii") if match else b""
        if case.stdout != expected:
            raise AssemblyError(
                "declared case contradicts H9 v2 framed digit-add semantics"
            )

    raw, bases, reads = build_native_digit_adder()
    image = format_image(raw, line_width)
    walk = walk_canonical(image, profile)
    if not walk.accepted or walk.accepted_cells != len(raw):
        raise AssemblyError("H9 v2 generated a non-canonical image")
    return EvalAddImage(
        image,
        walk,
        (
            (block.name, (99,)),
            ("input_bytes", reads),
            ("valid_frame", (bases[0] + 2,)),
            ("decimal_output", (bases[1] + 1, len(raw) - 61)),
        ),
    )

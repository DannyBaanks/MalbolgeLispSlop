"""H9 v3 lowering: framed digit arithmetic compiled from the IR to a ternary adder.

The frame is still `(+ a b)` with optional LF/CRLF and EOF, at most nine bytes.
What changes against v2 is the body: every Add, Sub and WriteDecimal of the IR is
lowered to VM arithmetic (`_native_eval_add_v3`). A different IR produces a
different image, and interval analysis rejects programs whose values could leave
the adder width or the decimal output domain.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .assemble import AssemblyError, format_image
from .canonical import CanonicalWalk, walk_canonical
from .ir import Add, Halt, Module, ReadA, Sub, WriteDecimal
from .profile import Profile, load_profile
from ._native_eval_add_v3 import (
    DIGIT_POSITIONS,
    FRAME,
    WIDTH,
    Step,
    build_native_program_v3,
    rounds_for,
)

_FRAME = re.compile(rb"\(\+ ([0-9]) ([0-9])\)(?:\n|\r\n)?")
LOWERING = "fixed19-framed-ternary-adder-v3"
DECIMAL_MAX = 19


@dataclass(frozen=True, slots=True)
class EvalAddImageV3:
    image: bytes
    walk: CanonicalWalk
    labels: tuple[tuple[str, tuple[int, ...]], ...]
    steps: tuple[Step, ...]
    lowering: str = LOWERING

    @property
    def cells(self) -> int:
        return self.walk.accepted_cells


def _ops(module: Module):
    if len(module.functions) != 1:
        raise AssemblyError("H9 v3 requires one parameterless function and one block")
    function = module.functions[0]
    if function.parameters or len(function.blocks) != 1:
        raise AssemblyError("H9 v3 requires one parameterless function and one block")
    ops = function.blocks[0].operations
    if len(ops) < 9 or not all(isinstance(op, ReadA) for op in ops[:7]):
        raise AssemblyError("H9 v3 requires the seven frame reads first")
    if any(isinstance(op, ReadA) for op in ops[7:]):
        raise AssemblyError("H9 v3 reads only the seven frame bytes")
    if not (isinstance(ops[-2], WriteDecimal) and isinstance(ops[-1], Halt)):
        raise AssemblyError("H9 v3 must end with write_decimal and halt")
    if any(isinstance(op, (WriteDecimal, Halt)) for op in ops[7:-2]):
        raise AssemblyError("H9 v3 writes exactly once, at the end")
    return ops


def plan(module: Module) -> tuple[dict[str, int], tuple[Step, ...]]:
    """Check the IR with interval analysis and lower it to adder steps."""
    ops = _ops(module)
    reads: dict[str, int] = {}
    ranges: dict[str, tuple[int, int]] = {}
    for position, op in enumerate(ops[:7]):
        if op.destination in reads:
            raise AssemblyError(f"H9 v3 read destination {op.destination!r} is reused")
        reads[op.destination] = position
        if position in DIGIT_POSITIONS:
            ranges[op.destination] = (48, 57)
        else:
            ranges[op.destination] = (FRAME[position], FRAME[position])

    def interval(ref):
        if isinstance(ref, bool) or not isinstance(ref, (str, int)):
            raise AssemblyError(f"H9 v3 operand {ref!r} is not a name or integer")
        if isinstance(ref, int):
            if not 0 <= ref < 3**WIDTH:
                raise AssemblyError(f"H9 v3 constant {ref} is outside 0..{3**WIDTH - 1}")
            return ref, ref
        if ref not in ranges:
            raise AssemblyError(f"H9 v3 operand {ref!r} is used before it is defined")
        return ranges[ref]

    steps = []
    for op in ops[7:-2]:
        if not isinstance(op, (Add, Sub)):
            raise AssemblyError(f"H9 v3 cannot lower {type(op).__name__}")
        if op.destination in ranges:
            raise AssemblyError(f"H9 v3 destination {op.destination!r} is reused")
        lo_l, hi_l = interval(op.left)
        lo_r, hi_r = interval(op.right)
        if isinstance(op.left, int):
            raise AssemblyError("H9 v3 needs a named left operand")
        if isinstance(op, Add):
            lo, hi = lo_l + lo_r, hi_l + hi_r
            if hi >= 3**WIDTH:
                raise AssemblyError(f"H9 v3 sum {op.destination!r} may reach {hi} (>= {3**WIDTH})")
            steps.append(Step("add", op.destination, op.left, op.right, rounds_for(hi)))
        else:
            if not isinstance(op.right, int):
                raise AssemblyError("H9 v3 subtracts only integer constants")
            if lo_l < op.right:
                raise AssemblyError(f"H9 v3 difference {op.destination!r} may be negative")
            lo, hi = lo_l - op.right, hi_l - op.right
            steps.append(
                Step("sub_const", op.destination, op.left, op.right, rounds_for(hi_l + 3**WIDTH - op.right))
            )
        ranges[op.destination] = (lo, hi)
    out = ops[-2].value
    lo, hi = interval(out)
    if hi > DECIMAL_MAX:
        raise AssemblyError(f"H9 v3 decimal output {out!r} may reach {hi} (> {DECIMAL_MAX})")
    steps.append(Step("write_decimal", None, out))
    return reads, tuple(steps)


def reference(module: Module, stdin: bytes) -> bytes:
    """Host semantics of the IR on one input, independent of the circuit."""
    match = _FRAME.fullmatch(stdin) if len(stdin) <= 9 else None
    if not match:
        return b""
    ops = _ops(module)
    env = {op.destination: stdin[i] for i, op in enumerate(ops[:7])}
    value = lambda ref: ref if isinstance(ref, int) else env[ref]
    for op in ops[7:-2]:
        env[op.destination] = value(op.left) + value(op.right) if isinstance(op, Add) else value(op.left) - value(op.right)
    return str(value(ops[-2].value)).encode("ascii")


def lower_eval_add_v3(module: Module, profile: Profile, *, line_width: int | None = None) -> EvalAddImageV3:
    bundled = load_profile(Path(__file__).resolve().parents[1] / "profiles/fixed19.json")
    if profile != bundled:
        raise AssemblyError("H9 v3 requires the exact bundled fixed19 profile")
    reads, steps = plan(module)
    for case in module.cases:
        if len(case.stdin) > 9:
            raise AssemblyError("H9 v3 input cases must fit the nine-byte frame contract")
        if case.stdout != reference(module, case.stdin):
            raise AssemblyError("declared case contradicts the IR semantics")
    raw, bases, input_sites = build_native_program_v3(reads, steps)
    image = format_image(raw, line_width)
    walk = walk_canonical(image, profile)
    if not walk.accepted or walk.accepted_cells != len(raw):
        raise AssemblyError("H9 v3 generated a non-canonical image")
    return EvalAddImageV3(
        image,
        walk,
        (
            ("input_bytes", input_sites),
            ("valid_frame", (bases[0] + 2,)),
            ("decimal_output", (bases[1] + 1, len(raw) - 61)),
        ),
        steps,
    )

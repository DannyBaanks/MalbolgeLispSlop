"""H13a: a native fixed19 loop whose body is executed again on every iteration.

The image is one loop, `input; output; jump back`, laid out once. It echoes one
byte per iteration for as many iterations as stdin has bytes. Nothing is
unrolled: the same 82 cells run every time (see `cycles.py` for why they survive).

Layout (addresses):

    0..42     inert cells; C and D both walk up from 0, so the first pass
              enters the loop with D = C
    43, 47    input pair          60, 64    move pair
    119, 123  output pair         124       jump (lands on 42, continues at 43)
    130..160  six data bytes: jump targets and D pointers

A pass is the cells 43..124. On even passes the first cell of each pair runs, on
odd passes the second, four steps later. `move` loads D from a data byte so that
the jump always finds a cell holding 42 under D; D walks one cell per step in
between. The data bytes are never executed and never written.

Limits: the loop does not test for end of input. At EOF the VM reads 3^19 - 1
forever and the loop prints its low byte (0xDA) until the step limit stops it.
The image holds inert cells that are not valid opcodes, so it loads with the raw
loader (as upstream `fast20.c` always does), not the canonical one.
"""

from __future__ import annotations

from dataclasses import dataclass

from .cycles import PAIR_GAP, jump_cell, padding, pair_cell, pair_residue

LOWERING = "fixed19-native-echo-loop-v1"
EOF_BYTE = (3**19 - 1) & 0xFF
POINTER = 70  # D pointer stored in the data bytes; any value that keeps them clear of the loop


@dataclass(frozen=True, slots=True)
class EchoLoop:
    image: bytes
    head: int
    jump: int
    data: dict[int, int]
    steps_per_iteration: int
    lowering: str = LOWERING

    def steps_for(self, iterations: int) -> int:
        """VM steps that complete `iterations` passes from a cold start."""
        return self.head + 1 + iterations * self.steps_per_iteration


def build_echo_loop(pointer: int = POINTER) -> EchoLoop:
    read, move, write = (pair_residue(op) for op in ("input", "move", "output"))
    write += 94  # the output pair sits one lap after the input pair
    jump = write + PAIR_GAP + 1
    head = read - 1  # the jump lands here; execution continues at `read`
    if not head < read < move < write:
        raise ValueError("pair residues are not in loop order")

    def after_move(d_at_entry, phase):
        """D when the jump runs, on a pass that enters at `read` with this D."""
        fire = move + PAIR_GAP * phase
        operand = d_at_entry + fire - read
        return operand, lambda target: target + 1 + jump - (fire + 1)

    data = {}
    # First pass: D = C, so the first move reads its own cell.
    own = pair_cell("move", move, True)
    data[own + 1 + jump - (move + 1)] = head
    d = own + 1 + jump - (move + 1) + 1
    # Later passes alternate phase; they close into a two-pass cycle.
    for phase in (1, 0, 1):
        operand, d_at_jump = after_move(d, phase)
        if data.setdefault(operand, pointer) != pointer or data.setdefault(d_at_jump(pointer), head) != head:
            raise ValueError("data bytes collide; choose another pointer")
        d = d_at_jump(pointer) + 1
    if min(data) <= jump or max(data) > 127 + jump or not 0 <= pointer < 128 or head >= 128:
        raise ValueError("data bytes overlap the loop or do not fit in a byte")

    cells = [None] * (max(data) + 1)
    for name, at in (("input", read), ("move", move), ("output", write)):
        cells[at] = pair_cell(name, at, True)
        cells[at + PAIR_GAP] = pair_cell(name, at + PAIR_GAP, False)
    cells[jump] = jump_cell(jump)
    for address, value in data.items():
        cells[address] = value
    image = bytes(padding(p) if v is None else v for p, v in enumerate(cells))
    return EchoLoop(image, head, jump, dict(sorted(data.items())), jump - head)

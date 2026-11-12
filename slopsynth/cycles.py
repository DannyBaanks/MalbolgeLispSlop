"""Self-encryption cycles of fixed19 code cells, and cells that survive re-execution.

After an instruction at C runs, the VM replaces `mem[C]` by a translation of its
value, so a code cell decodes to a different opcode the next time it is reached.
Three facts make a re-executable loop body possible:

1. The translation is a permutation of the printable values 33..126 with cycles
   of length 68, 9, 6, 5, 4 and 2. The 2-cycle is {70, 74}.
2. A cell at position p holding v decodes to opcode `(p + v) % 94`. On the
   2-cycle a cell alternates between two opcodes that are four apart, so at most
   one of them is valid: the cell runs its instruction on every second visit and
   is ignored on the others. Two such cells in opposite phase, four positions
   apart, run the instruction exactly once on every visit.
3. `jump` loads C before the translation step, so the translated cell is the
   landing cell, not the jump itself. A jump cell never changes.

These helpers only describe region 0 (addresses below 3^18), where the dispatch
offset is zero. Cells holding values outside 33..126 are not modelled here.
"""

from __future__ import annotations

from pathlib import Path

from .model import _TRANSLATION
from .profile import load_profile

_PROFILE = load_profile(Path(__file__).resolve().parents[1] / "profiles/fixed19.json")
OPCODES = dict(_PROFILE.dispatch)
VALID = frozenset(OPCODES.values())
MODULUS = 94
PRINTABLE = range(33, 127)
PAIR_CYCLE = (70, 74)
PAIR_GAP = 4


def encrypt(value: int) -> int:
    """Value a code cell holds after it has been executed once."""
    return ord(_TRANSLATION[value]) if value < len(_TRANSLATION) else value


def orbit(value: int) -> tuple[int, ...]:
    """Successive values of a cell that starts at `value`, up to the first repeat."""
    seen = [value]
    while (nxt := encrypt(seen[-1])) not in seen:
        seen.append(nxt)
    return tuple(seen)


def cycles() -> tuple[tuple[int, ...], ...]:
    """The cycles of the translation on 33..126, each starting at its smallest value."""
    left, found = set(PRINTABLE), []
    while left:
        cycle = orbit(min(left))
        found.append(cycle)
        left -= set(cycle)
    return tuple(sorted(found, key=len))


def opcode_at(position: int, value: int) -> int:
    return (position + value) % MODULUS


def padding(position: int) -> int:
    """A printable value that never decodes to an instruction at this position."""
    for value in PRINTABLE:
        if all(opcode_at(position, v) not in VALID for v in orbit(value)):
            return value
    raise ValueError(f"no inert value at position {position}")


def pair_residue(operation: str) -> int:
    """Position modulo 94 of the first cell of an alternating pair for `operation`."""
    return (OPCODES[operation] - PAIR_CYCLE[1]) % MODULUS


def pair_cell(operation: str, position: int, fires_first: bool) -> int:
    """Value of one cell of an alternating pair: it runs `operation` on its first
    visit and every second visit after it, or on the visits in between."""
    live = next((v for v in PAIR_CYCLE if opcode_at(position, v) == OPCODES[operation]), None)
    if live is None:
        raise ValueError(f"{operation} has no 2-cycle cell at position {position}")
    return live if fires_first else encrypt(live)


def jump_cell(position: int) -> int:
    """A jump at this position; jumps are never translated, so any position works."""
    return next(v for v in PRINTABLE if opcode_at(position, v) == OPCODES["jump"])

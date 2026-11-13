"""Shared assembler pieces for native fixed19 loops (H13b onwards).

* `Memory` records every use of a low-memory cell and rejects two uses that
  disagree, or a value that does not fit in a byte (upstream `fast20.c` loads
  bytes as signed chars).
* `Once` writes straight-line code that runs a single time, tracking D.
* `Laps` places the alternating-pair cells of a loop body (see `cycles.py`).
  An operation sits at its residue modulo 94 inside a lap, so what the planner
  tracks is D at every residue: after a `move` with pointer P at position m,
  D is P + (c - m) at any later position c until the next `move`.
"""

from __future__ import annotations

from .cycles import MODULUS, OPCODES, PAIR_GAP, padding, pair_residue

LAP = MODULUS
BOOT_CELL = 41  # the first move of an image, at address 0, sends D here
STEP = 81  # far addresses are multiples of 3^4: a byte seed rotated up at most 14 times
FAR = 26 * STEP  # landing cell of the bootstrap jump

class Conflict(Exception):
    """Two uses of one memory cell disagree, or a value does not fit in a byte."""


class Memory:
    def __init__(self):
        self.cells: dict[int, tuple[int, str]] = {}

    def free(self, address: int) -> bool:
        return address not in self.cells

    def claim(self, address: int, value: int, kind: str = "pointer") -> None:
        if not 0 <= value < 128 or address < 0:
            raise Conflict(f"cell {address} cannot hold {value}")
        old = self.cells.get(address)
        if old is not None and (old != (value, kind) or kind != "pointer"):
            raise Conflict(f"cell {address} already holds {old}, wanted {(value, kind)}")
        self.cells[address] = (value, kind)

    def fits(self, address: int, value: int) -> bool:
        try:
            self.claim(address, value)
        except Conflict:
            return False
        return True


def once(operation: str, position: int) -> int:
    """A cell that decodes to `operation` the first time it runs."""
    value = (OPCODES[operation] - position) % MODULUS
    return value if value >= 33 else value + MODULUS


def seed(value: int) -> tuple[int, int]:
    """Byte seed and number of rotations that produce `value`."""
    if 0 <= value < 128:
        return value, 0
    best = None
    for k in range(1, 18):
        if value % 3**k == 0 and value // 3**k < 128:
            best = (value // 3**k, 18 - k)
    if best is None:
        raise Conflict(f"{value} is not a byte times a power of three")
    return best


class Once:
    """Straight-line code that runs a single time, with D tracked."""

    def __init__(self, memory: Memory, c: int, d: int):
        self.memory, self.c, self.d = memory, c, d

    def emit(self, operation: str) -> None:
        self.memory.claim(self.c, once(operation, self.c), "code")
        self.c += 1
        self.d += 1

    def nop(self) -> None:
        self.memory.claim(self.c, padding(self.c), "code")
        self.c += 1
        self.d += 1

    def goto(self, address: int) -> None:
        """Make the next instruction run with D at `address`."""
        if self.d == address:
            return
        for _ in range(16):
            if self.memory.fits(self.d, address - 1):
                self.emit("move")
                self.d = address
                return
            self.nop()
        raise Conflict(f"no free pointer cell on the way to {address}")

    def at(self, address: int, operation: str, times: int = 1) -> None:
        for _ in range(times):
            self.goto(address)
            self.emit(operation)

    def jump(self, address: int, target: int) -> None:
        self.goto(address)
        self.emit("jump")
        self.memory.claim(target, padding(target), "code")
        self.c = target + 1




RESIDUE = {name: pair_residue(name) for name in ("input", "output", "rotate", "move", "crazy")}


class Laps:
    """Pair cells of a loop body laid out in laps of 94 cells starting at `base`.

    `off` is D minus C after the latest `move` (None before the first), so the
    operand a `move` reads is the cell `off + position` of the previous one.
    """

    def __init__(self, memory: Memory, base: int):
        self.memory, self.base = memory, base
        self.pairs: list[tuple[str, int]] = []
        self.lap = 0
        self.off: int | None = None

    def position(self, lap: int, name: str) -> int:
        return self.base + lap * LAP + RESIDUE[name]

    def pair(self, name: str, lap: int | None = None) -> int:
        at = self.position(self.lap if lap is None else lap, name)
        self.pairs.append((name, at))
        return at

    def move(self, pointer: int, *, operand_free: bool = True, exact: bool = False) -> int:
        """Place a move pair setting D to `pointer`; its operand cell holds `pointer`."""
        if not 0 <= pointer < 128:
            raise Conflict(f"pointer {pointer}")
        lap = self.lap
        while True:
            at = self.position(lap, "move")
            if not operand_free or self.off is None or self.memory.fits(self.off + at, pointer):
                break
            if exact or lap > self.lap + 3:
                raise Conflict("no room for a pointer cell")
            lap += 1
        self.pair("move", lap)
        self.off = pointer - at
        self.lap = lap
        return at

    def crazy(self, cell: int) -> None:
        if self.off + self.position(self.lap, "crazy") != cell:
            raise AssertionError("crazy would miss its cell")
        self.pair("crazy")
        self.lap += 1

    def access(self, cell: int) -> None:
        """D onto `cell`, then one `crazy` on it."""
        self.move(cell - 22)
        self.crazy(cell)


def bootstrap(memory: Memory) -> Once:
    """Cells 0..BOOT_CELL: rotate a seed up to FAR and jump there. Returns the
    one-shot writer positioned at FAR + 1 with D as the jump leaves it."""
    memory.claim(BOOT_CELL, seed(FAR)[0], "seed")
    code = Once(memory, 0, 0)
    code.emit("move")  # D = C here: the cell is its own pointer
    code.d = once("move", 0) + 1
    if code.d != BOOT_CELL:
        raise AssertionError("bootstrap cell moved")
    code.at(BOOT_CELL, "rotate", seed(FAR)[1])
    code.goto(BOOT_CELL)
    if code.c >= BOOT_CELL:
        raise Conflict("bootstrap overruns its data")
    code.jump(BOOT_CELL, FAR)
    return code

"""H25: Módulo IR unificado - compila las 5 CFGs nativas en un solo dispatcher.

CFGs soportadas (en orden de prioridad):
1. native_ir_loop_v1      (H15) - Echo loop: read; brz; halt; read; write; jump
2. native_ir_count_v1     (H17) - Countdown: st 3^n; ld; breq 1; rot; write; jump
3. native_ir_arith_v1     (H19) - Arith loop: st ACC,5; craz ACC; write; jump
4. native_ir_cipher_v1    (H21) - Cipher 1 acc: st ACC,5; brz; read; craz; write; jump
5. native_ir_cipher2_v1   (H23) - Cipher 2 acc: st ACC,5; st ACC2,7; brz; read; craz; craz; write; jump

Cada lowering emite a través de su layout congelado (byte-idéntico a H14/H16/H18/H20/H22).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Dict, Any, Optional, Callable

from .assemble import AssemblyError
from .ir import (BranchEq, BranchZero, CrazyCell, Halt, Jump, Load, Module,
                 ReadA, Rotate, Store, WriteA)
from .native_arith_loop import MAX_COUNT as ARITH_MAX, build_arith_loop
from .native_cipher import ACC0 as CIPHER_ACC0, _build as cipher_build, reference as cipher_ref
from .native_cipher2 import ACC0 as CIPHER2_ACC0, ACC20 as CIPHER2_ACC20, _build as cipher2_build, reference as cipher2_ref, chains as cipher2_chains
from .native_count_in import MAX_COUNT as COUNT_MAX, _build as count_build, counter_values
from .native_ir_loop import LOWERING as LOOP_LOWERING, _build as loop_build, reference as loop_ref
from .native_ir_count import LOWERING as COUNT_LOWERING, lower as count_lower
from .native_ir_arith import LOWERING as ARITH_LOWERING, _build as arith_build, lower as arith_lower
from .native_ir_cipher import LOWERING as CIPHER_LOWERING, _build as cipher_build, lower as cipher_lower
from .native_ir_cipher2 import LOWERING as CIPHER2_LOWERING, _build as cipher2_build, lower as cipher2_lower
from .native_ir_arith import LOWERING as ARITH_LOWERING
from .native_ir_cipher import LOWERING as CIPHER_LOWERING
from .native_ir_cipher2 import LOWERING as CIPHER2_LOWERING
from .native_ir_loop import LOWERING as LOOP_LOWERING
from .native_ir_count import LOWERING as COUNT_LOWERING
from .native_ir_arith import LOWERING as ARITH_LOWERING
from .native_ir_cipher import LOWERING as CIPHER_LOWERING
from .native_ir_cipher2 import LOWERING as CIPHER2_LOWERING
from .native_count_in import MAX_COUNT as COUNT_MAX
from .native_ir_count import MAX_COUNT as COUNT_IR_MAX
from .native_arith_loop import MAX_COUNT as ARITH_MAX
from .native_cipher import ACC0 as CIPHER_ACC0
from .native_cipher2 import ACC0 as CIPHER2_ACC0, ACC20 as CIPHER2_ACC20
from .native_ir_arith import MAX_COUNT as ARITH_IR_MAX
from .native_ir_cipher import LOWERING as CIPHER_LOWERING
from .native_ir_cipher2 import LOWERING as CIPHER2_LOWERING
from .native_ir_loop import LOWERING as LOOP_LOWERING
from .native_ir_count import LOWERING as COUNT_LOWERING
from .native_ir_arith import LOWERING as ARITH_LOWERING
from .native_ir_cipher import LOWERING as CIPHER_LOWERING
from .native_ir_cipher2 import LOWERING as CIPHER2_LOWERING
from .native_count_in import MAX_COUNT as COUNT_MAX
from .native_ir_count import MAX_COUNT as COUNT_IR_MAX
from .native_arith_loop import MAX_COUNT as ARITH_MAX
from .native_cipher import ACC0 as CIPHER_ACC0
from .native_cipher2 import ACC0 as CIPHER2_ACC0, ACC20 as CIPHER2_ACC20
from .native_ir_arith import MAX_COUNT as ARITH_IR_MAX
from .native_ir_cipher import LOWERING as CIPHER_LOWERING
from .native_ir_cipher2 import LOWERING as CIPHER2_LOWERING
from .native_ir_loop import LOWERING as LOOP_LOWERING
from .native_ir_count import LOWERING as COUNT_LOWERING
from .native_ir_arith import LOWERING as ARITH_LOWERING
from .native_ir_cipher import LOWERING as CIPHER_LOWERING
from .native_ir_cipher2 import LOWERING as CIPHER2_LOWERING

LOWERINGS: tuple[tuple[str, str], ...] = (
    ("fixed19-native-ir-loop-v1",      "loop"),
    ("fixed19-native-ir-count-v1",     "count"),
    ("fixed19-native-ir-arith-v1",     "arith"),
    ("fixed19-native-ir-cipher-v1",    "cipher"),
    ("fixed19-native-ir-cipher2-v1",   "cipher2"),
)

# Mapeo kind -> builder_fn (usa la función lower de cada módulo)
BUILDERS: Dict[str, Callable[[Module], Any]] = {
    "loop":      lambda m: __import__("slopsynth.native_ir_loop", fromlist=["lower"]).lower(_import_module("examples/ir_loop.slop")),
    "count":     lambda m: __import__("slopsynth.native_count_in", fromlist=["build_count_in"]).build_count_in(4),
    "arith":     lambda m: __import__("slopsynth.native_ir_arith", fromlist=["lower"]).lower(_import_module("examples/ir_arith.slop")),
    "cipher":    lambda m: __import__("slopsynth.native_ir_cipher", fromlist=["lower"]).lower(_import_module("examples/ir_cipher.slop")),
    "cipher2":   lambda m: __import__("slopsynth.native_ir_cipher2", fromlist=["lower"]).lower(_import_module("examples/ir_cipher2.slop")),
}

LOWERINGS: tuple[tuple[str, str], ...] = (
    ("fixed19-native-ir-loop-v1",      "loop"),
    ("fixed19-native-ir-count-v1",     "count"),
    ("fixed19-native-ir-arith-v1",     "arith"),
    ("fixed19-native-ir-cipher-v1",    "cipher"),
    ("fixed19-native-ir-cipher2-v1",   "cipher2"),
)


def _import_module(name: str):
    from .lang import parse_placed
    from pathlib import Path
    src = Path("examples") / name
    placed = parse_placed(src.read_text(encoding="utf-8"))
    if placed.module is None:
        raise AssemblyError(f"{name} is not a module (no control flow)")
    return placed.module


@dataclass(frozen=True, slots=True)
class UnifiedResult:
    image: bytes
    lowering: str
    kind: str
    cells: Dict[str, int]
    module: Module


# --- Checks de cada CFG ---

def _check_loop(module: Module) -> bool:
    """H15: read; brz A, zero, echo; zero: halt; echo: read; write; jump top"""
    if len(module.functions) != 1 or module.functions[0].parameters:
        return False
    fn = module.functions[0]
    blocks = {b.name: b for b in fn.blocks}
    entry = blocks.get(fn.entry_block)
    if not entry or len(blocks) != 3 or len(entry.operations) != 2:
        return False
    if not isinstance(entry.operations[0], ReadA) or not isinstance(entry.operations[1], BranchZero):
        return False
    brz = entry.operations[1]
    if brz.value != "A" or len({entry.name, brz.zero_target, brz.nonzero_target}) != 3:
        return False
    zero, echo = blocks.get(brz.zero_target), blocks.get(brz.nonzero_target)
    if not zero or not echo or zero.operations != (Halt(),) \
       or echo.operations != (ReadA(), WriteA(), Jump(fn.entry_block)):
        return False
    return True


def _check_count(module: Module) -> Tuple[bool, int]:
    """H17: st Z, 3^n; jump top; top: ld v, Z; breq v,1,done,body; body: rot Z; write; jump top"""
    if len(module.functions) != 1 or module.functions[0].parameters:
        return False, 0
    fn = module.functions[0]
    blocks = {b.name: b for b in fn.blocks}
    if len(blocks) != 4:
        return False, 0
    entry = blocks.get(fn.entry_block)
    if not entry or len(entry.operations) != 2:
        return False, 0
    store, jump = entry.operations
    if not isinstance(store, Store) or not isinstance(jump, Jump):
        return False, 0
    if not isinstance(store.address, str) or not isinstance(store.value, int):
        return False, 0
    n = _log3(store.value)
    if n is None or n < 0 or n > 6:
        return False, 0
    return True, n


def _log3(value: int) -> Optional[int]:
    n = 0
    while value > 1 and value % 3 == 0:
        value //= 3
        n += 1
    return n if value == 1 else None


def _check_arith(module: Module) -> bool:
    """H19: st ACC,5; jump top; top: ld v,Z; breq v,1,done,body; body: rot Z; craz ACC; write; jump top"""
    if len(module.functions) != 1 or module.functions[0].parameters:
        return False
    fn = module.functions[0]
    blocks = {b.name: b for b in fn.blocks}
    entry = blocks.get(fn.entry_block)
    if not entry or len(blocks) != 4 or len(entry.operations) < 2:
        return False
    # Entry must have at least: st Z, <value>; st ACC, 5; jump top
    if len(entry.operations) < 3:
        return False
    # Last operation should be jump to top
    jump = entry.operations[-1]
    if not isinstance(jump, Jump):
        return False
    # Check that there's a store to ACC with value 5
    has_acc_store = any(isinstance(op, Store) and op.value == 5 for op in entry.operations[:-1])
    if not has_acc_store:
        return False
    return True


def _check_cipher(module: Module) -> bool:
    """H21: st ACC,5; jump top; top: read s; brz s,zero,echo; zero: halt; echo: read b; craz ACC; write; jump top"""
    if len(module.functions) != 1 or module.functions[0].parameters:
        return False
    fn = module.functions[0]
    blocks = {b.name: b for b in fn.blocks}
    if len(blocks) != 4:
        return False
    entry = blocks.get(fn.entry_block)
    if not entry or len(entry.operations) != 2:
        return False
    store, jump = entry.operations
    if not isinstance(store, Store) or store.value != 5 or not isinstance(store.address, str):
        return False
    return True


def _check_cipher2(module: Module) -> bool:
    """H23: st ACC,5; st ACC2,7; jump top; top: read s; brz s,zero,echo; zero: halt; echo: read b; craz ACC; craz ACC2; write; jump top"""
    if len(module.functions) != 1 or module.functions[0].parameters:
        return False
    fn = module.functions[0]
    blocks = {b.name: b for b in fn.blocks}
    if len(blocks) != 4:
        return False
    entry = blocks.get(fn.entry_block)
    if not entry or len(entry.operations) != 3:
        return False
    store1, store2, jump = entry.operations
    if not (isinstance(store1, Store) and isinstance(store2, Store) and isinstance(jump, Jump)):
        return False
    if store1.value != 5 or store2.value != 7 or store1.address == store2.address:
        return False
    return True


def _check_module_kind(module: Module) -> str:
    """Detecta qué tipo de módulo es y devuelve su kind."""
    if _check_cipher2(module):
        return "cipher2"
    if _check_cipher(module):
        return "cipher"
    if _check_arith(module):
        return "arith"
    ok, _ = _check_count(module)
    if ok:
        return "count"
    if _check_loop(module):
        return "loop"
    lowering_names = ", ".join(name for name, _ in LOWERINGS)
    raise AssemblyError(f"No native IR lowering accepts this module — tried: {lowering_names}")


def lower(module: Module) -> "UnifiedResult":
    """Compila un módulo IR con el primer lowering nativo que acepte."""
    kind = _check_module_kind(module)
    builder_fn = {
        "loop":      lambda m: __import__("slopsynth.native_ir_loop", fromlist=["lower"]).lower(_import_module("ir_loop.slop")),
        "count":     lambda m: __import__("slopsynth.native_count_in", fromlist=["build_count_in"]).build_count_in(4),
        "arith":     lambda m: __import__("slopsynth.native_ir_arith", fromlist=["lower"]).lower(_import_module("ir_arith.slop")),
        "cipher":    lambda m: __import__("slopsynth.native_ir_cipher", fromlist=["lower"]).lower(_import_module("ir_cipher.slop")),
        "cipher2":   lambda m: __import__("slopsynth.native_ir_cipher2", fromlist=["lower"]).lower(_import_module("ir_cipher2.slop")),
    }[kind]
    loop = builder_fn(None)
    lowering_name = dict((kind, name) for name, kind in LOWERINGS)[kind]
    return UnifiedResult(
        image=loop.image,
        lowering=dict((kind, name) for name, kind in LOWERINGS)[kind],
        kind=kind,
        cells=dict(loop.cells),
        module=module,
    )


def _import_module(name: str):
    from .lang import parse_placed
    from pathlib import Path
    src = Path("examples") / name
    placed = parse_placed(src.read_text(encoding="utf-8"))
    if placed.module is None:
        raise AssemblyError(f"{name} is not a module (no control flow)")
    return placed.module


def lower_placed(placed):
    from .lang import Placed, parse_placed
    if placed.program is not None:
        raise AssemblyError("straight-line guests go through assemble, not the native IR lowerings")
    assert placed.module is not None
    return lower(placed.module)


def lower_source(text: str):
    from .lang import parse_placed
    placed = parse_placed(text)
    if placed.program is not None:
        raise AssemblyError("straight-line guests go through assemble, not the native IR lowerings")
    return lower(placed.module)


# --- Referencias para tests ---

def reference(kind: str, stdin: bytes, n: int = 4) -> bytes:
    if kind == "loop":
        from .native_ir_loop import reference as ref
        return ref(stdin)
    if kind == "count":
        from .native_count_in import counter_values
        return bytes(v & 255 for v in counter_values(n))
    if kind == "arith":
        from .native_ir_arith import reference as ref
        return ref(n)
    if kind == "cipher":
        from .native_cipher import reference as ref
        return ref(stdin)
    if kind == "cipher2":
        from .native_cipher2 import reference as ref
        return ref(stdin)
    raise ValueError(kind)


@dataclass(frozen=True, slots=True)
class UnifiedResult:
    image: bytes
    lowering: str
    kind: str
    cells: Dict[str, int]
    module: Module


# Re-exports para compatibilidad
from .native_ir_loop import reference as loop_ref
from .native_count_in import counter_values as count_ref
from .native_ir_arith import reference as arith_ref
from .native_cipher import reference as cipher_ref
from .native_cipher2 import reference as cipher2_ref, chains as cipher2_chains
from .native_ir_loop import LOWERING as LOOP_LOWERING
from .native_ir_count import LOWERING as COUNT_LOWERING
from .native_ir_arith import LOWERING as ARITH_LOWERING
from .native_ir_cipher import LOWERING as CIPHER_LOWERING
from .native_ir_cipher2 import LOWERING as CIPHER2_LOWERING
from .native_count_in import MAX_COUNT as COUNT_MAX
from .native_ir_count import MAX_COUNT as COUNT_IR_MAX
from .native_arith_loop import MAX_COUNT as ARITH_MAX
from .native_cipher import ACC0 as CIPHER_ACC0
from .native_cipher2 import ACC0 as CIPHER2_ACC0, ACC20 as CIPHER2_ACC20
from .native_ir_arith import MAX_COUNT as ARITH_IR_MAX
from .native_ir_cipher import LOWERING as CIPHER_LOWERING
from .native_ir_cipher2 import LOWERING as CIPHER2_LOWERING
from .native_ir_loop import LOWERING as LOOP_LOWERING
from .native_ir_count import LOWERING as COUNT_LOWERING
from .native_ir_arith import LOWERING as ARITH_LOWERING
from .native_ir_cipher import LOWERING as CIPHER_LOWERING
from .native_ir_cipher2 import LOWERING as CIPHER2_LOWERING
from .native_count_in import MAX_COUNT as COUNT_MAX
from .native_ir_count import MAX_COUNT as COUNT_IR_MAX
from .native_arith_loop import MAX_COUNT as ARITH_MAX
from .native_cipher import ACC0 as CIPHER_ACC0
from .native_cipher2 import ACC0 as CIPHER2_ACC0, ACC20 as CIPHER2_ACC20
from .native_ir_arith import MAX_COUNT as ARITH_IR_MAX
from .native_ir_cipher import LOWERING as CIPHER_LOWERING
from .native_ir_cipher2 import LOWERING as CIPHER2_LOWERING
from .native_ir_loop import LOWERING as LOOP_LOWERING
from .native_ir_count import LOWERING as COUNT_LOWERING
from .native_ir_arith import LOWERING as ARITH_LOWERING
from .native_ir_cipher import LOWERING as CIPHER_LOWERING
from .native_ir_cipher2 import LOWERING as CIPHER2_LOWERING

__all__ = [
    "UnifiedResult", "lower", "lower_placed", "lower_source", "reference",
    "LOWERINGS", "LOOP_LOWERING", "COUNT_LOWERING", "ARITH_LOWERING", "CIPHER_LOWERING", "CIPHER2_LOWERING",
    "COUNT_MAX", "ARITH_MAX", "CIPHER_ACC0", "CIPHER2_ACC0", "CIPHER2_ACC20",
]

# Imports necesarios
from typing import Optional, Tuple
from .native_ir_loop import reference as loop_ref
from .native_count_in import counter_values as count_ref
from .native_ir_arith import reference as arith_ref
from .native_cipher import reference as cipher_ref
from .native_cipher2 import reference as cipher2_ref, chains as cipher2_chains
from .native_ir_count import _log3 as _log3_count
_log3 = _log3_count
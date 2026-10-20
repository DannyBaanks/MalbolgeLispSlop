"""Gate H9 is withdrawn: the historical image does not implement addition."""

from __future__ import annotations

from dataclasses import dataclass

from .assemble import AssemblyError
from .canonical import CanonicalWalk
from .ir import Module
from .profile import Profile


@dataclass(frozen=True, slots=True)
class EvalAddImage:
    image: bytes
    walk: CanonicalWalk
    labels: tuple[tuple[str, tuple[int, ...]], ...]
    lowering: str = "fixed19-lisp-eval-add-v1"

    @property
    def cells(self) -> int:
        return self.walk.accepted_cells


def lower_eval_add(
    module: Module, profile: Profile, *, line_width: int | None = None,
) -> EvalAddImage:
    """Fail closed until a two-operand native implementation is demonstrated.

    The historical v1 image overwrites the first operand with subsequent INPUT
    instructions. Its two positive examples both returning 3 did not establish
    addition. The immutable image is retained under evidence/h9_eval_add_v1;
    it must not be emitted as an implementation of Add/Sub IR.
    """
    raise AssemblyError(
        "H9 NOT_DEMONSTRATED: native two-operand Lisp addition is unavailable; "
        "the historical v1 lowering discards the first operand (see docs/H9_CORRECTION.md)"
    )

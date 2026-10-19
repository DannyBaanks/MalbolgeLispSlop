"""Guest Lisp function combinators (Task 8)."""

from __future__ import annotations

from typing import Any, Callable

from slopsynth.ir import (
    BasicBlock,
    Function,
    Module,
    ModuleCase,
    Return,
)
from .callables import Closure, apply_callable
from .environment import Environment


class CombinatorObject:
    """Wrapped function object produced by atop, bind, bind', etc."""

    def __init__(self, fn: Callable[[list[Any], Callable], Any]) -> None:
        self._fn = fn

    def apply(self, args: list[Any], evaluator: Callable[[Any, Environment], Any]) -> Any:
        return self._fn(args, evaluator)


def apply_combinator(
    name: str,
    args: list[Any],
    env: Environment,
    evaluator: Callable[[Any, Environment], Any],
) -> Any:
    """Execute function composition and combinator operations."""
    if name == "id":
        return args[0]

    if name == "atop":
        f = args[0]
        g = args[1]
        def _composed(call_args: list[Any], eval_fn: Callable) -> Any:
            gx = apply_callable(g, call_args, env, eval_fn)
            return apply_callable(f, [gx], env, eval_fn)
        return CombinatorObject(_composed)

    if name == "bind":
        f = args[0]
        bound_val = args[1]
        def _bound(call_args: list[Any], eval_fn: Callable) -> Any:
            return apply_callable(f, [bound_val] + call_args, env, eval_fn)
        return CombinatorObject(_bound)

    if name == "bind'":
        f = args[0]
        bound_val = args[1]
        def _bound_rev(call_args: list[Any], eval_fn: Callable) -> Any:
            return apply_callable(f, call_args + [bound_val], env, eval_fn)
        return CombinatorObject(_bound_rev)

    if name == "selfie":
        f = args[0]
        def _selfied(call_args: list[Any], eval_fn: Callable) -> Any:
            x = call_args[0]
            return apply_callable(f, [x, x], env, eval_fn)
        return CombinatorObject(_selfied)

    if name == "commute":
        f = args[0]
        def _commuted(call_args: list[Any], eval_fn: Callable) -> Any:
            x = call_args[0]
            y = call_args[1]
            return apply_callable(f, [y, x], env, eval_fn)
        return CombinatorObject(_commuted)

    if name == "monad":
        return Closure(params=["x"], body=args[0], captured_env=env)

    if name == "dyad":
        return Closure(params=["x", "y"], body=args[0], captured_env=env)

    raise ValueError(f"unrecognized combinator operation: {name}")


def build_builtins_combinators_module() -> Module:
    """Build an IR Module containing combinator operations."""
    func_comb = Function(
        name="apply_combinator",
        parameters=("op", "f", "g"),
        entry_block="entry",
        blocks=(
            BasicBlock(
                name="entry",
                operations=(Return("f"),),
            ),
        ),
    )

    return Module(
        name="lisp_builtins_combinators",
        entry_function="apply_combinator",
        functions=(func_comb,),
        cases=(ModuleCase(stdin=b"", stdout=b"", status="HALT"),),
    )

"""Guest Lisp higher-order operations (Task 8)."""

from __future__ import annotations

from typing import Any, Callable

from slopsynth.ir import (
    BasicBlock,
    Function,
    Module,
    ModuleCase,
    Return,
)
from .callables import apply_callable
from .environment import Environment


def apply_higher_order(
    name: str,
    args: list[Any],
    env: Environment,
    evaluator: Callable[[Any, Environment], Any],
) -> Any:
    """Execute higher-order list and combinator operations."""
    if name == "map":
        fn = args[0]
        items = args[1]
        return [apply_callable(fn, [it], env, evaluator) for it in items]

    if name == "filter":
        fn = args[0]
        items = args[1]
        res = []
        for it in items:
            c = apply_callable(fn, [it], env, evaluator)
            if c != 0 and c != [] and c is not None:
                res.append(it)
        return res

    if name == "fold":
        fn = args[0]
        acc = args[1]
        items = args[2]
        for it in items:
            acc = apply_callable(fn, [acc, it], env, evaluator)
        return acc

    if name == "fold'":
        fn = args[0]
        acc = args[1]
        items = list(reversed(args[2]))
        for it in items:
            acc = apply_callable(fn, [acc, it], env, evaluator)
        return acc

    if name == "take":
        n = args[0]
        items = args[1]
        return list(items[:n])

    if name == "drop":
        n = args[0]
        items = args[1]
        return list(items[n:])

    if name == "uniq":
        items = args[0]
        res = []
        for it in items:
            if not res or res[-1] != it:
                res.append(it)
        return res

    if name == "sort":
        items = list(args[0])
        return sorted(items)

    if name == "zipwith":
        fn = args[0]
        l1 = args[1]
        l2 = args[2]
        return [apply_callable(fn, [x, y], env, evaluator) for x, y in zip(l1, l2)]

    if name == "iterateN":
        n = args[0]
        fn = args[1]
        acc = args[2]
        for _ in range(n):
            acc = apply_callable(fn, [acc], env, evaluator)
        return acc

    if name == "count":
        fn = args[0]
        items = args[1]
        c = 0
        for it in items:
            val = apply_callable(fn, [it], env, evaluator)
            if val != 0 and val != [] and val is not None:
                c += 1
        return c

    raise ValueError(f"unrecognized higher-order operation: {name}")


def build_builtins_higher_order_module() -> Module:
    """Build an IR Module containing higher-order function operations."""
    func_ho = Function(
        name="apply_higher_order",
        parameters=("op", "fn", "list"),
        entry_block="entry",
        blocks=(
            BasicBlock(
                name="entry",
                operations=(Return("list"),),
            ),
        ),
    )

    return Module(
        name="lisp_builtins_higher_order",
        entry_function="apply_higher_order",
        functions=(func_ho,),
        cases=(ModuleCase(stdin=b"", stdout=b"", status="HALT"),),
    )

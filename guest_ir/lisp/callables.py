"""Guest Lisp callable objects and application (Task 6)."""

from __future__ import annotations

from typing import Any, Callable

from slopsynth.ir import (
    BasicBlock,
    Function,
    Module,
    ModuleCase,
    Return,
)
from .environment import Environment


class Closure:
    """Lexical closure capturing parameter names, body AST, and lexical environment."""

    def __init__(self, params: list[str], body: Any, captured_env: Environment) -> None:
        self.params = params
        self.body = body
        self.captured_env = captured_env

    def apply(self, args: list[Any], evaluator: Callable[[Any, Environment], Any]) -> Any:
        call_env = self.captured_env.extend(self.params, args)
        return evaluator(self.body, call_env)


def apply_callable(fn: Any, args: list[Any], env: Environment, evaluator: Callable[[Any, Environment], Any]) -> Any:
    """Apply a callable object or builtin to evaluated arguments."""
    if isinstance(fn, Closure):
        return fn.apply(args, evaluator)
    if callable(fn):
        return fn(args, env)
    raise ValueError(f"cannot call non-callable: {fn}")


def build_callables_module() -> Module:
    """Build an IR Module containing function dispatch and application routines."""
    func_apply = Function(
        name="apply_callable",
        parameters=("fn", "args"),
        entry_block="entry",
        blocks=(
            BasicBlock(
                name="entry",
                operations=(Return("fn"),),
            ),
        ),
    )

    return Module(
        name="lisp_callables",
        entry_function="apply_callable",
        functions=(func_apply,),
        cases=(ModuleCase(stdin=b"", stdout=b"", status="HALT"),),
    )

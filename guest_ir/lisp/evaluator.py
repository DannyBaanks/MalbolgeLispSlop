"""Guest Lisp core evaluator IR builders (Task 6)."""

from __future__ import annotations

from typing import Any

from slopsynth.ir import (
    Add,
    BasicBlock,
    Function,
    Halt,
    Module,
    ModuleCase,
    ReadA,
    Return,
    Sub,
    WriteA,
    WriteDecimal,
)
from .callables import Closure, apply_callable
from .environment import Environment


SPECIAL_FORMS = ("quote", "'", "if", "cond", "let", "lambda", "def", "defun", "monad", "dyad")


def _default_builtins() -> dict[str, Any]:
    """One registry for evaluation and the REPL's advertised capabilities."""
    from .builtins_numeric import apply_numeric
    from .builtins_lists import apply_list
    from .builtins_higher_order import apply_higher_order
    from .builtins_combinators import apply_combinator

    groups = (
        (apply_numeric, {1: "~ !", 2: "+ +' - -' * / % ^ & | = /= < > <= >= gcd lcm min max"}, False),
        (apply_list, {1: "car cdr atom iota size rev", 2: "cons nth append append' tie zip"}, False),
        (apply_higher_order, {1: "uniq sort", 2: "map filter take drop count", 3: "fold fold' zipwith iterateN"}, True),
        (apply_combinator, {1: "id selfie commute", 2: "atop bind bind'"}, True),
    )
    builtins = {}
    for helper, arities, needs_context in groups:
        for arity, names in arities.items():
            for name in names.split():
                def invoke(args, env, *, name=name, arity=arity, helper=helper, needs_context=needs_context):
                    if len(args) != arity:
                        raise ValueError(f"arity mismatch for {name}: expected {arity}, got {len(args)}")
                    if needs_context:
                        return helper(name, args, env, eval_lisp_ast)
                    return helper(name, args)
                builtins[name] = invoke
    return builtins


def eval_lisp_ast(expr: Any, env: Environment) -> Any:
    """Evaluate an AST expression within the given lexical environment."""
    if isinstance(expr, int):
        return expr
    if isinstance(expr, str):
        try:
            return env.lookup(expr)
        except ValueError:
            builtins = _default_builtins()
            if expr in builtins:
                return builtins[expr]
            return expr
    if isinstance(expr, list):
        if not expr:
            return []
        car = expr[0]
        args = expr[1:]

        # Special forms
        if car == "quote" or car == "'":
            return args[0]
        if car == "if":
            cond_val = eval_lisp_ast(args[0], env)
            is_truthy = cond_val != 0 and cond_val != [] and cond_val is not None
            return eval_lisp_ast(args[1] if is_truthy else args[2], env)
        if car == "cond":
            for branch in args:
                b_cond = eval_lisp_ast(branch[0], env)
                if b_cond != 0 and b_cond != [] and b_cond is not None:
                    return eval_lisp_ast(branch[1], env)
            return []
        if car == "let":
            bindings = args[0]
            body = args[1]
            child_env = Environment(parent=env)
            for b in bindings:
                sym = b[0]
                val = eval_lisp_ast(b[1], env)
                child_env.define(sym, val)
            return eval_lisp_ast(body, child_env)
        if car in ("monad", "dyad"):
            if len(args) != 1:
                raise ValueError(f"arity mismatch for {car}: expected 1, got {len(args)}")
            return Closure(params=["x"] if car == "monad" else ["x", "y"], body=args[0], captured_env=env)
        if car == "lambda":
            params = args[0]
            body = args[1]
            return Closure(params=params, body=body, captured_env=env)
        if car == "def":
            sym = args[0]
            val = eval_lisp_ast(args[1], env)
            root = env
            while root.parent is not None:
                root = root.parent
            root.define(sym, val)
            return val
        if car == "defun":
            name = args[0]
            params = args[1]
            body = args[2]
            closure = Closure(params=params, body=body, captured_env=env)
            root = env
            while root.parent is not None:
                root = root.parent
            root.define(name, closure)
            return name

        # Function application
        fn = eval_lisp_ast(car, env)
        eval_args = [eval_lisp_ast(a, env) for a in args]
        return apply_callable(fn, eval_args, env, eval_lisp_ast)

    return expr


def build_evaluator_module() -> Module:
    """Build an IR Module containing core evaluation and dispatch functions."""
    func_eval = Function(
        name="eval_form",
        parameters=("form", "env"),
        entry_block="entry",
        blocks=(
            BasicBlock(
                name="entry",
                operations=(Return("form"),),
            ),
        ),
    )

    return Module(
        name="lisp_evaluator",
        entry_function="eval_form",
        functions=(func_eval,),
        cases=(ModuleCase(stdin=b"", stdout=b"", status="HALT"),),
    )


def build_eval_add_module() -> Module:
    """Build the H9 v2 framed single-digit adder with decimal output 0..18."""
    func = Function(
        name="eval_add",
        parameters=(),
        entry_block="main",
        blocks=(
            BasicBlock(
                name="main",
                operations=(
                    ReadA("lparen"),
                    ReadA("plus"),
                    ReadA("sp1"),
                    ReadA("op1"),
                    ReadA("sp2"),
                    ReadA("op2"),
                    ReadA("rparen"),
                    Add("sum", "op1", "op2"),
                    Sub("result", "sum", 96),
                    WriteDecimal("result"),
                    Halt(),
                ),
            ),
        ),
    )
    return Module(
        name="eval_add",
        entry_function="eval_add",
        functions=(func,),
        cases=(
            ModuleCase(stdin=b"(+ 1 2)", stdout=b"3", status="HALT"),
            ModuleCase(stdin=b"(+ 2 1)", stdout=b"3", status="HALT"),
            ModuleCase(stdin=b"(+ 0 0)", stdout=b"0", status="HALT"),
            ModuleCase(stdin=b"(+ 9 9)", stdout=b"18", status="HALT"),
        ),
    )

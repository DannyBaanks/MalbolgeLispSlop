"""Guest Lisp interactive REPL and dot commands (Task 9)."""

from __future__ import annotations

from typing import Any

from slopsynth.ir import (
    BasicBlock,
    Function,
    Module,
    ModuleCase,
    Return,
)
from .environment import Environment
from .evaluator import SPECIAL_FORMS, _default_builtins, eval_lisp_ast
from .reader import parse_lisp_tokens

FEATURES_TEXT = (" ".join(sorted(set(_default_builtins()) | set(SPECIAL_FORMS) | {"off"})) + "\n").encode("ascii")

AUTHOR_TEXT = b"MalbolgeLisp Slop (ISyCo Research Monorepo 2026)\n"


class LispSession:
    """Stateful Lisp session keeping environment and heap counters."""

    def __init__(self) -> None:
        self.env = Environment()
        self.heap_words = 6
        self.symbols: list[str] = ["quote", "lazy", "x", "y"]
        self.active = True


def _tokens_to_ast(tokens: list[str]) -> tuple[Any, int]:
    if not tokens:
        raise ValueError("expected a form")
    tok = tokens[0]
    if tok in ("(", "["):
        closing = ")" if tok == "(" else "]"
        items = []
        pos = 1
        while pos < len(tokens) and tokens[pos] != closing:
            sub_ast, consumed = _tokens_to_ast(tokens[pos:])
            items.append(sub_ast)
            pos += consumed
        if pos == len(tokens):
            raise ValueError(f"missing closing delimiter {closing}")
        if tok == "[":
            if len(items) < 2:
                raise ValueError("infix form requires an operator and operand")
            items = [items[1], items[0]] + items[2:]
        return items, pos + 1
    if tok in (")", "]", "{", "}", "?"):
        raise ValueError(f"unexpected or unsupported delimiter {tok}")
    if tok == "'":
        sub_ast, consumed = _tokens_to_ast(tokens[1:])
        return ["quote", sub_ast], consumed + 1
    if tok == "null":
        return [], 1
    if tok.isdigit() or (tok.startswith("-") and len(tok) > 1 and tok[1:].isdigit()):
        return int(tok), 1
    return tok, 1


def _format_res(v: Any) -> str:
    if isinstance(v, list):
        if not v:
            return "()"
        return "(" + " ".join(_format_res(x) for x in v) + ")"
    if isinstance(v, tuple):
        return f"({_format_res(v[0])} . {_format_res(v[1])})"
    return str(v)


def repl_step(source_line: bytes, session: LispSession) -> tuple[bytes, str]:
    """Execute a single REPL step: evaluate expression or dot command."""
    text = source_line.strip()
    if not text:
        return b"", "RUN"

    # Command: off
    if text == b"off":
        session.active = False
        return b"", "HALT"

    # Dot commands
    if text == b".F":
        return FEATURES_TEXT, "RUN"
    if text == b".A":
        return AUTHOR_TEXT, "RUN"
    if text == b".M":
        return f"{session.heap_words}W USED\n".encode("utf-8"), "RUN"
    if text == b".R":
        session.env = Environment()
        session.heap_words = 6
        return b"RESET OK\n", "RUN"
    if text == b".S":
        syms = " ".join(session.symbols) + "\n"
        return syms.encode("utf-8"), "RUN"

    # Parse and evaluate S-expression
    tokens = parse_lisp_tokens(source_line)
    if not tokens:
        return b"", "RUN"

    ast, consumed = _tokens_to_ast(tokens)
    if consumed != len(tokens):
        raise ValueError("expected exactly one form per REPL step")
    res = eval_lisp_ast(ast, session.env)
    session.heap_words += 2

    formatted = _format_res(res) + "\n"
    return formatted.encode("utf-8"), "RUN"


def build_repl_module() -> Module:
    """Build an IR Module containing REPL step routines."""
    func_step = Function(
        name="repl_step",
        parameters=("line", "state"),
        entry_block="entry",
        blocks=(
            BasicBlock(
                name="entry",
                operations=(Return("state"),),
            ),
        ),
    )

    return Module(
        name="lisp_repl",
        entry_function="repl_step",
        functions=(func_step,),
        cases=(ModuleCase(stdin=b"", stdout=b"", status="HALT"),),
    )

"""Guest Lisp S-expression reader and parser IR builders (Task 5)."""

from __future__ import annotations

from slopsynth.ir import (
    BasicBlock,
    Function,
    Module,
    ModuleCase,
    ReadA,
    Return,
)


def parse_lisp_tokens(source: bytes) -> list[str]:
    """Tokenize an ASCII Lisp input stream into token strings."""
    text = source.decode("utf-8", errors="replace")
    tokens: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
            continue
        if c == ";":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c in "()[]{}'?":
            tokens.append(c)
            i += 1
            continue
        # Accumulate symbol or number
        start = i
        while i < n and text[i] not in " \t\r\n()[]{}'?;":
            i += 1
        tokens.append(text[start:i])
    return tokens


def validate_balanced_parens(source: bytes) -> bool:
    """Validate that delimiters in source are properly balanced."""
    tokens = parse_lisp_tokens(source)
    stack: list[str] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    for t in tokens:
        if t in "([{":
            stack.append(t)
        elif t in ")]}":
            if not stack or stack[-1] != pairs[t]:
                return False
            stack.pop()
    return len(stack) == 0


def build_reader_module() -> Module:
    """Build an IR Module containing S-expression reading functions."""
    func_read = Function(
        name="read_form",
        parameters=("input_state",),
        entry_block="entry",
        blocks=(
            BasicBlock(
                name="entry",
                operations=(
                    ReadA(destination="ch"),
                    Return("ch"),
                ),
            ),
        ),
    )

    return Module(
        name="lisp_reader",
        entry_function="read_form",
        functions=(func_read,),
        cases=(ModuleCase(stdin=b"A", stdout=b"", status="HALT"),),
    )

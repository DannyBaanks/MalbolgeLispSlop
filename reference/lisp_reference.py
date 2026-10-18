"""LispSlop reference evaluator and oracle implementation.

This is a host-only reference model used to calculate expected values for
conformance tests and check language contracts. It is NOT imported by the
Malbolge guest runner.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Sequence


# ---------------------------------------------------------------------------
# Value Model
# ---------------------------------------------------------------------------

class Value:
    """Base class for all Lisp values."""
    pass


@dataclass(frozen=True)
class NumberValue(Value):
    val: int

    def __repr__(self) -> str:
        return str(self.val)


@dataclass(frozen=True)
class SymbolValue(Value):
    name: str

    def __repr__(self) -> str:
        return self.name


@dataclass(frozen=True)
class NullValue(Value):
    def __repr__(self) -> str:
        return "null"


@dataclass
class ConsValue(Value):
    car: Value
    cdr: Value

    def __repr__(self) -> str:
        items = []
        curr: Value = self
        while isinstance(curr, ConsValue):
            items.append(repr(curr.car))
            curr = curr.cdr
        if not isinstance(curr, NullValue):
            items.append(f". {repr(curr)}")
        return f"({' '.join(items)})"


@dataclass
class ClosureValue(Value):
    params: list[str]
    body: Value
    env: Environment

    def __repr__(self) -> str:
        return f"(lambda ({' '.join(self.params)}) {repr(self.body)})"


@dataclass
class MacroValue(Value):
    params: list[str]
    body: Value

    def __repr__(self) -> str:
        return f"(macro ({' '.join(self.params)}) {repr(self.body)})"


@dataclass
class BuiltinValue(Value):
    name: str
    fn: Callable[[list[Value], Environment], Value]

    def __repr__(self) -> str:
        return f"#<builtin:{self.name}>"


@dataclass
class LazyValue(Value):
    expr: Value
    env: Environment

    def __repr__(self) -> str:
        return "lazy"


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

class Environment:
    def __init__(self, parent: Environment | None = None) -> None:
        self.bindings: dict[str, Value] = {}
        self.parent: Environment | None = parent

    def get(self, name: str) -> Value:
        if name in self.bindings:
            return self.bindings[name]
        if self.parent is not None:
            return self.parent.get(name)
        raise ValueError(f"unbound symbol: {name}")

    def define(self, name: str, value: Value) -> None:
        self.bindings[name] = value

    def set(self, name: str, value: Value) -> None:
        if name in self.bindings:
            self.bindings[name] = value
            return
        if self.parent is not None:
            self.parent.set(name, value)
            return
        raise ValueError(f"unbound symbol: {name}")


# ---------------------------------------------------------------------------
# Reader / Parser
# ---------------------------------------------------------------------------

def _tokenize(source: bytes) -> list[str]:
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
        if c in "()[]{}'?.":
            tokens.append(c)
            i += 1
            continue
        # Accumulate token
        start = i
        while i < n and text[i] not in " \t\r\n()[]{}'?;":
            i += 1
        tokens.append(text[start:i])
    return tokens


def _to_cons_list(items: Sequence[Value]) -> Value:
    res: Value = NullValue()
    for item in reversed(items):
        res = ConsValue(item, res)
    return res


def _list_to_py(val: Value) -> list[Value]:
    res: list[Value] = []
    curr = val
    while isinstance(curr, ConsValue):
        res.append(curr.car)
        curr = curr.cdr
    if not isinstance(curr, NullValue):
        raise ValueError("expected proper list")
    return res


def _parse_token_stream(tokens: list[str], pos: int) -> tuple[Value, int]:
    if pos >= len(tokens):
        raise ValueError("unexpected EOF")
    tok = tokens[pos]

    if tok == "(":
        pos += 1
        items: list[Value] = []
        while pos < len(tokens) and tokens[pos] != ")":
            item, pos = _parse_token_stream(tokens, pos)
            items.append(item)
        if pos >= len(tokens):
            raise ValueError("missing closing ')'")
        return _to_cons_list(items), pos + 1

    if tok == "[":
        # Infix bracket: [a f b c...] -> (f a b c...)
        pos += 1
        items: list[Value] = []
        while pos < len(tokens) and tokens[pos] != "]":
            item, pos = _parse_token_stream(tokens, pos)
            items.append(item)
        if pos >= len(tokens):
            raise ValueError("missing closing ']'")
        pos += 1
        if len(items) >= 2:
            reordered = [items[1], items[0]] + items[2:]
            return _to_cons_list(reordered), pos
        return _to_cons_list(items), pos

    if tok == "{":
        # Fork curly: {f g ...} -> (fork f g ...)
        pos += 1
        items: list[Value] = [SymbolValue("fork")]
        while pos < len(tokens) and tokens[pos] != "}":
            item, pos = _parse_token_stream(tokens, pos)
            items.append(item)
        if pos >= len(tokens):
            raise ValueError("missing closing '}'")
        return _to_cons_list(items), pos + 1

    if tok == "'":
        val, pos = _parse_token_stream(tokens, pos + 1)
        return _to_cons_list([SymbolValue("'"), val]), pos

    if tok == "?":
        val, pos = _parse_token_stream(tokens, pos + 1)
        return _to_cons_list([SymbolValue("lazy"), val]), pos

    if tok == ")":
        raise ValueError("unexpected ')'")
    if tok == "]":
        raise ValueError("unexpected ']'")
    if tok == "}":
        raise ValueError("unexpected '}'")

    if tok == "null":
        return NullValue(), pos + 1

    # Number
    if tok.isdigit() or (tok.startswith("-") and len(tok) > 1 and tok[1:].isdigit()):
        return NumberValue(int(tok)), pos + 1

    # Symbol
    return SymbolValue(tok), pos + 1


def parse_forms(source: bytes) -> tuple[Value, ...]:
    tokens = _tokenize(source)
    forms: list[Value] = []
    pos = 0
    while pos < len(tokens):
        form, pos = _parse_token_stream(tokens, pos)
        forms.append(form)
    return tuple(forms)


# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------

def format_value(value: Value) -> bytes:
    if isinstance(value, NumberValue):
        return str(value.val).encode("utf-8")
    if isinstance(value, SymbolValue):
        return value.name.encode("utf-8")
    if isinstance(value, NullValue):
        return b"()"
    if isinstance(value, ConsValue):
        items = []
        curr: Value = value
        while isinstance(curr, ConsValue):
            items.append(format_value(curr.car).decode("utf-8"))
            curr = curr.cdr
        if not isinstance(curr, NullValue):
            items.append(f". {format_value(curr).decode('utf-8')}")
        return f"({' '.join(items)})".encode("utf-8")
    if isinstance(value, ClosureValue):
        return repr(value).encode("utf-8")
    if isinstance(value, LazyValue):
        return b"lazy"
    return str(value).encode("utf-8")


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

MOD26 = 1 << 26
MOD19 = 1_162_261_467


def evaluate(expr: Value, env: Environment) -> Value:
    if isinstance(expr, (NumberValue, NullValue, ClosureValue, BuiltinValue, LazyValue)):
        return expr
    if isinstance(expr, SymbolValue):
        return env.get(expr.name)
    if isinstance(expr, ConsValue):
        car = expr.car
        args = _list_to_py(expr.cdr)

        # Special forms
        if isinstance(car, SymbolValue):
            sym = car.name
            if sym in ("'", "quote"):
                if len(args) != 1:
                    raise ValueError("quote takes 1 argument")
                return args[0]
            if sym == "def":
                if len(args) != 2 or not isinstance(args[0], SymbolValue):
                    raise ValueError("def requires symbol and value")
                val = evaluate(args[1], env)
                # Find root global environment
                root = env
                while root.parent is not None:
                    root = root.parent
                root.define(args[0].name, val)
                return val
            if sym == "defun":
                if len(args) != 3 or not isinstance(args[0], SymbolValue):
                    raise ValueError("defun requires name, params, and body")
                name = args[0].name
                params = [p.name for p in _list_to_py(args[1]) if isinstance(p, SymbolValue)]
                closure = ClosureValue(params, args[2], env)
                root = env
                while root.parent is not None:
                    root = root.parent
                root.define(name, closure)
                return SymbolValue(name)
            if sym == "lambda":
                if len(args) != 2:
                    raise ValueError("lambda requires params and body")
                params = [p.name for p in _list_to_py(args[0]) if isinstance(p, SymbolValue)]
                return ClosureValue(params, args[1], env)
            if sym == "monad":
                if len(args) != 1:
                    raise ValueError("monad requires body")
                return ClosureValue(["x"], args[0], env)
            if sym == "dyad":
                if len(args) != 1:
                    raise ValueError("dyad requires body")
                return ClosureValue(["x", "y"], args[0], env)
            if sym == "if":
                if len(args) != 3:
                    raise ValueError("if requires cond, then, else")
                cond_val = evaluate(args[0], env)
                cond_is_true = True
                if isinstance(cond_val, NumberValue) and cond_val.val == 0:
                    cond_is_true = False
                elif isinstance(cond_val, NullValue):
                    cond_is_true = False
                return evaluate(args[1] if cond_is_true else args[2], env)
            if sym == "cond":
                for branch in args:
                    branch_items = _list_to_py(branch)
                    if len(branch_items) != 2:
                        raise ValueError("cond branch requires [cond expr]")
                    b_cond = evaluate(branch_items[0], env)
                    is_true = True
                    if isinstance(b_cond, NumberValue) and b_cond.val == 0:
                        is_true = False
                    elif isinstance(b_cond, NullValue):
                        is_true = False
                    if is_true:
                        return evaluate(branch_items[1], env)
                return NullValue()
            if sym == "let":
                if len(args) != 2:
                    raise ValueError("let requires bindings and body")
                bindings = _list_to_py(args[0])
                child_env = Environment(parent=env)
                for b in bindings:
                    b_items = _list_to_py(b)
                    if len(b_items) != 2 or not isinstance(b_items[0], SymbolValue):
                        raise ValueError("invalid let binding")
                    val = evaluate(b_items[1], env)
                    child_env.define(b_items[0].name, val)
                return evaluate(args[1], child_env)
            if sym == "list":
                eval_args = [evaluate(a, env) for a in args]
                return _to_cons_list(eval_args)
            if sym == "lazy":
                if len(args) != 1:
                    raise ValueError("lazy requires 1 expression")
                return LazyValue(args[0], env)

        # Standard function application
        fn = evaluate(car, env)
        eval_args = [evaluate(a, env) for a in args]

        if isinstance(fn, ClosureValue):
            call_env = Environment(parent=fn.env)
            if len(fn.params) != len(eval_args):
                raise ValueError(f"arity mismatch: expected {len(fn.params)}, got {len(eval_args)}")
            for p_name, arg_val in zip(fn.params, eval_args):
                call_env.define(p_name, arg_val)
            return evaluate(fn.body, call_env)

        if isinstance(fn, BuiltinValue):
            return fn.fn(eval_args, env)

        raise ValueError(f"cannot call non-function: {fn}")

    raise ValueError(f"cannot evaluate value: {expr}")


# ---------------------------------------------------------------------------
# Global Environment Initialization (76 Builtins)
# ---------------------------------------------------------------------------

def make_global_environment() -> Environment:
    env = Environment()

    def _num(v: Value) -> int:
        if isinstance(v, NumberValue):
            return v.val
        raise ValueError(f"expected number, got {v}")

    # Arithmetic
    env.define("+", BuiltinValue("+", lambda a, _: NumberValue((_num(a[0]) + _num(a[1])) % MOD26)))
    env.define("+'", BuiltinValue("+'", lambda a, _: NumberValue((_num(a[0]) + _num(a[1])) % MOD19)))
    env.define("-", BuiltinValue("-", lambda a, _: NumberValue((_num(a[0]) - _num(a[1])) % MOD26)))
    env.define("-'", BuiltinValue("-'", lambda a, _: NumberValue((_num(a[0]) - _num(a[1])) % MOD19)))
    env.define("*", BuiltinValue("*", lambda a, _: NumberValue((_num(a[0]) * _num(a[1])) % MOD26)))
    env.define("/", BuiltinValue("/", lambda a, _: NumberValue(_num(a[0]) // _num(a[1]) if _num(a[1]) != 0 else 0)))
    env.define("%", BuiltinValue("%", lambda a, _: NumberValue(_num(a[0]) % _num(a[1]) if _num(a[1]) != 0 else 0)))
    env.define("~", BuiltinValue("~", lambda a, _: NumberValue(1 if _num(a[0]) == 0 else 0)))
    fact_lut = [1, 1, 2, 6, 24, 120, 720, 5040, 40320, 362880, 3628800, 39916800]
    env.define("!", BuiltinValue("!", lambda a, _: NumberValue(fact_lut[_num(a[0])] if 0 <= _num(a[0]) < len(fact_lut) else 0)))
    env.define("^", BuiltinValue("^", lambda a, _: NumberValue(pow(_num(a[0]), _num(a[1]), MOD26))))
    env.define("&", BuiltinValue("&", lambda a, _: NumberValue(1 if _num(a[0]) > 0 and _num(a[1]) > 0 else 0)))
    env.define("|", BuiltinValue("|", lambda a, _: NumberValue(0 if _num(a[0]) == 0 and _num(a[1]) == 0 else 1)))
    env.define("=", BuiltinValue("=", lambda a, _: NumberValue(1 if a[0] == a[1] else 0)))
    env.define("/=", BuiltinValue("/=", lambda a, _: NumberValue(0 if a[0] == a[1] else 1)))
    env.define("<", BuiltinValue("<", lambda a, _: NumberValue(1 if _num(a[0]) < _num(a[1]) else 0)))
    env.define(">", BuiltinValue(">", lambda a, _: NumberValue(1 if _num(a[0]) > _num(a[1]) else 0)))
    env.define("<=", BuiltinValue("<=", lambda a, _: NumberValue(1 if _num(a[0]) <= _num(a[1]) else 0)))
    env.define(">=", BuiltinValue(">=", lambda a, _: NumberValue(1 if _num(a[0]) >= _num(a[1]) else 0)))
    env.define("gcd", BuiltinValue("gcd", lambda a, _: NumberValue(math.gcd(_num(a[0]), _num(a[1])))))
    env.define("lcm", BuiltinValue("lcm", lambda a, _: NumberValue(math.lcm(_num(a[0]), _num(a[1])))))
    env.define("min", BuiltinValue("min", lambda a, _: NumberValue(min(_num(a[0]), _num(a[1])))))
    env.define("max", BuiltinValue("max", lambda a, _: NumberValue(max(_num(a[0]), _num(a[1])))))

    # Core
    env.define("cons", BuiltinValue("cons", lambda a, _: ConsValue(a[0], a[1])))
    env.define("car", BuiltinValue("car", lambda a, _: a[0].car if isinstance(a[0], ConsValue) else NullValue()))
    env.define("cdr", BuiltinValue("cdr", lambda a, _: a[0].cdr if isinstance(a[0], ConsValue) else NullValue()))
    def _atom_tag(v: Value) -> int:
        if isinstance(v, NumberValue): return 0
        if isinstance(v, SymbolValue): return 1
        if isinstance(v, ConsValue): return 2
        if isinstance(v, ClosureValue): return 3
        if isinstance(v, MacroValue): return 4
        if isinstance(v, LazyValue): return 11
        if isinstance(v, NullValue): return 12
        return 1
    env.define("atom", BuiltinValue("atom", lambda a, _: NumberValue(_atom_tag(a[0]))))
    env.define("print", BuiltinValue("print", lambda a, _: a[0]))

    # Sequence and Combinator Functions
    env.define("iota", BuiltinValue("iota", lambda a, _: _to_cons_list([NumberValue(i) for i in range(_num(a[0]))])))
    env.define("size", BuiltinValue("size", lambda a, _: NumberValue(len(_list_to_py(a[0])))))
    env.define("nth", BuiltinValue("nth", lambda a, _: _list_to_py(a[1])[_num(a[0])]))
    env.define("rev", BuiltinValue("rev", lambda a, _: _to_cons_list(list(reversed(_list_to_py(a[0]))))))
    env.define("append", BuiltinValue("append", lambda a, _: _to_cons_list(_list_to_py(a[0]) + _list_to_py(a[1]))))
    env.define("append'", BuiltinValue("append'", lambda a, _: _to_cons_list(_list_to_py(a[0]) + [a[1]])))
    env.define("take", BuiltinValue("take", lambda a, _: _to_cons_list(_list_to_py(a[1])[:_num(a[0])])))
    env.define("drop", BuiltinValue("drop", lambda a, _: _to_cons_list(_list_to_py(a[1])[_num(a[0]):])))
    env.define("id", BuiltinValue("id", lambda a, _: a[0]))
    env.define("null", NullValue())

    # Higher Order / Combinators
    def _map(args: list[Value], current_env: Environment) -> Value:
        fn = args[0]
        items = _list_to_py(args[1])
        res = []
        for it in items:
            call_expr = ConsValue(fn, ConsValue(ConsValue(SymbolValue("'"), ConsValue(it, NullValue())), NullValue()))
            res.append(evaluate(call_expr, current_env))
        return _to_cons_list(res)
    env.define("map", BuiltinValue("map", _map))

    def _filter(args: list[Value], current_env: Environment) -> Value:
        fn = args[0]
        items = _list_to_py(args[1])
        res = []
        for it in items:
            call_expr = ConsValue(fn, ConsValue(ConsValue(SymbolValue("'"), ConsValue(it, NullValue())), NullValue()))
            c = evaluate(call_expr, current_env)
            if not (isinstance(c, NumberValue) and c.val == 0):
                res.append(it)
        return _to_cons_list(res)
    env.define("filter", BuiltinValue("filter", _filter))

    def _fold(args: list[Value], current_env: Environment) -> Value:
        fn = args[0]
        acc = args[1]
        items = _list_to_py(args[2])
        for it in items:
            call_expr = _to_cons_list([fn, ConsValue(SymbolValue("'"), ConsValue(acc, NullValue())), ConsValue(SymbolValue("'"), ConsValue(it, NullValue()))])
            acc = evaluate(call_expr, current_env)
        return acc
    env.define("fold", BuiltinValue("fold", _fold))

    def _atop(args: list[Value], current_env: Environment) -> Value:
        f = args[0]
        g = args[1]
        # returns (lambda (x) (f (g x)))
        body = ConsValue(f, ConsValue(ConsValue(g, ConsValue(SymbolValue("x"), NullValue())), NullValue()))
        return ClosureValue(["x"], body, current_env)
    env.define("atop", BuiltinValue("atop", _atop))

    def _bind(args: list[Value], current_env: Environment) -> Value:
        f = args[0]
        bound_arg = args[1]
        # returns (lambda (y) (f bound_arg y))
        body = _to_cons_list([f, ConsValue(SymbolValue("'"), ConsValue(bound_arg, NullValue())), SymbolValue("y")])
        return ClosureValue(["y"], body, current_env)
    env.define("bind", BuiltinValue("bind", _bind))

    return env

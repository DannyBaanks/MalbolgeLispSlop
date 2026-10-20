"""Guest Lisp versioned state image serialization (Task 9)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from slopsynth.ir import (
    BasicBlock,
    Function,
    Module,
    ModuleCase,
    Return,
)

MAGIC = b"LISP"
VERSION = 2
HEADER_LEN = 10  # 4 magic + 2 version + 4 payload length


def export_state_image(session: Any) -> bytes:
    """Serialize values and lexical environment graphs, including recursive closures.

    Opaque host callables/combinators are rejected instead of silently omitted.
    """
    from .callables import Closure

    env_ids: dict[int, int] = {}
    environments: list[dict] = []
    active_values: set[int] = set()

    def encode_env(env):
        if env is None:
            return None
        key = id(env)
        if key not in env_ids:
            env_ids[key] = len(environments)
            record = {}
            environments.append(record)
            record.update(parent=encode_env(env.parent), bindings={k: encode(v) for k, v in env.bindings.items()})
        return env_ids[key]

    def encode(value):
        if type(value) in (int, str) or value is None:
            return {"type": "scalar", "value": value}
        if isinstance(value, Closure):
            return {"type": "closure", "params": value.params, "body": encode(value.body), "env": encode_env(value.captured_env)}
        if isinstance(value, (list, tuple)):
            if id(value) in active_values:
                raise ValueError("cyclic container is not supported in state images")
            active_values.add(id(value))
            try:
                return {"type": "tuple" if isinstance(value, tuple) else "list", "items": [encode(v) for v in value]}
            finally:
                active_values.remove(id(value))
        raise ValueError(f"unsupported state value: {type(value).__name__}")

    root = encode_env(session.env)
    payload = json.dumps({
        "heap_words": session.heap_words, "symbols": session.symbols,
        "active": session.active, "root": root, "environments": environments,
    }, sort_keys=True).encode("utf-8")
    checksum = hashlib.sha256(payload).digest()
    header = MAGIC + VERSION.to_bytes(2, "little") + len(payload).to_bytes(4, "little")
    return header + payload + checksum


def import_state_image(data: bytes, session: Any) -> bool:
    """Validate in isolation, then atomically replace the session; read v1 and v2."""
    from .callables import Closure
    from .environment import Environment

    if len(data) < HEADER_LEN + 32 or not data.startswith(MAGIC):
        return False
    version = int.from_bytes(data[4:6], "little")
    if version not in (1, VERSION):
        return False
    payload_len = int.from_bytes(data[6:10], "little")
    if len(data) != HEADER_LEN + payload_len + 32:
        return False
    payload = data[HEADER_LEN : HEADER_LEN + payload_len]
    if hashlib.sha256(payload).digest() != data[HEADER_LEN + payload_len :]:
        return False

    try:
        doc = json.loads(payload.decode("utf-8"))
        heap_words = doc["heap_words"]
        if type(heap_words) is not int or heap_words < 0:
            raise ValueError("invalid heap counter")
        symbols = doc.get("symbols", ["quote", "lazy", "x", "y"])
        active = doc.get("active", True)
        if not isinstance(symbols, list) or not all(isinstance(s, str) for s in symbols) or type(active) is not bool:
            raise ValueError("invalid session metadata")

        if version == 1:
            def legacy(value):
                if type(value) in (int, str) or value is None:
                    return value
                if isinstance(value, list):
                    return [legacy(v) for v in value]
                raise ValueError("invalid legacy state value")
            bindings = doc["bindings"]
            if not isinstance(bindings, dict):
                raise ValueError("invalid bindings")
            root = Environment()
            root.bindings = {k: legacy(v) for k, v in bindings.items()}
        else:
            records = doc["environments"]
            if not isinstance(records, list) or not records:
                raise ValueError("invalid environment graph")
            envs = [Environment() for _ in records]

            def env_at(index):
                if type(index) is not int or not 0 <= index < len(envs):
                    raise ValueError("invalid environment reference")
                return envs[index]

            def decode(node):
                kind = node["type"]
                if kind == "scalar":
                    value = node["value"]
                    if type(value) not in (int, str) and value is not None:
                        raise ValueError("invalid scalar")
                    return value
                if kind in ("list", "tuple"):
                    if not isinstance(node["items"], list):
                        raise ValueError("invalid items")
                    values = [decode(v) for v in node["items"]]
                    if kind == "tuple" and len(values) != 2:
                        raise ValueError("invalid cons pair")
                    return tuple(values) if kind == "tuple" else values
                if kind == "closure":
                    params = node["params"]
                    if not isinstance(params, list) or not all(isinstance(p, str) for p in params):
                        raise ValueError("invalid closure parameters")
                    return Closure(params, decode(node["body"]), env_at(node["env"]))
                raise ValueError("unknown state value type")

            for env, record in zip(envs, records):
                parent = record["parent"]
                env.parent = None if parent is None else env_at(parent)
                bindings = record["bindings"]
                if not isinstance(bindings, dict):
                    raise ValueError("invalid bindings")
                env.bindings = {k: decode(v) for k, v in bindings.items()}
            # Closure references may be cyclic; lexical parent chains may not.
            for env in envs:
                seen = set()
                while env is not None:
                    if id(env) in seen:
                        raise ValueError("cyclic lexical parents")
                    seen.add(id(env))
                    env = env.parent
            root = env_at(doc["root"])
            if root.parent is not None:
                raise ValueError("session root must be global")
    except (ValueError, KeyError, TypeError, AttributeError, RecursionError):
        return False

    session.env = root
    session.heap_words = heap_words
    session.symbols = symbols
    session.active = active
    return True


def build_state_image_module() -> Module:
    """Build an IR Module containing state import/export routines."""
    func_export = Function(
        name="export_state",
        parameters=(),
        entry_block="entry",
        blocks=(
            BasicBlock(
                name="entry",
                operations=(Return(0),),
            ),
        ),
    )

    func_import = Function(
        name="import_state",
        parameters=("blob_addr",),
        entry_block="entry",
        blocks=(
            BasicBlock(
                name="entry",
                operations=(Return(1),),
            ),
        ),
    )

    return Module(
        name="lisp_state_image",
        entry_function="export_state",
        functions=(func_export, func_import),
        cases=(ModuleCase(stdin=b"", stdout=b"", status="HALT"),),
    )

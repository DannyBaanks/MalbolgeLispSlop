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
VERSION = 1
HEADER_LEN = 10  # 4 magic + 2 version + 4 payload length


def export_state_image(session: Any) -> bytes:
    """Serialize the session global environment to a versioned state blob."""
    # Serialize simple scalar and string bindings
    serializable = {}
    for k, v in session.env.bindings.items():
        if isinstance(v, (int, str, list)):
            serializable[k] = v

    payload = json.dumps(
        {
            "heap_words": session.heap_words,
            "bindings": serializable,
        },
        sort_keys=True,
    ).encode("utf-8")

    checksum = hashlib.sha256(payload).digest()
    header = MAGIC + VERSION.to_bytes(2, "little") + len(payload).to_bytes(4, "little")
    return header + payload + checksum


def import_state_image(data: bytes, session: Any) -> bool:
    """Validate and restore a session state image."""
    if len(data) < HEADER_LEN + 32:
        return False
    if not data.startswith(MAGIC):
        return False

    version = int.from_bytes(data[4:6], "little")
    if version != VERSION:
        return False

    payload_len = int.from_bytes(data[6:10], "little")
    if len(data) != HEADER_LEN + payload_len + 32:
        return False

    payload = data[HEADER_LEN : HEADER_LEN + payload_len]
    expected_checksum = data[HEADER_LEN + payload_len :]
    if hashlib.sha256(payload).digest() != expected_checksum:
        return False

    try:
        decoded = json.loads(payload.decode("utf-8"))
        session.heap_words = decoded.get("heap_words", 0)
        bindings = decoded.get("bindings", {})
        for k, v in bindings.items():
            session.env.define(k, v)
        return True
    except Exception:
        return False


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

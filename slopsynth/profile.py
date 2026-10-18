"""Validated target-profile data for automatic fixed-3^19 synthesis."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from types import MappingProxyType
from typing import Mapping


_DISPATCH_NAMES = frozenset(
    {"jump", "output", "input", "rotate", "move", "crazy", "nop", "halt"}
)
_LOADER_NAMES = frozenset({"raw", "canonical"})


@dataclass(frozen=True, slots=True)
class LoaderRule:
    skip_whitespace: bool
    whitespace_is_cell: bool
    validate_opcodes: bool
    whitespace_bytes: tuple[int, ...]
    position_cycle: int | None
    byte_min: int
    byte_max_exclusive: int


@dataclass(frozen=True, slots=True)
class Profile:
    name: str
    trits: int
    end: int
    eof_value: int
    dispatch: Mapping[str, int]
    loaders: Mapping[str, LoaderRule]


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _integer(value: object, label: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{label} must be an integer")
    return value


def _boolean(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{label} must be a boolean")
    return value


def _loader_rule(name: str, value: object) -> LoaderRule:
    data = _object(value, f"loaders.{name}")
    required = {
        "skip_whitespace",
        "whitespace_is_cell",
        "validate_opcodes",
        "whitespace_bytes",
        "position_cycle",
        "byte_min",
        "byte_max_exclusive",
    }
    if set(data) != required:
        raise ValueError(f"loaders.{name} fields must be {sorted(required)}")

    whitespace = data["whitespace_bytes"]
    if not isinstance(whitespace, list) or any(
        type(byte) is not int or not 0 <= byte <= 255 for byte in whitespace
    ):
        raise ValueError(f"loaders.{name}.whitespace_bytes must contain byte values")
    if len(set(whitespace)) != len(whitespace):
        raise ValueError(f"loaders.{name}.whitespace_bytes must be unique")

    raw_cycle = data["position_cycle"]
    if raw_cycle is None:
        position_cycle = None
    else:
        position_cycle = _integer(raw_cycle, f"loaders.{name}.position_cycle")
        if position_cycle <= 0:
            raise ValueError(f"loaders.{name}.position_cycle must be positive")

    byte_min = _integer(data["byte_min"], f"loaders.{name}.byte_min")
    byte_max = _integer(
        data["byte_max_exclusive"], f"loaders.{name}.byte_max_exclusive"
    )
    if not 0 <= byte_min < byte_max <= 256:
        raise ValueError(f"loaders.{name} byte range must be inside [0, 256]")

    rule = LoaderRule(
        skip_whitespace=_boolean(data["skip_whitespace"], f"loaders.{name}.skip_whitespace"),
        whitespace_is_cell=_boolean(
            data["whitespace_is_cell"], f"loaders.{name}.whitespace_is_cell"
        ),
        validate_opcodes=_boolean(
            data["validate_opcodes"], f"loaders.{name}.validate_opcodes"
        ),
        whitespace_bytes=tuple(whitespace),
        position_cycle=position_cycle,
        byte_min=byte_min,
        byte_max_exclusive=byte_max,
    )
    if name == "raw" and (
        rule.skip_whitespace or not rule.whitespace_is_cell or rule.validate_opcodes
    ):
        raise ValueError("loaders.raw must count bytes without opcode validation")
    if name == "canonical" and (
        not rule.skip_whitespace
        or rule.whitespace_is_cell
        or not rule.validate_opcodes
        or rule.position_cycle is None
    ):
        raise ValueError("loaders.canonical must skip whitespace and validate opcodes")
    return rule


def load_profile(path: Path) -> Profile:
    """Load and validate a JSON machine profile from ``path``."""
    try:
        data = _object(json.loads(path.read_text(encoding="utf-8")), "profile")
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not load profile {path}: {exc}") from exc

    required = {
        "schema_version",
        "name",
        "trits",
        "end",
        "eof_value",
        "dispatch",
        "loaders",
    }
    if set(data) != required:
        raise ValueError(f"profile fields must be {sorted(required)}")
    if _integer(data["schema_version"], "schema_version") != 1:
        raise ValueError("unsupported profile schema_version")

    name = data["name"]
    if not isinstance(name, str) or not name:
        raise ValueError("name must be a non-empty string")
    trits = _integer(data["trits"], "trits")
    end = _integer(data["end"], "end")
    eof_value = _integer(data["eof_value"], "eof_value")
    if trits <= 0 or end != 3**trits or eof_value != end - 1:
        raise ValueError("profile trits, end, and eof_value are inconsistent")

    dispatch_data = _object(data["dispatch"], "dispatch")
    if set(dispatch_data) != _DISPATCH_NAMES:
        raise ValueError(f"dispatch names must be {sorted(_DISPATCH_NAMES)}")
    dispatch: dict[str, int] = {}
    for opname, raw_index in dispatch_data.items():
        index = _integer(raw_index, f"dispatch.{opname}")
        if not 0 <= index < 94:
            raise ValueError(f"dispatch.{opname} index must be in [0, 94)")
        dispatch[opname] = index
    if len(set(dispatch.values())) != len(dispatch):
        raise ValueError("dispatch indices must be unique")

    loader_data = _object(data["loaders"], "loaders")
    if set(loader_data) != _LOADER_NAMES:
        raise ValueError(f"loaders must define exactly {sorted(_LOADER_NAMES)}")
    loaders = {
        loader_name: _loader_rule(loader_name, loader_data[loader_name])
        for loader_name in sorted(_LOADER_NAMES)
    }
    if loaders["raw"].whitespace_bytes != loaders["canonical"].whitespace_bytes:
        raise ValueError("raw and canonical loaders must identify the same whitespace")

    return Profile(
        name=name,
        trits=trits,
        end=end,
        eof_value=eof_value,
        dispatch=MappingProxyType(dispatch),
        loaders=MappingProxyType(loaders),
    )

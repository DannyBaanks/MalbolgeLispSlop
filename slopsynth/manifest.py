"""Stable manifests and integrity checks for generated guest images."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .ir_json import load_program
from .profile import load_profile
from .search import SearchBudget, SemanticProof, SynthesisStatus, synthesize_program


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} {path} must contain a JSON object")
    return value


def build_manifest(
    *,
    profile_path: Path,
    program_path: Path,
    artifact: bytes,
    generator_revision: str,
    algorithm: str,
    configuration: dict[str, Any],
    explored_nodes: int,
    validation: dict[str, Any],
    generator_sha256: str | None = None,
) -> dict[str, Any]:
    """Build a timestamp-free manifest from exact input and output bytes."""
    if not isinstance(artifact, bytes):
        raise ValueError("artifact must be bytes")
    if not generator_revision:
        raise ValueError("generator_revision must not be empty")
    if not algorithm:
        raise ValueError("algorithm must not be empty")
    if type(explored_nodes) is not int or explored_nodes < 0:
        raise ValueError("explored_nodes must be a non-negative integer")
    if not isinstance(configuration, dict) or not isinstance(validation, dict):
        raise ValueError("configuration and validation must be objects")

    profile = _read_json(profile_path, "profile")
    program = _read_json(program_path, "program")
    try:
        frozen_configuration = json.loads(
            json.dumps(configuration, sort_keys=True, allow_nan=False)
        )
        frozen_validation = json.loads(
            json.dumps(validation, sort_keys=True, allow_nan=False)
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"manifest fields must be JSON-compatible: {exc}") from exc

    return {
        "schema_version": 1,
        "target_profile": profile.get("name"),
        "profile_path": profile_path.name,
        "profile_sha256": sha256_file(profile_path),
        "program_name": program.get("name"),
        "program_path": program_path.name,
        "program_sha256": sha256_file(program_path),
        "generator_revision": generator_revision,
        "generator_sha256": generator_sha256,
        "algorithm": algorithm,
        "configuration": frozen_configuration,
        "explored_nodes": explored_nodes,
        "synthesis_status": frozen_validation.get("synthesis_status", "FOUND"),
        "artifact_sha256": sha256_bytes(artifact),
        "validation": frozen_validation,
    }


def manifest_bytes(manifest: dict[str, Any]) -> bytes:
    """Serialize a manifest deterministically with a final newline."""
    try:
        encoded = json.dumps(
            manifest,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"manifest must contain JSON-compatible values: {exc}") from exc
    return (encoded + "\n").encode("utf-8")


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    """Write a new manifest file and refuse to replace an existing one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(manifest_bytes(manifest))


def verify_manifest(
    manifest_path: Path,
    artifact_path: Path,
    *,
    profile_path: Path,
    program_path: Path,
) -> dict[str, Any]:
    """Verify digests and recompute the certified lowering byte for byte."""
    manifest = _read_json(manifest_path, "manifest")
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported manifest schema_version")
    if manifest.get("artifact_sha256") != sha256_file(artifact_path):
        raise ValueError("artifact SHA-256 mismatch")
    if manifest.get("profile_sha256") != sha256_file(profile_path):
        raise ValueError("profile SHA-256 mismatch")
    if manifest.get("program_sha256") != sha256_file(program_path):
        raise ValueError("program SHA-256 mismatch")
    validation = manifest.get("validation")
    if not isinstance(validation, dict) or validation.get("status") != "PASS":
        raise ValueError("manifest does not record a passing guest validation")
    if manifest.get("synthesis_status") != "FOUND":
        raise ValueError("manifest does not record a FOUND synthesis result")
    if validation.get("synthesis_status") != "FOUND":
        raise ValueError("manifest validation does not record FOUND synthesis")
    semantic_proof = validation.get("semantic_proof")
    if not isinstance(semantic_proof, str) or not semantic_proof:
        raise ValueError("manifest does not record a semantic lowering proof")
    if semantic_proof not in {proof.value for proof in SemanticProof}:
        raise ValueError("manifest records an unrecognized semantic lowering proof")

    if semantic_proof != SemanticProof.DIRECT_M1_LOWERING_V1.value:
        raise ValueError("manifest proof has no verifier implementation")
    if manifest.get("algorithm") != "profile-derived-direct-lowering-v1":
        raise ValueError("manifest algorithm does not match its semantic proof")

    configuration = manifest.get("configuration")
    if not isinstance(configuration, dict) or configuration.get("loader") != "canonical":
        raise ValueError("manifest does not contain a canonical lowering configuration")
    try:
        budget = SearchBudget(
            max_cells=configuration["max_cells"],
            max_nodes=configuration["max_nodes"],
            max_steps=configuration["max_steps"],
            max_address=configuration["max_address"],
        )
        profile = load_profile(profile_path)
        canonical_profile = load_profile(
            Path(__file__).resolve().parents[1] / "profiles" / "fixed19.json"
        )
        if (
            profile != canonical_profile
            or manifest.get("target_profile") != profile.name
        ):
            raise ValueError("manifest profile does not match the bundled fixed profile")
        program = load_program(program_path)
        synthesis = synthesize_program(program, profile, budget)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"manifest certified lowering could not be recomputed: {exc}") from exc

    if (
        synthesis.status is not SynthesisStatus.FOUND
        or synthesis.semantic_proof is None
        or synthesis.semantic_proof.value != semantic_proof
        or synthesis.image != artifact_path.read_bytes()
        or type(manifest.get("explored_nodes")) is not int
        or manifest.get("explored_nodes") != synthesis.explored_nodes
    ):
        raise ValueError("artifact does not match certified semantic lowering")
    return manifest

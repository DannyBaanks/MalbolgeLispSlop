"""Stable manifests and integrity checks for generated guest images."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
from typing import Any

from .ir import Halt, Program, ReadA, WriteA
from .ir_json import load_program
from .profile import load_profile
from .search import SearchBudget, SemanticProof, SynthesisStatus, synthesize_program
from tools.guest_runner import GuestStatus, RunConfig, run_guest


_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_GIT_REVISION_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
_GENERATOR_SOURCE_FILES = (
    "slopsynth/encode.py",
    "slopsynth/search.py",
    "slopsynth/model.py",
    "slopsynth/profile.py",
    "slopsynth/ir.py",
    "slopsynth/ir_json.py",
    "slopsynth/manifest.py",
    "tools/synthesize_guest.py",
    "tools/guest_runner.py",
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def generator_source_digest(root: Path, *, revision: str | None = None) -> str:
    """Hash generator sources from the worktree or one exact Git revision."""
    digest = hashlib.sha256()
    if revision is not None:
        if _GIT_REVISION_PATTERN.fullmatch(revision) is None:
            raise ValueError("generator_revision must be a full 40-character Git commit")
        commit = subprocess.run(
            ["git", "cat-file", "-e", f"{revision}^{{commit}}"],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if commit.returncode != 0:
            raise ValueError("generator_revision is not a commit in this repository")

    for relative in _GENERATOR_SOURCE_FILES:
        if revision is None:
            content = (root / relative).read_bytes()
        else:
            result = subprocess.run(
                ["git", "show", f"{revision}:{relative}"],
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if result.returncode != 0:
                raise ValueError(
                    f"generator_revision does not contain source file {relative}"
                )
            content = result.stdout
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
    return digest.hexdigest()


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


def _validation_inputs(program: Program) -> tuple[bytes, ...]:
    read_count = sum(isinstance(operation, ReadA) for operation in program.operations)
    length = max(1, read_count)
    samples = [bytes([value]) * length for value in (0x41, 0x7A, 0x00, 0xFF)]
    samples.append(b"")
    return tuple(samples)


def _expected_stdout(program: Program, stdin: bytes, eof_value: int) -> bytes:
    accumulator = 0
    input_position = 0
    stdout = bytearray()
    for operation in program.operations:
        if isinstance(operation, ReadA):
            if operation.destination != "A":
                raise ValueError("certified direct lowering can read only into A")
            if input_position < len(stdin):
                accumulator = stdin[input_position]
                input_position += 1
            else:
                accumulator = eof_value
        elif isinstance(operation, WriteA):
            if operation.value != "A":
                raise ValueError("certified direct lowering can write only from A")
            stdout.append(accumulator & 0xFF)
        elif not isinstance(operation, Halt):
            raise ValueError("certified direct lowering contains an unsupported operation")
    return bytes(stdout)


def _verify_guest_validation(
    validation: dict[str, Any],
    artifact_path: Path,
    program: Program,
    *,
    max_steps: int,
    eof_value: int,
    engine_path: Path,
) -> None:
    """Replay every recorded M1 validation case against the real fixed19 VM."""
    if validation.get("guest_status") != GuestStatus.HALT.value:
        raise ValueError("manifest guest_status must be HALT")
    engine_digest = validation.get("engine_sha256")
    if (
        not isinstance(engine_digest, str)
        or _SHA256_PATTERN.fullmatch(engine_digest) is None
        or engine_digest != sha256_file(engine_path)
    ):
        raise ValueError("manifest guest VM engine SHA-256 mismatch")
    if validation.get("loader") != "canonical":
        raise ValueError("manifest guest validation loader must be canonical")
    if type(validation.get("max_steps")) is not int or validation["max_steps"] != max_steps:
        raise ValueError("manifest guest validation max_steps does not match synthesis bounds")

    timeout_seconds = validation.get("timeout_seconds")
    try:
        valid_timeout = (
            not isinstance(timeout_seconds, bool)
            and isinstance(timeout_seconds, (int, float))
            and math.isfinite(timeout_seconds)
            and timeout_seconds > 0
        )
    except OverflowError:
        valid_timeout = False
    if not valid_timeout:
        raise ValueError("manifest guest validation timeout_seconds is invalid")
    address_space_bytes = validation.get("address_space_bytes")
    output_bytes = validation.get("output_bytes")
    if type(address_space_bytes) is not int or address_space_bytes <= 0:
        raise ValueError("manifest guest validation address_space_bytes is invalid")
    if type(output_bytes) is not int or output_bytes < 0:
        raise ValueError("manifest guest validation output_bytes is invalid")

    # Cap untrusted manifest limits while replaying. Passing with stricter
    # limits still proves the recorded bounded guest behavior.
    run_config = RunConfig(
        loader="canonical",
        max_steps=max_steps,
        timeout_seconds=min(float(timeout_seconds), 5.0),
        address_space_bytes=min(address_space_bytes, 536_870_912),
        output_bytes=min(output_bytes, 1_048_576),
    )
    cases = validation.get("cases")
    inputs = _validation_inputs(program)
    if not isinstance(cases, list) or len(cases) != len(inputs):
        raise ValueError("manifest guest validation cases are incomplete")

    required_case_fields = {
        "stdin_hex",
        "expected_stdout_hex",
        "observed_stdout_hex",
        "guest_status",
        "returncode",
        "matches",
    }
    for case, stdin in zip(cases, inputs, strict=True):
        if not isinstance(case, dict) or set(case) != required_case_fields:
            raise ValueError("manifest guest validation case has an invalid schema")
        expected = _expected_stdout(program, stdin, eof_value)
        if (
            case.get("stdin_hex") != stdin.hex()
            or case.get("expected_stdout_hex") != expected.hex()
            or case.get("matches") is not True
        ):
            raise ValueError("manifest guest validation case does not match the certified goal")
        if type(case.get("returncode")) is not int or case["returncode"] != 0:
            raise ValueError("manifest guest validation case returncode must be integer 0")

        guest = run_guest(artifact_path, stdin, run_config, engine_path=engine_path)
        if (
            guest.status is not GuestStatus.HALT
            or guest.returncode != 0
            or guest.stdout != expected
            or case.get("observed_stdout_hex") != guest.stdout.hex()
            or case.get("guest_status") != guest.status.value
            or case.get("returncode") != guest.returncode
        ):
            raise ValueError("manifest guest validation case failed real-VM replay")


def verify_manifest(
    manifest_path: Path,
    artifact_path: Path,
    *,
    profile_path: Path,
    program_path: Path,
    engine_path: Path | None = None,
) -> dict[str, Any]:
    """Verify digests and recompute the certified lowering byte for byte."""
    manifest = _read_json(manifest_path, "manifest")
    if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        raise ValueError("unsupported manifest schema_version")
    if manifest.get("artifact_sha256") != sha256_file(artifact_path):
        raise ValueError("artifact SHA-256 mismatch")
    if manifest.get("profile_sha256") != sha256_file(profile_path):
        raise ValueError("profile SHA-256 mismatch")
    if manifest.get("program_sha256") != sha256_file(program_path):
        raise ValueError("program SHA-256 mismatch")
    if manifest.get("profile_path") != profile_path.name:
        raise ValueError("manifest profile_path does not match the supplied profile")
    program_metadata = _read_json(program_path, "program")
    if manifest.get("program_name") != program_metadata.get("name"):
        raise ValueError("manifest program_name does not match the supplied program")
    if manifest.get("program_path") != program_path.name:
        raise ValueError("manifest program_path does not match the supplied program")
    generator_revision = manifest.get("generator_revision")
    generator_digest = manifest.get("generator_sha256")
    if not isinstance(generator_revision, str) or _GIT_REVISION_PATTERN.fullmatch(
        generator_revision
    ) is None:
        raise ValueError("manifest generator_revision must be a full 40-character Git commit")
    if not isinstance(generator_digest, str) or _SHA256_PATTERN.fullmatch(
        generator_digest
    ) is None:
        raise ValueError("manifest generator source SHA-256 is invalid")
    try:
        expected_generator_digest = generator_source_digest(
            Path(__file__).resolve().parents[1], revision=generator_revision
        )
    except ValueError as exc:
        raise ValueError(f"manifest generator_revision is invalid: {exc}") from exc
    if generator_digest != expected_generator_digest:
        raise ValueError("manifest generator source SHA-256 does not match its revision")
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
    selected_vm_path = (
        engine_path
        if engine_path is not None
        else Path(__file__).resolve().parents[1] / "build" / "bolge19"
    )
    try:
        vm_path = selected_vm_path.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"manifest guest VM engine path cannot be resolved: {exc}") from exc

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
    _verify_guest_validation(
        validation,
        artifact_path,
        program,
        max_steps=budget.max_steps,
        eof_value=profile.eof_value,
        engine_path=vm_path,
    )
    return manifest

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from slopsynth.manifest import build_manifest, manifest_bytes, verify_manifest, write_manifest


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "profiles" / "fixed19.json"
PROGRAM = ROOT / "examples" / "echo.json"


class SynthesisManifestTests(unittest.TestCase):
    def build(self, image: bytes) -> dict[str, object]:
        return build_manifest(
            profile_path=PROFILE,
            program_path=PROGRAM,
            artifact=image,
            generator_revision="codex-test-revision",
            algorithm="profile-derived-direct-lowering-v1",
            configuration={
                "loader": "canonical",
                "max_cells": 3,
                "max_nodes": 10000,
                "max_steps": 8,
                "max_address": 8,
            },
            explored_nodes=1,
            validation={
                "status": "PASS",
                "guest_status": "HALT",
                "synthesis_status": "FOUND",
                "semantic_proof": "direct-m1-lowering-v1",
                "engine_sha256": hashlib.sha256(
                    (ROOT / "build" / "bolge19").read_bytes()
                ).hexdigest(),
            },
        )

    def test_repeated_manifest_is_byte_deterministic(self) -> None:
        first = self.build(b"ubO")
        second = self.build(b"ubO")

        self.assertEqual(manifest_bytes(first), manifest_bytes(second))

    def test_manifest_write_refuses_to_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "guest.manifest.json"
            write_manifest(path, self.build(b"ubO"))
            with self.assertRaises(FileExistsError):
                write_manifest(path, self.build(b"ubO"))

    def test_manifest_rejects_changed_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "guest.mb"
            artifact.write_bytes(b"ubO")
            manifest = root / "guest.manifest.json"
            write_manifest(manifest, self.build(artifact.read_bytes()))
            artifact.write_bytes(b"ubP")

            with self.assertRaisesRegex(ValueError, "artifact SHA-256"):
                verify_manifest(
                    manifest,
                    artifact,
                    profile_path=PROFILE,
                    program_path=PROGRAM,
                )

    def test_manifest_requires_semantic_lowering_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "guest.mb"
            artifact.write_bytes(b"ubO")
            manifest_data = self.build(artifact.read_bytes())
            validation = manifest_data["validation"]
            assert isinstance(validation, dict)
            validation.pop("semantic_proof")
            manifest = root / "guest.manifest.json"
            manifest.write_bytes(manifest_bytes(manifest_data))

            with self.assertRaisesRegex(ValueError, "semantic lowering proof"):
                verify_manifest(
                    manifest,
                    artifact,
                    profile_path=PROFILE,
                    program_path=PROGRAM,
                )

    def test_manifest_rejects_unrecognized_semantic_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "guest.mb"
            artifact.write_bytes(b"ubO")
            manifest_data = self.build(artifact.read_bytes())
            validation = manifest_data["validation"]
            assert isinstance(validation, dict)
            validation["semantic_proof"] = "unverified-observational-candidate"
            manifest = root / "guest.manifest.json"
            manifest.write_bytes(manifest_bytes(manifest_data))

            with self.assertRaisesRegex(
                ValueError, "unrecognized semantic lowering proof"
            ):
                verify_manifest(
                    manifest,
                    artifact,
                    profile_path=PROFILE,
                    program_path=PROGRAM,
                )

    def test_manifest_rejects_proof_token_for_mismatched_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "guest.mb"
            artifact.write_bytes(b"not-the-echo-image")
            manifest = root / "guest.manifest.json"
            write_manifest(manifest, self.build(artifact.read_bytes()))

            with self.assertRaisesRegex(
                ValueError, "artifact does not match certified semantic lowering"
            ):
                verify_manifest(
                    manifest,
                    artifact,
                    profile_path=PROFILE,
                    program_path=PROGRAM,
                )

    def test_manifest_rejects_same_name_profile_with_changed_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile_data = json.loads(PROFILE.read_text(encoding="utf-8"))
            profile_data["dispatch"].update(
                {"input": 65, "output": 67, "halt": 69}
            )
            spoofed_profile = root / "spoofed-profile.json"
            spoofed_profile.write_text(json.dumps(profile_data), encoding="utf-8")
            artifact = root / "guest.mb"
            artifact.write_bytes(b"ABC")
            manifest_data = build_manifest(
                profile_path=spoofed_profile,
                program_path=PROGRAM,
                artifact=artifact.read_bytes(),
                generator_revision="codex-test-revision",
                algorithm="profile-derived-direct-lowering-v1",
                configuration={
                    "loader": "canonical",
                    "max_cells": 3,
                    "max_nodes": 10000,
                    "max_steps": 8,
                    "max_address": 8,
                },
                explored_nodes=1,
                validation={
                    "status": "PASS",
                    "guest_status": "HALT",
                    "synthesis_status": "FOUND",
                    "semantic_proof": "direct-m1-lowering-v1",
                },
            )
            manifest = root / "guest.manifest.json"
            write_manifest(manifest, manifest_data)

            with self.assertRaisesRegex(
                ValueError, "does not match the bundled fixed profile"
            ):
                verify_manifest(
                    manifest,
                    artifact,
                    profile_path=spoofed_profile,
                    program_path=PROGRAM,
                )

    def test_manifest_rejects_contradictory_guest_validation_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "guest.mb"
            artifact.write_bytes(b"ubO")
            manifest_data = self.build(artifact.read_bytes())
            validation = manifest_data["validation"]
            assert isinstance(validation, dict)
            validation.update(
                {
                    "guest_status": "MAX_STEPS",
                    "loader": "raw",
                    "max_steps": 8,
                    "timeout_seconds": 5.0,
                    "address_space_bytes": 536_870_912,
                    "output_bytes": 1_048_576,
                    "cases": [
                        self._echo_validation_case("41", "41", "42", False),
                        self._echo_validation_case("7a", "7a", "7a", True),
                        self._echo_validation_case("00", "00", "00", True),
                        self._echo_validation_case("ff", "ff", "ff", True),
                        self._echo_validation_case("", "da", "da", True),
                    ],
                }
            )
            manifest = root / "guest.manifest.json"
            manifest.write_bytes(manifest_bytes(manifest_data))

            with self.assertRaisesRegex(ValueError, "guest_status.*HALT"):
                verify_manifest(
                    manifest,
                    artifact,
                    profile_path=PROFILE,
                    program_path=PROGRAM,
                )

    def test_manifest_replays_guest_cases_instead_of_trusting_claimed_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "guest.mb"
            artifact.write_bytes(b"ubO")
            manifest_data = self.build(artifact.read_bytes())
            validation = manifest_data["validation"]
            assert isinstance(validation, dict)
            validation.update(
                {
                    "loader": "canonical",
                    "max_steps": 8,
                    "timeout_seconds": 5.0,
                    "address_space_bytes": 536_870_912,
                    "output_bytes": 1_048_576,
                    "cases": [
                        self._echo_validation_case("41", "41", "42", True),
                        self._echo_validation_case("7a", "7a", "7a", True),
                        self._echo_validation_case("00", "00", "00", True),
                        self._echo_validation_case("ff", "ff", "ff", True),
                        self._echo_validation_case("", "da", "da", True),
                    ],
                }
            )
            manifest = root / "guest.manifest.json"
            manifest.write_bytes(manifest_bytes(manifest_data))

            with self.assertRaisesRegex(ValueError, "real-VM replay"):
                verify_manifest(
                    manifest,
                    artifact,
                    profile_path=PROFILE,
                    program_path=PROGRAM,
                )

    def test_manifest_rejects_boolean_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "guest.mb"
            artifact.write_bytes(b"ubO")
            manifest_data = self.build(artifact.read_bytes())
            manifest_data["schema_version"] = True
            manifest = root / "guest.manifest.json"
            manifest.write_bytes(manifest_bytes(manifest_data))

            with self.assertRaisesRegex(ValueError, "schema_version"):
                verify_manifest(
                    manifest,
                    artifact,
                    profile_path=PROFILE,
                    program_path=PROGRAM,
                )

    def test_manifest_rejects_boolean_case_returncode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "guest.mb"
            artifact.write_bytes(b"ubO")
            manifest_data = self.build(artifact.read_bytes())
            validation = manifest_data["validation"]
            assert isinstance(validation, dict)
            validation.update(
                {
                    "loader": "canonical",
                    "max_steps": 8,
                    "timeout_seconds": 5.0,
                    "address_space_bytes": 536_870_912,
                    "output_bytes": 1_048_576,
                    "cases": [
                        self._echo_validation_case("41", "41", "41", True),
                        self._echo_validation_case("7a", "7a", "7a", True),
                        self._echo_validation_case("00", "00", "00", True),
                        self._echo_validation_case("ff", "ff", "ff", True),
                        self._echo_validation_case("", "da", "da", True),
                    ],
                }
            )
            validation["cases"][0]["returncode"] = False
            manifest = root / "guest.manifest.json"
            manifest.write_bytes(manifest_bytes(manifest_data))

            with self.assertRaisesRegex(ValueError, "returncode must be integer 0"):
                verify_manifest(
                    manifest,
                    artifact,
                    profile_path=PROFILE,
                    program_path=PROGRAM,
                )

    def test_manifest_pins_replayed_vm_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "guest.mb"
            artifact.write_bytes(b"ubO")
            manifest_data = self.build(artifact.read_bytes())
            validation = manifest_data["validation"]
            assert isinstance(validation, dict)
            validation["engine_sha256"] = "0" * 64
            manifest = root / "guest.manifest.json"
            manifest.write_bytes(manifest_bytes(manifest_data))

            with self.assertRaisesRegex(ValueError, "engine SHA-256"):
                verify_manifest(
                    manifest,
                    artifact,
                    profile_path=PROFILE,
                    program_path=PROGRAM,
                )

    @staticmethod
    def _echo_validation_case(
        stdin_hex: str,
        expected_stdout_hex: str,
        observed_stdout_hex: str,
        matches: bool,
    ) -> dict[str, object]:
        return {
            "stdin_hex": stdin_hex,
            "expected_stdout_hex": expected_stdout_hex,
            "observed_stdout_hex": observed_stdout_hex,
            "guest_status": "HALT",
            "returncode": 0,
            "matches": matches,
        }

    def test_cli_outputs_are_reproducible_and_existing_paths_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outputs: list[bytes] = []
            manifests: list[bytes] = []
            first_output: Path | None = None
            first_manifest: Path | None = None
            for index in range(2):
                folder = root / f"run-{index}"
                output = folder / "echo.mb"
                manifest = folder / "echo.manifest.json"
                command = [
                    sys.executable,
                    str(ROOT / "tools" / "synthesize_guest.py"),
                    str(PROGRAM),
                    "--profile",
                    str(PROFILE),
                    "--output",
                    str(output),
                    "--manifest",
                    str(manifest),
                    "--max-cells",
                    "3",
                    "--max-nodes",
                    "10000",
                    "--max-steps",
                    "8",
                    "--max-address",
                    "8",
                ]
                completed = subprocess.run(
                    command,
                    cwd=ROOT,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=20,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                outputs.append(output.read_bytes())
                manifests.append(manifest.read_bytes())
                if index == 0:
                    first_output = output
                    first_manifest = manifest

            self.assertEqual(outputs, [b"ubO", b"ubO"])
            self.assertEqual(manifests[0], manifests[1])
            manifest_data = json.loads(manifests[0])
            self.assertEqual(manifest_data["validation"]["status"], "PASS")
            self.assertEqual(
                manifest_data["validation"]["semantic_proof"],
                "direct-m1-lowering-v1",
            )
            assert first_output is not None and first_manifest is not None
            verified = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "verify_generated_guest.py"),
                    str(first_output),
                    str(first_manifest),
                    "--profile",
                    str(PROFILE),
                    "--goal",
                    str(PROGRAM),
                ],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=20,
            )
            self.assertEqual(verified.returncode, 0, verified.stderr)
            verify_manifest(
                first_manifest,
                first_output,
                profile_path=PROFILE,
                program_path=PROGRAM,
            )

            refused = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "synthesize_guest.py"),
                    str(PROGRAM),
                    "--profile",
                    str(PROFILE),
                    "--output",
                    str(first_output),
                    "--manifest",
                    str(first_manifest),
                    "--max-cells",
                    "3",
                    "--max-nodes",
                    "10000",
                    "--max-steps",
                    "8",
                    "--max-address",
                    "8",
                ],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=20,
            )
            self.assertEqual(refused.returncode, 2)


if __name__ == "__main__":
    unittest.main()

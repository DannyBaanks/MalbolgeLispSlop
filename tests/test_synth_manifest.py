from __future__ import annotations

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
                "max_cells": 3,
                "max_nodes": 10000,
                "max_steps": 8,
                "max_address": 8,
            },
            explored_nodes=1,
            validation={"status": "PASS", "guest_status": "HALT"},
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

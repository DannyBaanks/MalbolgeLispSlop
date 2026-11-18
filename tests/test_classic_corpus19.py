"""Tests for the Classic -> Unshackled 3^19 CFG lifter and imported corpus."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from slopsynth.classic_lift import LiftedCFG, lower_lifted_cfg

ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT / "corpus/unshackled19"
BOLGE19 = ROOT / "build/bolge19"
FAST20 = ROOT / "build/fast20"


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _run_vm(binary: Path, image: Path, stdin: bytes) -> bytes:
    proc = subprocess.run([str(binary), str(image)], input=stdin, capture_output=True, timeout=20)
    assert proc.returncode == 0, f"{binary.name} failed ({proc.returncode}): {proc.stderr!r}"
    return proc.stdout


def test_tagged_echo_unified_ir(tmp_path: Path) -> None:
    cfg = LiftedCFG(
        nodes={},
        edges={},
        sccs=[],
        loop_ops={},
        kind="TAGGED_ECHO_LOOP",
        reason="unit test H15 tagged-echo IR",
    )
    low = lower_lifted_cfg(cfg)
    assert low is not None
    assert low["lowering"] == "fixed19-native-ir-loop-v1"
    img = tmp_path / "tagged.19.mb"
    img.write_bytes(low["image"])
    payload = b"\x01H\x01o\x01l\x01a\x00"
    for vm in (BOLGE19, FAST20):
        if vm.exists():
            assert _run_vm(vm, img, payload) == b"Hola"


def test_manifest_and_sha256sums() -> None:
    manifest = json.loads((CORPUS_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["total_imported"] == len(manifest["entries"]) >= 44
    sums = {}
    for line in (CORPUS_DIR / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        sums[name] = digest
    for entry in manifest["entries"]:
        p = CORPUS_DIR / entry["image_file"]
        assert p.exists()
        digest = _sha256(p.read_bytes())
        assert digest == entry["image_sha256"]
        assert sums[entry["image_file"]] == digest


@pytest.mark.parametrize(
    "entry",
    json.loads((CORPUS_DIR / "manifest.json").read_text(encoding="utf-8"))["entries"],
    ids=lambda e: e["name"],
)
def test_imported_corpus_runs_on_vms(entry: dict) -> None:
    img = CORPUS_DIR / entry["image_file"]
    stdin = bytes.fromhex(entry["probe_stdin_hex"])
    for vm in (BOLGE19, FAST20):
        if vm.exists():
            out = _run_vm(vm, img, stdin)
            assert _sha256(out) == entry["expected_stdout_sha256"]

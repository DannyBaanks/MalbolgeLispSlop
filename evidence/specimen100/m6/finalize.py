#!/usr/bin/env python3
"""Prepare source-addressed claims, then seal new research directories once."""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DOCS = ["README.md", "docs/SPECIMEN100.md", "docs/BASELINE.md",
        "docs/PARITY_MATRIX.md", "docs/RISKS.md"]


def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        while b := f.read(1 << 20):
            h.update(b)
    return h.hexdigest()


def write_new(path, value):
    with path.open("x", encoding="utf-8") as f:
        json.dump(value, f, indent=2)
        f.write("\n")


def prepare():
    rows = [
        ("M0", "VERIFIED", "Identity and init-first concatenation", "m0/inventory.json"),
        ("M1", "REPRODUCED_BYTE_EXACT", "Pinned committed artifacts and concat recipe; not source compilation", "m1/upstream.json"),
        ("M2", "REPRODUCED", "Canonical CRLF stdout and HALT tuple; bounded session only", "m2/reproduction.json"),
        ("M3", "VERIFIED_WITH_LIMITS", "Measured differential rows; not all proposed stress cases", "m3/differential_matrix.json"),
        ("M4", "PARTIAL", "Full artifact hash differs; covered bytes exact", "m4/g_check.log"),
        ("M5", "PARTIAL", "Prerequisite fails: final two bytes unknown under sealed G", "m5/gate_run1.stdout.json"),
        ("M5-behavior", "NOT_DEMONSTRATED", "No behavioral runs, no semantic counterexample or minimum", "m5/execution.json"),
        ("M6", "VERIFIED", "Suite and M0-M4 manifests executed with exit zero", "m6/execution.json"),
        ("M6-tests", "VERIFIED_WITH_WARNINGS", "93 tests OK; ResourceWarnings retained", "m6/unittest.stderr.txt"),
    ]
    claims = []
    for milestone, status, claim, rel in rows:
        path = ROOT / "evidence/specimen100" / rel
        claims.append({"milestone": milestone, "status": status, "claim": claim,
                       "source": str(path.relative_to(ROOT)), "sha256": sha(path)})
    write_new(HERE / "claims.json", {"schema": "specimen100.closeout.claims.v1",
                                    "claims": claims,
                                    "not_demonstrated": [
                                        "Full Lisp conformance and all planned stress cases",
                                        "Full raw regeneration from G",
                                        "Behavioral equivalence, semantic liveness, behavioral minimum",
                                        "Prefix-only derivation of G metadata",
                                    ]})
    write_new(HERE / "documentation_hashes.json", {rel: sha(ROOT / rel) for rel in DOCS})
    print("Prepared source-addressed claims and documentation hashes")


def seal():
    docs = json.loads((HERE / "documentation_hashes.json").read_text())
    assert all(sha(ROOT / rel) == digest for rel, digest in docs.items())
    claims = json.loads((HERE / "claims.json").read_text())["claims"]
    assert all(sha(ROOT / c["source"]) == c["sha256"] for c in claims)
    for name in ("m5", "m6"):
        directory = HERE.parent / name
        manifest = directory / "SHA256SUMS.txt"
        assert not manifest.exists(), "Refusing overwrite of sealed evidence"
        files = sorted(p for p in directory.rglob("*") if p.is_file()
                       and "__pycache__" not in p.parts)
        # Pack metadata is included; external pack artifacts have their own hashes.
        with manifest.open("x", encoding="utf-8") as f:
            for p in files:
                f.write(f"{sha(p)}  {p.relative_to(directory)}\n")
        print(f"{name}: {len(files)} files; manifest sha256={sha(manifest)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["prepare", "seal"])
    args = ap.parse_args()
    prepare() if args.mode == "prepare" else seal()

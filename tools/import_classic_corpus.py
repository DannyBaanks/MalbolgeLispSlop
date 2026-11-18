"""Import and verify Classic Malbolge (3^10) programs into MalbolgeLispSlop's
Unshackled fixed-3^19 (`fast20` / `bolge19`) corpus.

Usage:
  python3 tools/import_classic_corpus.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.classic_lift import ClassicLoadError, lift_classic_cfg, lower_lifted_cfg  # noqa: E402

ISYC_GIT = ROOT.parent
DEFAULT_SOURCES = [
    ISYC_GIT / "MALBOLGE-MB-DATABASE/tools/fixtures/hello_world_40.mb",
    *(sorted((ISYC_GIT / "MALBOLGE-MB-DATABASE/pureepoch/programs").glob("*.mal"))),
    *(sorted((ISYC_GIT / "MALBOLGE-MB-DATABASE/vm_malbolge/src").glob("*.mb"))),
    *(sorted((ISYC_GIT / "MalbolgeFree/corpus/classic").glob("*.mal"))),
    *(sorted((ISYC_GIT / "Malbolge-Translator/artifacts/quijote").glob("chapter_*/quijote_ch*_full.mal"))),
]


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def run_vm(binary: Path, image: Path, stdin: bytes = b"", timeout: float = 20.0) -> tuple[int, bytes]:
    p = subprocess.run([str(binary), str(image)], input=stdin, capture_output=True, timeout=timeout)
    return p.returncode, p.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=ROOT / "corpus/unshackled19")
    args = parser.parse_args()

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    fast20 = ROOT / "build/fast20"
    bolge19 = ROOT / "build/bolge19"
    if not fast20.exists() or not bolge19.exists():
        raise SystemExit(f"Missing VM binaries in {ROOT / 'build'}")

    entries = []
    seen_sources: set[str] = set()
    skipped = []

    for path in DEFAULT_SOURCES:
        if not path.exists():
            continue
        raw = path.read_bytes()
        src_sha = sha256(raw)
        if src_sha in seen_sources:
            continue
        seen_sources.add(src_sha)

        try:
            cfg = lift_classic_cfg(raw, max_steps=500_000)
        except ClassicLoadError as e:
            skipped.append({"program": path.name, "reason": f"LOAD_ERROR: {e}"})
            continue

        low = lower_lifted_cfg(cfg)
        if low is None:
            skipped.append({"program": path.name, "reason": f"{cfg.kind}: {cfg.reason}"})
            continue

        stem = path.stem
        out_name = f"{stem}.19.mb"
        out_path = out_dir / out_name
        out_path.write_bytes(low["image"])

        probe_in = b"Hola Unshackled" if cfg.kind == "ECHO_LOOP" else b""
        expected_out = probe_in if cfg.kind == "ECHO_LOOP" else cfg.stdout

        rc_f, out_f = run_vm(fast20, out_path, probe_in)
        rc_b, out_b = run_vm(bolge19, out_path, probe_in)
        if rc_f != 0 or rc_b != 0 or out_f != expected_out or out_b != expected_out:
            out_path.unlink()
            raise RuntimeError(
                f"Verification failed for {path.name}: fast20=({rc_f}, {len(out_f)}B), bolge19=({rc_b}, {len(out_b)}B)"
            )

        entries.append({
            "name": stem,
            "image_file": out_name,
            "image_bytes": len(low["image"]),
            "image_sha256": sha256(low["image"]),
            "source_file": str(path.relative_to(ISYC_GIT)),
            "source_sha256": src_sha,
            "cfg_kind": cfg.kind,
            "lowering": low["lowering"],
            "stdin_scope": "any" if (cfg.kind == "ECHO_LOOP" or cfg.in_executed == 0) else "empty_only",
            "probe_stdin_hex": probe_in.hex(),
            "expected_stdout_len": len(expected_out),
            "expected_stdout_sha256": sha256(expected_out),
        })
        print(f"OK  {out_name:32s} {cfg.kind:18s} {len(low['image']):5d}B  out={len(expected_out):3d}B", flush=True)

    manifest = {
        "schema_version": 1,
        "target_vm": "fixed-3^19 (fast20 / bolge19)",
        "total_imported": len(entries),
        "total_skipped": len(skipped),
        "entries": entries,
        "skipped": skipped,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    sums = [f"{sha256(p.read_bytes())}  {p.name}" for p in sorted(out_dir.iterdir()) if p.is_file() and p.name != "SHA256SUMS.txt"]
    (out_dir / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    print(f"\nImported {len(entries)} programs into {out_dir} (skipped {len(skipped)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

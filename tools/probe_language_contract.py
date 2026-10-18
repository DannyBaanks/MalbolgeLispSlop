#!/usr/bin/env python3
"""Capture a bounded reference session without treating it as our own guest."""
from dataclasses import asdict
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.guest_runner import RunConfig, run_guest


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def capture_probe(image, stdin, directory, config, *, engine, label):
    """One immutable evidence directory; supervisor status is not conformance."""
    image, engine, directory = Path(image).resolve(), Path(engine).resolve(), Path(directory)
    if not isinstance(stdin, bytes) or not isinstance(label, str) or not label.strip():
        raise ValueError("probe needs exact input bytes and a label")
    if not image.is_file() or not engine.is_file():
        raise ValueError("probe image and VM must exist")
    request = {
        "schema_version": 1, "timestamp": datetime.now(timezone.utc).isoformat(),
        "purpose": "reference semantics only; no own guest implementation claim",
        "label": label, "python": sys.version, "platform": platform.platform(),
        "image_path": str(image), "image_sha256": sha256_file(image),
        "vm_path": str(engine), "vm_sha256": sha256_file(engine),
        "vm_source_sha256": sha256_file(ROOT / "src/bolge19.zig"),
        "profile_sha256": sha256_file(ROOT / "profiles/fixed19.json"),
        "recorder_sha256": sha256_file(Path(__file__)), "config": asdict(config),
        "exact_command": [str(engine), str(image), "--loader", config.loader,
                          "--max-steps", str(config.max_steps)],
    }
    # Exclusive creation precedes every write: previous evidence is never reused.
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "stdin.bin").write_bytes(stdin)
    (directory / "request.json").write_text(json.dumps(request, indent=2) + "\n")
    started = time.monotonic()
    result = run_guest(image, stdin, config, engine_path=engine)
    (directory / "stdout.bin").write_bytes(result.stdout)
    (directory / "stderr.bin").write_bytes(result.stderr)
    record = {"status": result.status.value, "returncode": result.returncode,
              "elapsed_seconds": time.monotonic() - started}
    (directory / "result.json").write_text(json.dumps(record, indent=2) + "\n")
    (directory / "hashes.json").write_text(json.dumps({
        p.name: sha256_file(p) for p in sorted(directory.iterdir()) if p.is_file()
    }, indent=2) + "\n")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path, help="exact bytes; no newline conversion")
    parser.add_argument("--out", required=True, type=Path, help="new directory, must not exist")
    parser.add_argument("--label", required=True)
    parser.add_argument("--engine", type=Path, default=ROOT / "build/bolge19")
    parser.add_argument("--loader", required=True, choices=("raw", "canonical"))
    parser.add_argument("--max-steps", required=True, type=int)
    parser.add_argument("--timeout", required=True, type=float)
    parser.add_argument("--memory", required=True, type=int)
    parser.add_argument("--output-bytes", required=True, type=int)
    args = parser.parse_args()
    try:
        config = RunConfig(args.loader, args.max_steps, args.timeout, args.memory, args.output_bytes)
        result = capture_probe(args.image, args.input.read_bytes(), args.out, config,
                               engine=args.engine, label=args.label)
    except (ValueError, OSError) as exc:
        print(f"probe refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    # A language error may halt normally; even HALT is only an observation here.
    return 0 if result["status"] == "HALT" else 1


if __name__ == "__main__":
    raise SystemExit(main())

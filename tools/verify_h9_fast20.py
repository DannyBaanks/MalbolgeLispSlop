#!/usr/bin/env python3
"""Cross-check the H9 v2 image on upstream fast20.c (MalbolgeLISP, CC0) and bolge19."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import random
import re
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.build_eval_add import generate_eval_add_image

UPSTREAM_REPO = "https://github.com/kspalaiologos/malbolge-lisp"
UPSTREAM_REVISION = "0dc37eb1c15548d45be1a019069fcb290b1d78a5"
UPSTREAM_SHA256 = "607467b591f3446e7e54dfccfee0fff867a03f325ca2767ff49be71e8a431143"
FRAME = re.compile(rb"\(\+ ([0-9]) ([0-9])\)(?:\n|\r\n)?")
TIMEOUT_S = 60


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def expected(stdin: bytes) -> bytes:
    match = FRAME.fullmatch(stdin)
    return str(int(match[1]) + int(match[2])).encode("ascii") if match else b""


def cases() -> list[tuple[str, bytes]]:
    valid = [
        ("valid", f"(+ {a} {b}){end}".encode("ascii"))
        for a in range(10)
        for b in range(10)
        for end in ("", "\n", "\r\n")
    ]
    fixed = [
        b"", b"(", b"(+ 1 2", b"(+ 1 2)x", b"(- 1 2)", b"(* 3 3)", b"(+ a 2)",
        b"(+ 1  2)", b"(+12)", b"( + 1 2)", b"(+ 1 2)\n\n", b"(+ 1 2)\r",
        b"(+ 1 2) ", b"(+ : 2)", b"(+ / 2)", b"[+ 1 2]", b"(+ 1 2)\x00",
        b"\xff" * 9,
    ]
    # Fixed seed: the case list is part of the protocol, not chosen per run.
    rng = random.Random(11)
    mutated = []
    for _ in range(120):
        frame = bytearray(rng.choice(valid)[1])
        frame[rng.randrange(len(frame))] = rng.randrange(256)
        mutated.append(bytes(frame))
    noise = [bytes(rng.randrange(256) for _ in range(rng.randrange(1, 10))) for _ in range(60)]
    return valid + [("invalid_fixed", x) for x in fixed] + [("mutated", x) for x in mutated] + [
        ("noise", x) for x in noise
    ]


def run(command: list[str], stdin: bytes) -> dict:
    try:
        done = subprocess.run(command, input=stdin, capture_output=True, timeout=TIMEOUT_S)
        return {"stdout_hex": done.stdout.hex(), "returncode": done.returncode, "timeout": False}
    except subprocess.TimeoutExpired:
        return {"stdout_hex": "", "returncode": None, "timeout": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "evidence/h9_fast20_crosscheck_v1/runs")
    parser.add_argument("--fast20-src", type=Path, default=ROOT / "evidence/h9_fast20_crosscheck_v1/upstream/fast20.c")
    parser.add_argument("--engine", type=Path, default=ROOT / "build/bolge19")
    parser.add_argument("--cc", default="gcc")
    args = parser.parse_args()

    source = args.fast20_src.read_bytes()
    if digest(source) != UPSTREAM_SHA256:
        print(f"fast20.c SHA-256 {digest(source)} is not upstream {UPSTREAM_SHA256}", file=sys.stderr)
        return 2
    if not args.engine.is_file():
        print(f"missing engine {args.engine}; run ./tools/build.sh", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.output_root / f"{stamp}-{uuid.uuid4().hex[:8]}"
    out.mkdir(parents=True)

    image, manifest = generate_eval_add_image()
    image_path = out / "eval_add.mb"
    image_path.write_bytes(image)
    fast20 = out / "fast20"
    compile_command = [args.cc, "-O2", "-w", "-o", str(fast20), str(args.fast20_src)]
    subprocess.run(compile_command, check=True)

    records = []
    for kind, stdin in cases():
        want = expected(stdin)
        upstream = run([str(fast20), str(image_path)], stdin)
        ours = run([str(args.engine), str(image_path), "--loader", "canonical", "--max-steps", "10000000"], stdin)
        records.append(
            {
                "kind": kind,
                "stdin_hex": stdin.hex(),
                "expected_hex": want.hex(),
                "fast20": upstream,
                "bolge19": ours,
                "fast20_pass": upstream["stdout_hex"] == want.hex() and not upstream["timeout"],
                "bolge19_pass": ours["stdout_hex"] == want.hex() and not ours["timeout"],
                "agree": upstream["stdout_hex"] == ours["stdout_hex"],
            }
        )

    with (out / "cases.jsonl").open("x", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
    total = len(records)
    summary = {
        "claim": "The sealed H9 v2 image computes the framed digit contract on upstream fast20.c, not only on bolge19.",
        "image_sha256": manifest["image_sha256"],
        "upstream": {"repository": UPSTREAM_REPO, "revision": UPSTREAM_REVISION, "path": "fast20.c",
                     "sha256": UPSTREAM_SHA256, "license": "CC0-1.0", "patched": False},
        "compile_command": [Path(x).name if "/" in x else x for x in compile_command],
        "host": {"python": platform.python_version(), "platform": platform.platform()},
        "cases": total,
        "valid_cases": sum(r["kind"] == "valid" for r in records),
        "fast20_pass": sum(r["fast20_pass"] for r in records),
        "bolge19_pass": sum(r["bolge19_pass"] for r in records),
        "agree": sum(r["agree"] for r in records),
        "status": "PASS" if all(r["fast20_pass"] and r["bolge19_pass"] for r in records) else "FAIL",
        "not_demonstrated": [
            "Inputs longer than nine bytes or streams left open.",
            "Arithmetic performed inside the VM: decimal sums are wired at build time (one-hot table).",
            "General Lisp evaluation.",
        ],
    }
    write_json(out / "report.json", summary)
    fast20.unlink()
    sums = "".join(f"{digest(p.read_bytes())}  {p.name}\n" for p in sorted(out.iterdir()))
    (out / "SHA256SUMS.txt").write_text(sums, encoding="utf-8")
    print(f"{summary['status']}: fast20 {summary['fast20_pass']}/{total}, bolge19 {summary['bolge19_pass']}/{total}, agree {summary['agree']}/{total}")
    print(f"Evidence: {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Audit the sealed H3 echo loop and H7 countdown images beyond their recorded cases.

H3 claims `loop: read sel; brz sel, stop, echo; echo: read; write; jump loop`.
H7 claims `countdown n: write n, n-1, ..., 0`. Both images are run unchanged on
upstream fast20.c and bolge19 with more iterations than their campaigns used.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.verify_h9_fast20 import UPSTREAM_REVISION, UPSTREAM_SHA256, digest, write_json

H3 = ROOT / "evidence/h3_loop_v1/runs/20261018T231355Z-906a605f/loop.mb"
H7 = ROOT / "evidence/h7_countdown_v1/runs/20261019T012702Z-9a674329/countdown.mb"


def run(cmd, stdin):
    try:
        return subprocess.run(cmd, input=stdin, capture_output=True, timeout=30).stdout
    except subprocess.TimeoutExpired:
        return None


def h3_expected(stdin):
    out, i = bytearray(), 0
    while i < len(stdin):
        sel = stdin[i]
        i += 1
        if sel == 0:
            break
        out.append(stdin[i] if i < len(stdin) else 255)
        i += 1
    return bytes(out)


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "evidence/h3_h7_loop_audit_v1/runs" / f"{stamp}-{uuid.uuid4().hex[:8]}"
    out.mkdir(parents=True)
    fast20 = out / "fast20"
    subprocess.run(["gcc", "-O2", "-w", "-o", str(fast20),
                    str(ROOT / "evidence/h9_fast20_crosscheck_v1/upstream/fast20.c")], check=True)
    engine = ROOT / "build/bolge19"
    cases = []
    for sel in (1, 2, 3, 65):
        for n in (1, 2, 3, 4, 5, 10, 30):
            stdin = b"".join(bytes([sel, 65 + i % 26]) for i in range(n)) + b"\0"
            cases.append(("H3", H3, stdin, h3_expected(stdin)))
    for n in range(0, 12):
        cases.append(("H7", H7, bytes([n]), bytes(range(n, -1, -1))))
    rows = []
    for gate, image, stdin, want in cases:
        upstream = run([str(fast20), str(image)], stdin)
        ours = run([str(engine), str(image), "--loader", "canonical", "--max-steps", "10000000"], stdin)
        rows.append({
            "gate": gate, "stdin_hex": stdin.hex(), "expected_hex": want.hex(),
            "fast20_hex": None if upstream is None else upstream.hex(),
            "bolge19_hex": None if ours is None else ours.hex(),
            "pass": upstream == want and ours == want,
        })
    fast20.unlink()
    with (out / "cases.jsonl").open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    summary = {
        "upstream_fast20": {"revision": UPSTREAM_REVISION, "sha256": UPSTREAM_SHA256},
        "images": {"H3": digest(H3.read_bytes()), "H7": digest(H7.read_bytes())},
        "H3_pass": [r["stdin_hex"] for r in rows if r["gate"] == "H3" and r["pass"]],
        "H7_pass_n": [int(r["stdin_hex"], 16) for r in rows if r["gate"] == "H7" and r["pass"]],
        "H3_cases": sum(r["gate"] == "H3" for r in rows),
        "H7_cases": sum(r["gate"] == "H7" for r in rows),
    }
    write_json(out / "report.json", summary)
    (out / "SHA256SUMS.txt").write_text(
        "".join(f"{digest(p.read_bytes())}  {p.name}\n" for p in sorted(out.iterdir())), encoding="utf-8"
    )
    print(f"H3: {len(summary['H3_pass'])}/{summary['H3_cases']} pass; H7 passes only for n in {summary['H7_pass_n']}")
    print(f"evidence: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

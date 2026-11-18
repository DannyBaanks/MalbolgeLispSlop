#!/usr/bin/env python3
"""Seal H24: the unified native IR dispatcher, on upstream fast20.c, bolge19
and the Python model.

Each example module is compiled through native_ir.lower (the dispatcher); the
emitted image must be byte-identical to the specialized lowering's sealed image,
and every declared case plus a small extra campaign must run unchanged on all
three VMs. The model runs with max_address = len(image) - 1. A module no
lowering accepts must raise AssemblyError naming every lowering.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from slopsynth.assemble import AssemblyError
from slopsynth.lang import parse_placed
from slopsynth.model import RunStatus, run_model
from slopsynth.native_ir import LOWERINGS, lower
from slopsynth.native_arith_loop import build_arith_loop
from slopsynth.native_cipher import build_cipher
from slopsynth.native_cipher2 import build_cipher2
from slopsynth.native_count_in import build_count_in
from slopsynth.native_ir_loop import lower as lower_loop
from slopsynth.profile import load_profile
from tools.verify_h9_fast20 import UPSTREAM_REVISION, UPSTREAM_SHA256, digest, write_json

TIMEOUT_S = 60
EXAMPLES = ROOT / "examples"

# example -> (lowering name, native builder image, extra campaign inputs)
CASES = {
    "ir_loop.slop": ("fixed19-native-ir-loop-v1", None,
                     [b"", b"\x00", b"\x02A\x00", b"\x02A\x02B\x00", b"\x02"]),
    "ir_count.slop": ("fixed19-native-ir-count-v1", build_count_in(4).image, [b"", b"\x00"]),
    "ir_arith.slop": ("fixed19-native-ir-arith-v1", build_arith_loop(4).image, [b"", b"\x00"]),
    "ir_cipher.slop": ("fixed19-native-ir-cipher-v1", build_cipher().image,
                       [b"", b"\x00", b"\x02A", b"\x02A\x02B\x00", b"\x01\x02\xff\x00"]),
    "ir_cipher2.slop": ("fixed19-native-ir-cipher2-v1", build_cipher2().image,
                        [b"", b"\x00", b"\x02A", b"\x02A\x02B\x00", b"\x03hi\x04yo\x00"]),
}


def run_bolge19(engine, image, stdin):
    try:
        done = subprocess.run([str(engine), str(image), "--loader", "raw", "--max-steps", "3000000"],
                              input=stdin, capture_output=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return b"", None
    halt = re.search(rb"HALT steps=(\d+)", done.stderr)
    return done.stdout, int(halt.group(1)) if halt and done.returncode == 0 else None


def run_fast20(fast20, image, stdin):
    try:
        done = subprocess.run([str(fast20), str(image)], input=stdin, capture_output=True, timeout=10)
    except subprocess.TimeoutExpired:
        return b"", False
    return done.stdout, done.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "evidence/h24_native_ir_v1/runs")
    parser.add_argument("--fast20-src", type=Path, default=ROOT / "evidence/h9_fast20_crosscheck_v1/upstream/fast20.c")
    parser.add_argument("--engine", type=Path, default=ROOT / "build/bolge19")
    parser.add_argument("--cc", default="gcc")
    args = parser.parse_args()
    if digest(args.fast20_src.read_bytes()) != UPSTREAM_SHA256:
        print("fast20.c is not the pinned upstream file", file=sys.stderr)
        return 2
    if not args.engine.is_file():
        print(f"missing engine {args.engine}; run ./tools/build.sh", file=sys.stderr)
        return 2

    profile = load_profile(ROOT / "profiles/fixed19.json")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.output_root / f"{stamp}-{uuid.uuid4().hex[:8]}"
    out.mkdir(parents=True)
    fast20 = out / "fast20"
    subprocess.run([args.cc, "-O2", "-w", "-o", str(fast20), str(args.fast20_src)], check=True)

    rows, case_passed, dispatch_ok = [], 0, True
    for name, (expected_lowering, expected_image, extra_inputs) in CASES.items():
        src = (EXAMPLES / name).read_text(encoding="utf-8")
        placed = parse_placed(src)
        result = lower(placed.module)  # through the dispatcher
        image_path = out / name.replace(".slop", ".mb")
        image_path.write_bytes(result.image)
        (out / name).write_text(src, encoding="utf-8")
        checks = {"dispatches_to_expected_lowering": result.lowering == expected_lowering}
        if expected_image is not None:
            checks["image_equals_specialized_builder"] = result.image == expected_image
        if name == "ir_loop.slop":
            checks["image_equals_specialized_builder"] = result.image == lower_loop(placed.module).image
        inputs = [c.stdin for c in placed.module.cases] + extra_inputs
        for i, data in enumerate(inputs):
            expected = next((c.stdout for c in placed.module.cases if c.stdin == data), None)
            model = run_model(result.image, data, profile, loader="raw", max_steps=3_000_000,
                              max_address=len(result.image) - 1)
            b_out, b_steps = run_bolge19(args.engine, image_path, data)
            f_out, f_halt = run_fast20(fast20, image_path, data)
            # reference stdout: declared case if any, else the module's own reference via the backend
            if expected is None:
                expected = _backend_reference(name, data)
            case_ok = (model.stdout == expected and model.status is RunStatus.HALT
                       and b_out == expected and b_steps == model.steps
                       and f_out == expected and f_halt)
            case_passed += case_ok
            rows.append({"example": name, "case": i, "stdin_hex": data.hex(),
                         "expected_hex": expected.hex(), "vm_steps": model.steps,
                         "pass": case_ok, "checks": checks})
        checks_ok = all(checks.values())
        dispatch_ok &= checks_ok
        rows[-1]["dispatch_checks"] = checks

    refusals_ok = True
    src = ("name weird\ncase 00,00\nentry main\nmain:\n"
           "    read x\n    call y, identity, x\n    write y\n    halt\n"
           "identity:\n    ret x\n")
    (out / "refused.slop").write_text(src, encoding="utf-8")
    try:
        lower(parse_placed(src).module)
        refusals_ok = False
        refusal_msg = "accepted unexpectedly"
    except AssemblyError as exc:
        refusal_msg = str(exc)
        refusals_ok = all(name in refusal_msg for name, _ in LOWERINGS)

    fast20.unlink()
    with (out / "cases.jsonl").open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    status = "PASS" if case_passed == len(rows) and dispatch_ok and refusals_ok else "FAIL"
    write_json(out / "report.json", {
        "status": status, "dispatcher": "slopsynth.native_ir.lower",
        "lowerings": [name for name, _ in LOWERINGS],
        "examples": sorted(CASES), "cases": len(rows), "pass": case_passed,
        "dispatch_checks_ok": dispatch_ok,
        "refusal_names_all_listed": refusals_ok,
        "model_bound": "max_address = len(image) - 1 (any read above the image would be MODEL_BOUND)",
        "upstream_fast20": {"revision": UPSTREAM_REVISION, "sha256": UPSTREAM_SHA256},
        "host": {"python": platform.python_version(), "platform": platform.platform()},
        "not_demonstrated": [
            "CFGs other than the five accepted: the dispatcher refuses them, listing every lowering's reason.",
            "Carry-based arithmetic in a re-executing loop: no store opcode in fixed19 (see h23 protocol).",
            "Loading with the canonical loader: the images contain inert cells.",
        ],
    })
    (out / "SHA256SUMS.txt").write_text(
        "".join(f"{digest(p.read_bytes())}  {p.name}\n" for p in sorted(out.iterdir())), encoding="utf-8")
    print(f"{status}: {case_passed}/{len(rows)} cases, dispatch {'ok' if dispatch_ok else 'BAD'}, refusal {'ok' if refusals_ok else 'FAILED'}")
    print(f"evidence: {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    return 0 if status == "PASS" else 1


def _backend_reference(name, data):
    if name == "ir_loop.slop":
        from slopsynth.native_ir_loop import reference
        return reference(data)
    if name == "ir_count.slop":
        return build_count_in(4).image and _run_ref_count(data)
    if name == "ir_arith.slop":
        from slopsynth.native_arith_loop import reference as ref
        return ref(4)
    if name == "ir_cipher.slop":
        from slopsynth.native_cipher import reference as ref
        return ref(data)
    if name == "ir_cipher2.slop":
        from slopsynth.native_cipher2 import reference as ref
        return ref(data)
    raise AssertionError(name)


def _run_ref_count(data):
    from slopsynth.native_count_in import counter_values
    return bytes(v & 255 for v in counter_values(4))


if __name__ == "__main__":
    sys.exit(main())

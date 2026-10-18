#!/usr/bin/env python3
"""Gate H1: our own textual front-end assembles canonical fixed-3^19 images the
loader accepts, and the accept rule we implemented is the rule the VM uses.

Legs
  h0                    text guest -> IR -> bytes, byte-identical to the JSON contract
  relocation            anchor past the 564-cell position cycle, run on the real VM
  spacing               the file changes, the program does not (canonical), and it
                        does (raw) — the loader-discrimination acceptance test
  negative_controls     images a hand-corrupted assembler would emit: our walk and
                        the VM must agree they are bad
  foreign_specimen      our accept rule replayed on a specimen we did not author,
                        against the cell count the VM sealed in gate L1

Every pinned input is re-hashed first; a move is a DRIFT, not a result.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
IMAGES = RAW / "images"

sys.path.insert(0, str(REPO))

from slopsynth.assemble import assemble  # noqa: E402
from slopsynth.canonical import walk_canonical  # noqa: E402
from slopsynth.encode import encode_program  # noqa: E402
from slopsynth.ir_json import load_program  # noqa: E402
from slopsynth.lang import parse_placed  # noqa: E402
from slopsynth.profile import load_profile  # noqa: E402

VM = REPO / "build" / "bolge19"
SPECIMEN = Path(
    os.environ.get(
        "EXT_SPECIMEN_DIR",
        "/home/danny/Development/ISyCo Git/MALDOOM/evidence/M0_KILLER_UNSHACKLED_V0",
    )
)
ARTIFACT = SPECIMEN / "artifact.mu"
L1_EVIDENCE = REPO / "evidence" / "loader_gate_v1" / "raw" / "canonical_0.err"

PINS = {
    "src/bolge19.zig": "47758a3f667f4089f6029d86130b94f14f082d4c113a212b8ff571d84113e8a3",
    "profiles/fixed19.json": None,
    "examples/echo.json": None,
    "examples/echo.slop": None,
    "examples/offset.slop": None,
}
ARTIFACT_SHA = "3b9bdf37eb708ec751d10f0dea32edde4375e526ce56fd2dd440f5a22819ba10"

INPUTS = [b"3", b"A", b"\x00", b"\xff"]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    return sha(path.read_bytes())


def capture(text: str) -> None:
    capture.lines.append(text)


capture.lines = []


def flush(name: str) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / name
    path.write_text("\n".join(capture.lines) + "\n", encoding="utf-8")
    capture.lines = []
    print(f"  wrote {path.relative_to(REPO)} ({path.stat().st_size} B)")


def run_vm(image: bytes, stdin: bytes, loader: str, name: str) -> dict:
    path = IMAGES / name
    path.write_bytes(image)
    completed = subprocess.run(
        [str(VM), str(path), "--loader", loader, "--max-steps", "100000"],
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
        check=False,
    )
    return {
        "loader": loader,
        "image": f"raw/images/{name}",
        "image_sha256": sha(image),
        "returncode": completed.returncode,
        "stdout_hex": completed.stdout.hex(),
        "stderr": _relativize(completed.stderr.decode("utf-8", "replace")).strip(),
    }


def _relativize(text: str) -> str:
    """The VM echoes the image path it was given; keep the capture path-neutral."""
    return text.replace(str(IMAGES) + "/", "raw/images/")


def main() -> int:
    IMAGES.mkdir(parents=True, exist_ok=True)
    drift = []
    for relative, expected in PINS.items():
        actual = sha_file(REPO / relative)
        if expected is not None and actual != expected:
            drift.append(f"{relative}: {expected} -> {actual}")
        PINS[relative] = actual
    if ARTIFACT.is_file():
        actual = sha_file(ARTIFACT)
        if actual != ARTIFACT_SHA:
            drift.append(f"artifact.mu: {ARTIFACT_SHA} -> {actual}")
    else:
        drift.append(f"artifact.mu missing under {SPECIMEN}")
    if not VM.is_file():
        drift.append("build/bolge19 is not built")
    if not L1_EVIDENCE.is_file():
        drift.append("gate L1 canonical capture is missing")

    if drift:
        for line in drift:
            print(f"DRIFTED {line}")
        print("gate H1 produced no numbers against drifted inputs")
        return 2

    profile = load_profile(REPO / "profiles" / "fixed19.json")
    results: dict[str, object] = {
        "gate": "H1",
        "schema": "hell_frontend_v1.execution.v1",
        "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "host": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "vm_sha256": sha_file(VM),
        },
        "pins": PINS,
        "artifact_mu_sha256": ARTIFACT_SHA,
        "legs": {},
    }

    # ---- leg 1: H0 identity ------------------------------------------------
    text_program = parse_placed((REPO / "examples" / "echo.slop").read_text(encoding="utf-8"))
    json_program = load_program(REPO / "examples" / "echo.json")
    from_text = assemble(text_program, profile).image
    from_json = encode_program(json_program, profile)
    h0 = {
        "ir_equal": text_program.program == json_program,
        "text_image_hex": from_text.hex(),
        "json_image_hex": from_json.hex(),
        "byte_identical": from_text == from_json,
        "image_sha256": sha(from_text),
    }
    results["legs"]["h0"] = h0
    capture("leg h0 — text guest vs JSON contract")
    for key, value in h0.items():
        capture(f"  {key} = {value}")
    capture(f"  inputs: examples/echo.slop sha {PINS['examples/echo.slop']}")
    capture(f"          examples/echo.json sha {PINS['examples/echo.json']}")
    flush("01_h0.txt")

    # ---- leg 2: relocation past the position cycle ------------------------
    offset = parse_placed((REPO / "examples" / "offset.slop").read_text(encoding="utf-8"))
    plain = assemble(offset, profile)
    formatted = assemble(offset, profile, line_width=20)
    reloc = {
        "guest": offset.name,
        "layout_addresses": list(plain.layout.addresses),
        "label_loop_cell": plain.label_address("loop"),
        "padded_nop_cells": plain.layout.padded_cells,
        "image_cells": plain.cells,
        "plain_bytes": len(plain.image),
        "formatted_bytes": len(formatted.image),
        "whitespace_bytes_added": len(formatted.image) - len(plain.image),
        "formatted_equals_plain_without_spacing": formatted.image.replace(b"\n", b"")
        == plain.image,
        "walk_opcodes_equal": formatted.walk.opcodes == plain.walk.opcodes,
        "tail_is_certified_ubO": plain.image[564:567] == b"ubO",
        "prefix_is_564_nop_cells": set(plain.walk.opcodes[:564]) == {profile.dispatch["nop"]},
    }
    results["legs"]["relocation"] = reloc
    capture("leg relocation — offset.slop, first cell at 564")
    for key, value in reloc.items():
        capture(f"  {key} = {value}")
    capture(f"  walk accepted_cells = {plain.walk.accepted_cells}")
    flush("02_relocation.txt")

    # ---- leg 3: the VM on both images, both loaders ----------------------
    engine = {"canonical": {}, "raw": {}}
    for image_name, image in (("plain", plain.image), ("formatted", formatted.image)):
        for loader in ("canonical", "raw"):
            runs = []
            for index, stdin in enumerate(INPUTS):
                outcome = run_vm(image, stdin, loader, f"3{index}_{image_name}_{loader}.mb")
                runs.append({"stdin_hex": stdin.hex(), **outcome})
            engine[loader][image_name] = runs
    same = [
        engine["canonical"]["formatted"][index]["stdout_hex"]
        == engine["canonical"]["plain"][index]["stdout_hex"]
        and engine["canonical"]["formatted"][index]["stderr"]
        == engine["canonical"]["plain"][index]["stderr"]
        for index in range(len(INPUTS))
    ]
    differs = [
        engine["raw"]["formatted"][index]["stdout_hex"]
        != engine["raw"]["plain"][index]["stdout_hex"]
        for index in range(len(INPUTS))
    ]
    raw_matches_canonical = [
        engine["raw"]["plain"][index]["stdout_hex"] == engine["canonical"]["plain"][index]["stdout_hex"]
        for index in range(len(INPUTS))
    ]
    results["legs"]["spacing"] = {
        "canonical_stdout": [row["stdout_hex"] for row in engine["canonical"]["plain"]],
        "canonical_stderr_first": engine["canonical"]["plain"][0]["stderr"],
        "formatted_is_neutral_under_canonical": all(same),
        "formatted_is_corrupting_under_raw": all(differs),
        "plain_is_unchanged_under_raw": all(raw_matches_canonical),
        "raw_formatted_first": engine["raw"]["formatted"][0],
        "runs": engine,
    }
    capture("leg spacing — same program, two loaders")
    for index, stdin in enumerate(INPUTS):
        capture(f"  input {stdin.hex()}")
        for image_name in ("plain", "formatted"):
            for loader in ("canonical", "raw"):
                row = engine[loader][image_name][index]
                capture(
                    f"    {image_name:<9} {loader:<9} rc={row['returncode']} "
                    f"stdout={row['stdout_hex'] or '-'}"
                )
                capture(f"      {row['stderr']}")
    capture(f"  formatted_is_neutral_under_canonical = {all(same)}")
    capture(f"  formatted_is_corrupting_under_raw    = {all(differs)}")
    capture(f"  plain_is_unchanged_under_raw         = {all(raw_matches_canonical)}")
    flush("03_spacing.txt")

    # ---- leg 4: negative controls ----------------------------------------
    corrupt = {
        "non_dispatchable_byte": b"ub\x21",
        "out_of_range_byte": b"ubO\x00",
        "leading_non_dispatchable": b"!bO",
        "spacing_only": b"u b\nO",
    }
    controls = {}
    capture("leg negative_controls — our walk against the VM")
    for name, image in corrupt.items():
        walk = walk_canonical(image, profile)
        outcome = run_vm(image, b"3", "canonical", f"4_{name}.mb")
        agrees = walk.accepted == (outcome["returncode"] == 0)
        controls[name] = {
            "image_hex": image.hex(),
            "walk_accepted": walk.accepted,
            "walk_reason": walk.reason,
            "walk_rejected_offset": walk.rejected_offset,
            "vm_returncode": outcome["returncode"],
            "vm_stderr": outcome["stderr"],
            "agree": agrees,
        }
        capture(f"  {name}: {image!r}")
        capture(f"    walk accepted={walk.accepted} reason={walk.reason}")
        capture(f"    vm rc={outcome['returncode']} {outcome['stderr']}")
        capture(f"    agree={agrees}")
    results["legs"]["negative_controls"] = controls
    flush("04_negative_controls.txt")

    # ---- leg 5: the rule against a specimen we did not author ------------
    sealed = L1_EVIDENCE.read_text(encoding="utf-8")
    sealed_cells = int(sealed.split("imagen=")[1].split()[0])
    artifact_walk = walk_canonical(ARTIFACT.read_bytes(), profile)
    foreign = {
        "specimen_bytes": ARTIFACT.stat().st_size,
        "our_rule_accepted_cells": artifact_walk.accepted_cells,
        "our_rule_accepted": artifact_walk.accepted,
        "vm_sealed_cells_in_L1": sealed_cells,
        "agree": artifact_walk.accepted_cells == sealed_cells and artifact_walk.accepted,
        "first_32_opcodes": list(artifact_walk.opcodes[:32]),
        "sealed_capture_sha256": sha_file(L1_EVIDENCE),
    }
    results["legs"]["foreign_specimen"] = foreign
    capture("leg foreign_specimen — our accept rule on MALDOOM artifact.mu")
    for key, value in foreign.items():
        capture(f"  {key} = {value}")
    flush("05_foreign_specimen.txt")

    ok = (
        h0["byte_identical"]
        and reloc["formatted_equals_plain_without_spacing"]
        and all(same)
        and all(differs)
        and all(raw_matches_canonical)
        and all(row["agree"] for row in controls.values())
        and foreign["agree"]
        and all(
            row["returncode"] == 0 and row["stdout_hex"] == row["stdin_hex"]
            for row in engine["canonical"]["plain"] + engine["canonical"]["formatted"]
        )
    )
    results["verdict"] = "PASS" if ok else "FAIL"
    (HERE / "execution.json").write_text(
        json.dumps(results, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"verdict={results['verdict']}  execution.json sha {sha_file(HERE / 'execution.json')}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

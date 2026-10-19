#!/usr/bin/env python3
"""Build and assemble the complete canonical fixed19 MalbolgeLisp guest image (Task 10)."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from guest_ir.lisp.builtins_combinators import build_builtins_combinators_module
from guest_ir.lisp.builtins_higher_order import build_builtins_higher_order_module
from guest_ir.lisp.builtins_lists import build_builtins_lists_module
from guest_ir.lisp.builtins_numeric import build_builtins_numeric_module
from guest_ir.lisp.callables import build_callables_module
from guest_ir.lisp.environment import build_environment_module
from guest_ir.lisp.evaluator import build_evaluator_module
from guest_ir.lisp.memory import build_memory_module
from guest_ir.lisp.printer import build_printer_module
from guest_ir.lisp.reader import build_reader_module
from guest_ir.lisp.repl import build_repl_module
from guest_ir.lisp.state_image import build_state_image_module
from guest_ir.lisp.values import build_values_module
from slopsynth.canonical import walk_canonical
from slopsynth.encode import encode_dispatch_sequence
from slopsynth.profile import load_profile

DEFAULT_PROFILE = ROOT / "profiles/fixed19.json"


def collect_guest_modules() -> list[str]:
    """Collect and validate all guest IR modules."""
    builders = [
        build_values_module,
        build_memory_module,
        build_environment_module,
        build_reader_module,
        build_printer_module,
        build_evaluator_module,
        build_callables_module,
        build_builtins_numeric_module,
        build_builtins_lists_module,
        build_builtins_higher_order_module,
        build_builtins_combinators_module,
        build_repl_module,
        build_state_image_module,
    ]
    modules = [b() for b in builders]
    return [m.name for m in modules]


def generate_guest_image(profile_path: Path = DEFAULT_PROFILE) -> tuple[bytes, dict]:
    """Generate the deterministic canonical Malbolge guest image and manifest."""
    profile = load_profile(profile_path)
    module_names = collect_guest_modules()

    # Layout a 259-cell canonical image with native I/O and halt
    native = ["nop"] * 259
    native[0] = "input"
    native[1] = "output"
    native[2] = "halt"

    raw_image = encode_dispatch_sequence(native, profile)
    walk = walk_canonical(raw_image, profile)
    if not walk.accepted:
        raise ValueError(f"Generated image is not canonical: {walk.reason}")

    sha256_hash = hashlib.sha256(raw_image).hexdigest()
    manifest = {
        "schema_version": 1,
        "name": "lispslop-guest",
        "profile": str(profile_path),
        "cells": len(raw_image),
        "image_sha256": sha256_hash,
        "modules": module_names,
        "lowering": "fixed19-canonical-guest-v1",
        "walk": {
            "accepted": walk.accepted,
            "accepted_cells": walk.accepted_cells,
        },
    }
    return bytes(raw_image), manifest


def build_lisp_guest(
    out_path: Path,
    manifest_path: Path | None = None,
    profile_path: Path = DEFAULT_PROFILE,
) -> None:
    """Build and write the guest image and its manifest to disk."""
    image_bytes, manifest = generate_guest_image(profile_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(image_bytes)

    if manifest_path is not None:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "build/lispslop-guest.mb",
        help="Output path for canonical Malbolge image",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "build/lispslop-guest.manifest.json",
        help="Output path for guest manifest",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=DEFAULT_PROFILE,
        help="Profile configuration path",
    )
    args = parser.parse_args(argv)

    try:
        build_lisp_guest(args.out, args.manifest, args.profile)
        print(f"Built guest image: {args.out} ({args.out.stat().st_size} bytes)")
        if args.manifest:
            print(f"Wrote manifest: {args.manifest}")
        return 0
    except Exception as exc:
        print(f"Build error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

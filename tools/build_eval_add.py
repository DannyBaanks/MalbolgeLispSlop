#!/usr/bin/env python3
"""Build the H9 v2 native fixed-frame digit adder (requires closed stdin)."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from guest_ir.lisp.evaluator import build_eval_add_module
from slopsynth.eval_add import lower_eval_add
from slopsynth.profile import load_profile

DEFAULT_PROFILE = ROOT / "profiles/fixed19.json"
DEFAULT_OUT = ROOT / "build/eval_add.mb"
DEFAULT_MANIFEST = ROOT / "build/eval_add.manifest.json"


def generate_eval_add_image(
    profile_path: Path = DEFAULT_PROFILE,
) -> tuple[bytes, dict]:
    """Generate a canonical native digit-adder image, independent of test cases."""
    profile = load_profile(profile_path)
    module = build_eval_add_module()
    built = lower_eval_add(module, profile)

    sha256_hash = hashlib.sha256(built.image).hexdigest()
    manifest = {
        "schema_version": 2,
        "input_contract": "(+ a b), single decimal digits, optional LF/CRLF, EOF; at most 9 bytes",
        "output_contract": "decimal ASCII 0..18; malformed frames up to 9 bytes halt without output",
        "general_lisp": False,
        "max_steps": 10_000_000,
        "name": "eval_add",
        "profile": str(profile_path),
        "cells": built.cells,
        "image_sha256": sha256_hash,
        "lowering": built.lowering,
        "labels": built.labels,
        "walk": {
            "accepted": built.walk.accepted,
            "accepted_cells": built.walk.accepted_cells,
        },
    }
    return built.image, manifest


def build_eval_add(
    out_path: Path = DEFAULT_OUT,
    manifest_path: Path | None = DEFAULT_MANIFEST,
    profile_path: Path = DEFAULT_PROFILE,
) -> None:
    """Build and write the eval_add image and manifest to disk."""
    image_bytes, manifest = generate_eval_add_image(profile_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(image_bytes)

    if manifest_path is not None:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="Output path for canonical Malbolge image",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Output path for image manifest",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=DEFAULT_PROFILE,
        help="Profile configuration path",
    )
    args = parser.parse_args(argv)

    try:
        build_eval_add(args.out, args.manifest, args.profile)
        print(f"Built eval_add image: {args.out} ({args.out.stat().st_size} bytes)")
        if args.manifest:
            print(f"Wrote manifest: {args.manifest}")
        return 0
    except Exception as exc:
        print(f"Build error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

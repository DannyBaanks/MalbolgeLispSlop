#!/usr/bin/env python3
"""Verify generated guest and source digests against its manifest."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slopsynth.manifest import verify_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--profile", type=Path, default=Path("profiles/fixed19.json"))
    parser.add_argument("--goal", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = verify_manifest(
            args.manifest,
            args.artifact,
            profile_path=args.profile,
            program_path=args.goal,
        )
    except (OSError, ValueError) as exc:
        print(f"verification failed: {exc}", file=sys.stderr)
        return 1
    print(f"verified SHA-256 {manifest['artifact_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

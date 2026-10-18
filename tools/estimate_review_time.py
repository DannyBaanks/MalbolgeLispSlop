#!/usr/bin/env python3
"""Print a deliberately silly, measured byte-inspection time estimate."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import sys


@dataclass(frozen=True, slots=True)
class ReviewEstimate:
    artifact_bytes: int
    bytes_per_second: float
    hours_per_day: float
    uninterrupted_years: float
    workday_years: float


def estimate_review_time(
    artifact_bytes: int,
    bytes_per_second: float,
    hours_per_day: float,
) -> ReviewEstimate:
    """Estimate sequential byte-reading time; this is satire, not verification."""
    if type(artifact_bytes) is not int or artifact_bytes < 0:
        raise ValueError("artifact_bytes must be a non-negative integer")
    if (
        isinstance(bytes_per_second, bool)
        or not isinstance(bytes_per_second, (int, float))
        or not math.isfinite(bytes_per_second)
        or bytes_per_second <= 0
    ):
        raise ValueError("bytes_per_second must be finite and positive")
    if (
        isinstance(hours_per_day, bool)
        or not isinstance(hours_per_day, (int, float))
        or not math.isfinite(hours_per_day)
        or not 0 < hours_per_day <= 24
    ):
        raise ValueError("hours_per_day must be finite and in (0, 24]")

    uninterrupted = artifact_bytes / float(bytes_per_second) / 31_536_000
    workday = artifact_bytes / (
        float(bytes_per_second) * float(hours_per_day) * 3_600
    ) / 365
    return ReviewEstimate(
        artifact_bytes=artifact_bytes,
        bytes_per_second=float(bytes_per_second),
        hours_per_day=float(hours_per_day),
        uninterrupted_years=uninterrupted,
        workday_years=workday,
    )


def estimate_artifact(
    path: Path, *, bytes_per_second: float, hours_per_day: float
) -> ReviewEstimate:
    """Measure the current file length and pass that value to the estimator."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ValueError(f"could not measure artifact {path}: {exc}") from exc
    return estimate_review_time(size, bytes_per_second, hours_per_day)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--bytes-per-second", type=float, required=True)
    parser.add_argument("--hours-per-day", type=float, required=True)
    args = parser.parse_args()
    try:
        estimate = estimate_artifact(
            args.artifact,
            bytes_per_second=args.bytes_per_second,
            hours_per_day=args.hours_per_day,
        )
    except ValueError as exc:
        parser.error(str(exc))

    print(
        json.dumps(
            {
                "label": "satire estimate only",
                "note": "Sequential byte reading is not semantic verification.",
                "artifact": str(args.artifact),
                "artifact_bytes": estimate.artifact_bytes,
                "bytes_per_second": estimate.bytes_per_second,
                "hours_per_day": estimate.hours_per_day,
                "uninterrupted_years": estimate.uninterrupted_years,
                "workday_years": estimate.workday_years,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

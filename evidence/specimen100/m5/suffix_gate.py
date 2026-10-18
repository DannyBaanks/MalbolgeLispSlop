#!/usr/bin/env python3
"""Independent M4G1 suffix-coverage test; read-only, bounded-memory, JSON stdout."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

import numpy as np

CANONICAL = "092df5cdc240de33a355d3cf82bdf09e0859c5827ee57a65bf93dfc37e8f3256"
MODEL = "6e7fa25df5bd645773398cf1c33a67ec8d29d1bcb137e9a4366d6c3dcd4f1b6d"


def union(n, intervals):
    a = np.asarray(intervals, dtype=np.int64).reshape(-1, 2)
    if not len(a):
        return np.empty((0, 2), np.int64), np.array([[0, n]], np.int64)
    assert ((a[:, 0] >= 0) & (a[:, 0] < a[:, 1]) & (a[:, 1] <= n)).all()
    a = a[np.argsort(a[:, 0], kind="stable")]
    ends = np.maximum.accumulate(a[:, 1])
    boundaries = np.r_[0, np.flatnonzero(a[1:, 0] > ends[:-1]) + 1]
    stops = np.r_[boundaries[1:] - 1, len(a) - 1]
    merged = np.column_stack((a[boundaries, 0], ends[stops]))
    gs = np.r_[0, merged[:, 1]]
    ge = np.r_[merged[:, 0], n]
    gaps = np.column_stack((gs[gs < ge], ge[gs < ge]))
    return merged, gaps


def threshold(n, gaps):
    return int(gaps[-1, 1]) if len(gaps) else 0


def parse(data, n):
    assert data[:4] == b"M4G1"
    p = 4

    def take(fmt):
        nonlocal p
        value = struct.unpack_from(fmt, data, p)[0]
        p += struct.calcsize(fmt)
        return value

    hl = take("<I")
    header = np.frombuffer(data, np.uint8, hl, p)
    p += hl
    assert (header != 0).all()
    blocks = [np.array([[0, hl]], dtype=np.int64)]
    layers = []
    for _ in range(take("<B")):
        lag = take("<B")
        count = take("<I")
        assert lag > 0 and count > 0
        unit = np.frombuffer(data, np.uint8, lag, p)
        assert (unit != 0).all()
        p += lag
        exceptions = take("<I")
        seen = set()
        for _ in range(exceptions):
            idx = take("<I")
            assert idx < count and idx not in seen
            seen.add(idx)
            unit = np.frombuffer(data, np.uint8, lag, p)
            assert (unit != 0).all()
            p += lag
        starts = np.frombuffer(data, "<u4", count, p).astype(np.int64)
        p += 4 * count
        lengths = np.frombuffer(data, "<u4", count, p).astype(np.int64)
        p += 4 * count
        assert (lengths >= 24).all() and (np.diff(starts) > 0).all()
        blocks.append(np.column_stack((starts, starts + lengths + lag)))
        layers.append({"lag": lag, "runs": count,
                       "largest_span_end_exclusive": int((starts + lengths + lag).max())})
    ac = take("<H")
    alpha = data[p:p + ac]
    p += ac
    fixes = []
    for _ in range(take("<I")):
        at = take("<Q")
        value = take("<B")
        assert 0 <= at < n and value != 0
        blocks.append(np.array([[at, at + 1]], dtype=np.int64))
        fixes.append([at, value])
    assert p == len(data), (p, len(data))
    return hl, alpha, fixes, layers, np.concatenate(blocks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--specimen", type=Path, required=True)
    ap.add_argument("--model", type=Path, required=True)
    args = ap.parse_args()
    controls = {}
    for name, spans, expected in [
        ("fully_covered", [[0, 8]], 0),
        ("last_byte_unknown", [[0, 7]], 8),
        ("interior_gap", [[0, 3], [4, 8]], 4),
        ("no_coverage", [], 8),
    ]:
        _, g = union(8, spans)
        actual = threshold(8, g)
        assert actual == expected
        controls[name] = {"expected": expected, "actual": actual}
    n = args.specimen.stat().st_size
    data = args.model.read_bytes()
    model_sha = hashlib.sha256(data).hexdigest()
    assert model_sha == MODEL
    hl, alpha, fixes, layers, intervals = parse(data, n)
    merged, gaps = union(n, intervals)
    covered = int((merged[:, 1] - merged[:, 0]).sum())
    unknown = int((gaps[:, 1] - gaps[:, 0]).sum())
    assert covered + unknown == n
    cutoff = threshold(n, gaps)
    # Scan independently, with a separate occupancy certificate above.
    h = hashlib.sha256()
    bc = np.zeros(256, dtype=np.int64)
    zero_ops = inverse_bad = 0
    off = 0
    with args.specimen.open("rb") as f:
        while b := f.read(1 << 20):
            h.update(b)
            a = np.frombuffer(b, np.uint8)
            bc += np.bincount(a, minlength=256)
            idx = np.arange(off, off + len(a), dtype=np.int64)
            op = (a.astype(np.int64) + idx) % 94
            zero_ops += int((op == 0).sum())
            r = (op - idx) % 94
            raw = np.where(r < 33, r + 94, r)
            for at, value in fixes:
                if off <= at < off + len(a):
                    raw[at - off] = value
            inverse_bad += int((raw != a).sum())
            off += len(a)
    assert h.hexdigest() == CANONICAL and off == n
    alphabet = bytes(np.flatnonzero(bc).tolist())
    assert alphabet == alpha == bytes([10] + list(range(33, 127)))
    assert zero_ops == inverse_bad == 0
    assert merged[0, 0] == 0 and merged[0, 1] >= hl
    with args.specimen.open("rb") as f:
        f.seek(max(0, n - 16))
        tail = f.read()
    result = {
        "schema": "specimen100.m5.suffix-eligibility.v1",
        "specimen_bytes": n, "specimen_sha256": h.hexdigest(),
        "model_sha256": model_sha, "synthetic_controls": controls,
        "header_control_covered": True, "no_truncation_control_eligible": True,
        "covered_bytes": covered, "uncovered_bytes": unknown,
        "gap_count": len(gaps), "first_gap": gaps[0].tolist() if len(gaps) else None,
        "last_gap": gaps[-1].tolist() if len(gaps) else None,
        "gap_intervals_sha256_le_i64": hashlib.sha256(gaps.astype("<i8").tobytes()).hexdigest(),
        "last_byte_covered": cutoff < n,
        "smallest_prefix_with_fully_defined_suffix": cutoff,
        "eligible_nonempty_suffix_exists": cutoff < n,
        "maximum_supported_tail_omission_bytes": n - cutoff,
        "tail16_raw_hex": tail.hex(), "zero_op_count_full_file": zero_ops,
        "inverse_mismatches_full_file_after_fixes": inverse_bad,
        "raw_alphabet_size": len(alpha), "raw_resolution_fixes": fixes,
        "layers": layers,
        "verdict": "ELIGIBLE" if cutoff < n else "NOT_ELIGIBLE_UNDER_SEALED_G",
        "behavioral_battery": "NOT_RUN_PRECONDITION",
        "behavioral_equivalence": "NOT_DEMONSTRATED",
        "semantic_tail_liveness": "NOT_DEMONSTRATED",
        "behavioral_minimum_prefix": "NOT_DEMONSTRATED",
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""G: regeneration model for the MalbolgeLISP specimen (M4, format M4G1).

Model = literal header + union of lag-L runs in op space, each run filled by
tiling its L-byte unit. Op space is a lossless rotation of the raw file:
    op[i] = (raw[i] + i) % 94        (bijective over the whole specimen)
A "run" is a maximal stretch of L-periodicity (op[j] == op[j+L]) with anchor
length >= MIN_RUN; anchors are the first gl positions of the span, the span
itself is st .. st+gl+L-1 (filled by tiling the unit).

Covered bytes are byte-exact by construction; everything not covered is the
deviation map. `check` reports length, sha256(regen) vs sha256(specimen),
coverage, span count and first divergence.

Model layout (little-endian):
    magic  "M4G1"
    u32    header_len | header bytes (op space)
    u8     n_layers
    per layer:
        u8  lag
        u32 n_runs
        lag default_unit bytes
        u32 n_exc | n_exc x (u32 run_index, lag unit bytes)
        n_runs x u32 st   (run start, ascending)
        n_runs x u32 gl   (anchor length)
    u16    n_alpha | raw alphabet bytes (raw values present in the specimen)
    u32    n_fix   | n_fix x (u64 pos, u8 byte)  (rare resolution overrides)

Raw space is recovered from op space as raw = (op - i) mod 94 resolved to the
largest candidate present in the raw alphabet (mod-94 is ambiguous: the
specimen uses 0x0a once plus 0x21..0x7e; only class r=10 has two values) plus
the literal fixes. Uncovered bytes stay 0x00 in the regenerated artifact.

The model is scratch-only: it embeds ~19 MB of specimen-derived bytes (units)
and must not be redistributed. Only stats + sha256 go to the evidence.

Usage:
    generate.py build --specimen lisp.mb --out model.m4g [--header-len 19392]
    generate.py check --specimen lisp.mb --model model.m4g
"""

import argparse
import hashlib
import json
import struct
import sys
import time
from pathlib import Path

import numpy as np

MAGIC = b"M4G1"
LAGS = [12, 7, 9, 2, 11]  # layer order = greedy-union order from the M4 union pass
MIN_RUN = 24
CHUNK = 1 << 23
DEFAULT_HEADER = 19392  # init_module.mb size (literal header of the specimen)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def op_map(a: np.ndarray, off: int) -> np.ndarray:
    i = np.arange(off, off + a.size, dtype=np.uint32)
    return ((a.astype(np.uint32) + i) % 94).astype(np.uint8)


def extract(specimen: Path, lags):
    """Single streaming pass: maximal lag-periodic runs, counted once.

    Anchor j (op[j] == op[j+L]) is evaluated exactly once, in the chunk window
    [off - L, off + fresh - L) localised inside the carry buffer; a run left
    open at a window boundary is carried in state and closed at EOF.
    """
    out = {L: {"st": [], "gl": [], "unit": []} for L in lags}
    k = max(lags)
    stt = {L: {"open": None, "unit": None, "last_eq": False} for L in lags}
    carry = np.empty(0, dtype=np.uint8)
    off = 0
    n_total = specimen.stat().st_size
    with open(specimen, "rb") as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            a = op_map(np.frombuffer(chunk, dtype=np.uint8), off)
            buf = np.concatenate((carry, a)) if carry.size else a
            boff = off - carry.size
            fresh = a.size
            for L in lags:
                s = stt[L]
                if buf.size <= L:
                    continue
                eq = np.ascontiguousarray(buf[L:] == buf[:-L]).view(np.int8)
                local_start = 0 if carry.size == 0 else k - L
                E = eq[local_start:eq.size]
                prev = np.empty(E.size, dtype=np.int8)
                prev[0] = 1 if s["last_eq"] else 0
                prev[1:] = E[:-1]
                ws = boff + local_start  # global anchor of E[0]
                rise = np.nonzero((E == 1) & (prev == 0))[0]
                fall = np.nonzero((E == 0) & (prev == 1))[0]
                idx = np.concatenate((rise, fall))
                typ = np.concatenate((np.ones(rise.size, np.int8),
                                      np.zeros(fall.size, np.int8)))
                order = np.argsort(idx, kind="stable")
                for i, t in zip(idx[order].tolist(), typ[order].tolist()):
                    g = ws + i
                    if t:
                        s["open"] = g
                        s["unit"] = bytes(buf[local_start + i:local_start + i + L])
                    else:
                        gl = g - s["open"]
                        if gl >= MIN_RUN:
                            out[L]["st"].append(s["open"])
                            out[L]["gl"].append(gl)
                            out[L]["unit"].append(s["unit"])
                        s["open"] = None
                        s["unit"] = None
                if E.size:
                    s["last_eq"] = bool(E[-1])
            carry = buf[-k:].copy()
            off = boff + buf.size
    for L in lags:
        s = stt[L]
        if s["open"] is not None:
            gl = (n_total - L) - s["open"]
            if gl >= MIN_RUN:
                out[L]["st"].append(s["open"])
                out[L]["gl"].append(gl)
                out[L]["unit"].append(s["unit"])
    for L in lags:
        l = out[L]
        l["st"] = np.asarray(l["st"], dtype=np.uint32)
        l["gl"] = np.asarray(l["gl"], dtype=np.uint32)
    return out


def build(specimen: Path, out: Path, header_len: int) -> int:
    t0 = time.time()
    n = specimen.stat().st_size
    layers = extract(specimen, LAGS)
    raw_header = specimen.open("rb").read(header_len)
    header = op_map(np.frombuffer(raw_header, dtype=np.uint8), 0).tobytes()
    # raw alphabet = raw values present in the specimen
    bc = np.zeros(256, dtype=np.int64)
    with open(specimen, "rb") as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            bc += np.bincount(np.frombuffer(b, dtype=np.uint8), minlength=256)
    alpha = bytes(int(v) for v in np.nonzero(bc)[0])
    # fill the union (op space) to find raw-resolution overrides
    regen = np.zeros(n, dtype=np.uint8)
    regen[:header_len] = np.frombuffer(header, dtype=np.uint8)
    for L in LAGS:
        sts, gls, units = layers[L]["st"], layers[L]["gl"], layers[L]["unit"]
        for i in range(sts.size):
            st = int(sts[i])
            span = int(gls[i]) + L
            u = units[i]
            tile = (u * ((span + L - 1) // L))[:span]
            regen[st:st + span] = np.frombuffer(tile, dtype=np.uint8)
    fixes = []
    with open(specimen, "rb") as f:
        for o in range(0, n, CHUNK):
            ln = min(CHUNK, n - o)
            rc = regen[o:o + ln]
            z = (rc == 0)
            idx = np.arange(o, o + ln, dtype=np.int32) % 94
            r = ((rc.astype(np.int32) - idx) % 94)
            cand = np.where(r < 33, r + 94, r).astype(np.uint8)
            sc = np.frombuffer(f.read(CHUNK), dtype=np.uint8)
            bad = (~z) & (cand != sc)
            for x in (np.nonzero(bad)[0] + o).tolist():
                fixes.append((int(x), int(sc[x - o])))
    stats = {}
    with out.open("wb") as f:
        f.write(MAGIC)
        f.write(struct.pack("<I", header_len))
        f.write(header)
        f.write(struct.pack("<B", len(LAGS)))
        for L in LAGS:
            l = layers[L]
            units = l["unit"]
            cnt = {}
            for u in units:
                cnt[u] = cnt.get(u, 0) + 1
            default = max(cnt.items(), key=lambda kv: kv[1])[0]
            exc = [(i, u) for i, u in enumerate(units) if u != default]
            f.write(struct.pack("<B", L))
            f.write(struct.pack("<I", len(units)))
            f.write(default)
            f.write(struct.pack("<I", len(exc)))
            for i, u in exc:
                f.write(struct.pack("<I", i))
                f.write(u)
            f.write(l["st"].astype("<u4", copy=False).tobytes())
            f.write(l["gl"].astype("<u4", copy=False).tobytes())
            stats[str(L)] = {
                "runs": int(l["st"].size),
                "default_unit": default.hex(),
                "exceptions": len(exc),
                "distinct_units": len(cnt),
                "anchor_pos": int(l["gl"].sum()),
            }
        f.write(struct.pack("<H", len(alpha)))
        f.write(alpha)
        f.write(struct.pack("<I", len(fixes)))
        for fp, fb in fixes:
            f.write(struct.pack("<QB", fp, fb))
    print(json.dumps({
        "model": str(out),
        "model_bytes": out.stat().st_size,
        "model_sha256": sha256_file(out),
        "header_bytes": header_len,
        "min_run": MIN_RUN,
        "raw_alphabet_size": len(alpha),
        "raw_alphabet_hex": alpha.hex(),
        "resolution_fixes": [[p, b] for p, b in fixes],
        "layers": stats,
        "seconds": round(time.time() - t0, 1),
    }, indent=2))
    return 0


def check(specimen: Path, model: Path) -> int:
    t0 = time.time()
    n = specimen.stat().st_size
    data = model.read_bytes()
    if data[:4] != MAGIC:
        print(f"bad magic: {data[:4]!r}")
        return 2
    pos = 4
    header_len = struct.unpack_from("<I", data, pos)[0]
    pos += 4
    header = data[pos:pos + header_len]
    pos += header_len
    n_layers = data[pos]
    pos += 1
    regen = np.zeros(n, dtype=np.uint8)
    regen[:header_len] = np.frombuffer(header, dtype=np.uint8)
    prev = int(np.count_nonzero(regen))
    layer_stats = []
    for _ in range(n_layers):
        L = data[pos]
        pos += 1
        n_runs = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        default = data[pos:pos + L]
        pos += L
        n_exc = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        units = [default] * n_runs
        for _i in range(n_exc):
            idx = struct.unpack_from("<I", data, pos)[0]
            pos += 4
            units[idx] = data[pos:pos + L]
            pos += L
        sts = np.frombuffer(data, dtype="<u4", count=n_runs, offset=pos)
        pos += 4 * n_runs
        gls = np.frombuffer(data, dtype="<u4", count=n_runs, offset=pos)
        pos += 4 * n_runs
        for i in range(n_runs):
            st = int(sts[i])
            gl = int(gls[i])
            span = gl + L
            u = units[i]
            tile = (u * ((span + L - 1) // L))[:span]
            regen[st:st + span] = np.frombuffer(tile, dtype=np.uint8)
        cov = int(np.count_nonzero(regen))
        layer_stats.append({"lag": L, "runs": n_runs, "cum_covered": cov,
                            "added": cov - prev})
        prev = cov
    n_alpha = struct.unpack_from("<H", data, pos)[0]
    pos += 2
    alpha = data[pos:pos + n_alpha]
    pos += n_alpha
    n_fix = struct.unpack_from("<I", data, pos)[0]
    pos += 4
    fixes = []
    for _i in range(n_fix):
        fp = struct.unpack_from("<Q", data, pos)[0]
        pos += 8
        fixes.append((fp, data[pos]))
        pos += 1
    if pos != len(data):
        print(f"trailing bytes: pos={pos} len={len(data)}")
        return 2

    # deviation spans + first divergence (op space; regen[i]==0 <=> uncovered)
    first_dev = -1
    spans = 0
    carry_open = False
    for o in range(0, n, CHUNK):
        z = (regen[o:o + CHUNK] == 0)
        if first_dev < 0:
            w = np.nonzero(z)[0]
            if w.size:
                first_dev = o + int(w[0])
        d = np.diff(np.concatenate(([carry_open], z, [False])).astype(np.int8))
        spans += int((d == 1).sum())
        carry_open = bool(z[-1])
    covered = int(np.count_nonzero(regen))

    # resolve to raw space (raw = (op - i) mod 94 -> largest alphabet candidate)
    # + literal fixes + covered-exactness (chunked)
    mism_cov = 0
    fx = 0
    with open(specimen, "rb") as f:
        for o in range(0, n, CHUNK):
            ln = min(CHUNK, n - o)
            z = (regen[o:o + ln] == 0)
            idx = np.arange(o, o + ln, dtype=np.int32) % 94
            r = ((regen[o:o + ln].astype(np.int32) - idx) % 94)
            rc = np.where(r < 33, r + 94, r).astype(np.uint8)
            rc[z] = 0
            while fx < len(fixes) and fixes[fx][0] < o + ln:
                fp, fb = fixes[fx]
                rc[fp - o] = fb
                fx += 1
            regen[o:o + ln] = rc
            sc = np.frombuffer(f.read(CHUNK), dtype=np.uint8)
            m = ~z
            if m.any():
                mism_cov += int((rc[m] != sc[m]).sum())

    h = hashlib.sha256()
    for o in range(0, n, CHUNK):
        h.update(memoryview(regen)[o:o + CHUNK])
    regen_sha = h.hexdigest()
    spec_sha = sha256_file(specimen)
    res = {
        "specimen_bytes": n,
        "specimen_sha256": spec_sha,
        "regen_bytes": n,
        "regen_sha256": regen_sha,
        "byte_exact": regen_sha == spec_sha,
        "covered_bytes": covered,
        "covered_frac": round(covered / n, 6),
        "deviation_bytes": n - covered,
        "deviation_spans": spans,
        "first_deviation": first_dev,
        "covered_mismatches": mism_cov,
        "raw_alphabet_size": n_alpha,
        "resolution_fixes": n_fix,
        "layers": layer_stats,
        "seconds": round(time.time() - t0, 1),
    }
    print(json.dumps(res, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Specimen-100 M4 regeneration model G")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--specimen", required=True, type=Path)
    b.add_argument("--out", required=True, type=Path)
    b.add_argument("--header-len", type=int, default=DEFAULT_HEADER)
    c = sub.add_parser("check")
    c.add_argument("--specimen", required=True, type=Path)
    c.add_argument("--model", required=True, type=Path)
    args = ap.parse_args()
    if args.cmd == "build":
        return build(args.specimen, args.out, args.header_len)
    return check(args.specimen, args.model)


if __name__ == "__main__":
    sys.exit(main())

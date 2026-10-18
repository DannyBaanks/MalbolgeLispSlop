#!/usr/bin/env python3
"""M4: union coverage of periodicity rules over op.bin (specimen100) + deviation map.

Rule set R = {lag-L equality runs (anchors >= MINRUN)}: a run [st, gl) (eq true at
op[j]==op[j+L] for j in [st, st+gl)) regenerates the span [st, st+gl+L) by tiling
the L-byte unit op[st:st+L] (exactness is algebraic, no data stored).
Coverage = header [0, HEADER) literal + union of spans over layers.

Outputs (scratch dir): union.json, devmap_v1.bin (varint zero-span lengths),
runs_l{L}.npz per layer. Internal control: lag12/min24 must equal lag_scan.json
(481,893 runs, 92,986,899 anchor positions).
"""
import json, time
from hashlib import sha256
from pathlib import Path

import numpy as np

M4 = Path("/tmp/opencode/m4")
OP = M4 / "op.bin"
N = OP.stat().st_size
HEADER = 19392
MINRUN = 24
LAGS = [12, 7, 14, 9, 2, 4, 6, 3, 5, 8, 11, 10]
CH = 1 << 24
t0 = time.time()

# ---------- single pass: runs for every lag ----------
runs_acc = {lag: ([], []) for lag in LAGS}
K = max(LAGS)
carry = np.empty(0, dtype=np.uint8)
off = 0
with open(OP, "rb") as f:
    while True:
        c = f.read(CH)
        if not c:
            break
        a = np.frombuffer(c, dtype=np.uint8)
        buf = np.concatenate((carry, a)) if carry.size else a
        boff = off - carry.size
        for lag in LAGS:
            if buf.size > lag:
                eq = buf[lag:] == buf[:-lag]
                d = np.diff(np.concatenate(([0], eq.astype(np.int8), [0])))
                st = np.nonzero(d == 1)[0]
                en = np.nonzero(d == -1)[0]
                ss, gg = runs_acc[lag]
                for a0, b0 in zip(st, en):
                    gl = int(b0 - a0)
                    if gl >= MINRUN:
                        ss.append(boff + int(a0))
                        gg.append(gl)
        carry = buf[-K:].copy()
        off = boff + buf.size

layers = {}
for lag in LAGS:
    sts = np.asarray(runs_acc[lag][0], dtype=np.int64)
    gls = np.asarray(runs_acc[lag][1], dtype=np.int64)
    np.savez(M4 / f"runs_l{lag}.npz", sts=sts, gls=gls)
    layers[lag] = (sts, gls)
    print(f"lag {lag:>2}: runs={sts.size} pos={int(gls.sum())} span={int((gls+lag).sum())}")

# control vs lag_scan.json: lag_scan used thr=max(24,3L) and no cross-chunk carry (CH=8MB);
# union.py has carry. Compare at equal threshold and report deltas (expect tiny boundary deltas).
ctrl = json.loads((M4 / "lag_scan.json").read_text())
def ck(lag, thr):
    sts, gls = layers[lag]
    m = gls >= thr
    r = int(m.sum()); p = int(gls[m].sum())
    er = ctrl[str(lag)]["runs"]; ep = ctrl[str(lag)]["pos"]
    return {"runs": r, "exp_runs": er, "d_runs": r - er, "pos": p, "exp_pos": ep, "d_pos": p - ep}
ctl = {"lag12_thr36": ck(12, 36), "lag7_thr24": ck(7, 24), "lag2_thr24": ck(2, 24)}
print("control:", json.dumps(ctl))

# ---------- fill ----------
canon = np.memmap(OP, dtype=np.uint8, mode="r")
regen = np.zeros(N, dtype=np.uint8)
regen[0:HEADER] = canon[0:HEADER]

def nz():
    tot = 0
    for o in range(0, N, CH):
        tot += int(np.count_nonzero(regen[o:o + CH]))
    return tot

layer_stats = []
prev_cov = nz()
for lag in LAGS:
    sts, gls = layers[lag]
    idx = sts[:, None] + np.arange(lag, dtype=np.int64)[None, :]
    units = np.asarray(canon[idx])
    # unit vocabulary (for structure report)
    ucnt = {}
    for r in range(sts.size):
        key = units[r].tobytes()
        ucnt[key] = ucnt.get(key, 0) + 1
    top_u = sorted(ucnt.items(), key=lambda kv: -kv[1])[:5]
    for r in range(sts.size):
        st = int(sts[r])
        end = min(st + int(gls[r]) + lag, N)
        regen[st:end] = np.resize(units[r], end - st)
    cov = nz()
    added = cov - prev_cov
    layer_stats.append({
        "lag": lag,
        "runs": int(sts.size),
        "anchor_pos": int(gls.sum()),
        "span_bytes": int((gls + lag).sum()),
        "cum_covered": cov,
        "cum_frac": round(cov / N, 6),
        "added": added,
        "distinct_units": len(ucnt),
        "top_units": [[u.hex(), c] for u, c in top_u],
    })
    prev_cov = cov
    print(f"layer {lag:>2}: runs={int(sts.size)} added={added} cum={cov} ({cov/N:.4f})")
    del units

covered = nz()
dev_bytes = N - covered

# ---------- deviation spans (zeros), histogram, first ----------
first_dev = -1
lens_all = []
open_start = None
for o in range(0, N, CH):
    z = (regen[o:o + CH] == 0)
    if first_dev < 0:
        w = np.nonzero(z)[0]
        if w.size:
            first_dev = o + int(w[0])
    d = np.diff(np.concatenate(([open_start is not None], z, [False])).astype(np.int8))
    for idx in np.nonzero(d)[0].tolist():
        if d[idx] == 1:
            open_start = o + idx
        else:
            lens_all.append(o + idx - open_start)
            open_start = None
lens_np = np.asarray(lens_all, dtype=np.int64)
span_count = int(lens_np.size)
hist = {
    "0-15": int(((lens_np >= 1) & (lens_np <= 15)).sum()),
    "16-63": int(((lens_np >= 16) & (lens_np <= 63)).sum()),
    "64-255": int(((lens_np >= 64) & (lens_np <= 255)).sum()),
    "256-1023": int(((lens_np >= 256) & (lens_np <= 1023)).sum()),
    "1024-4095": int(((lens_np >= 1024) & (lens_np <= 4095)).sum()),
    "4096+": int((lens_np >= 4096).sum()),
}
assert int(lens_np.sum()) == dev_bytes, (int(lens_np.sum()), dev_bytes)

# varint devmap file
def vw(buf, x):
    while x >= 0x80:
        buf.append((x & 0x7F) | 0x80)
        x >>= 7
    buf.append(x)

buf = bytearray()
buf += int(span_count).to_bytes(4, "little")
buf += int(max(first_dev, 0)).to_bytes(8, "little")
for L in lens_np.tolist():
    vw(buf, int(L))
(M4 / "devmap_v1.bin").write_bytes(bytes(buf))
dev_sha = sha256(bytes(buf)).hexdigest()
print(f"devmap: spans={span_count} bytes={len(buf)} sha={dev_sha[:16]}")

# ---------- covered exactness check (mismatch inside covered must be 0) ----------
bad = 0
for o in range(0, N, CH):
    rc = regen[o:o + CH]
    cc = np.asarray(canon[o:o + CH])
    bad += int(((rc != cc) & (rc != 0)).sum())
print(f"covered-exactness mismatch count = {bad}")

def stream_sha(arr):
    h = sha256()
    for o in range(0, N, CH):
        h.update(np.asarray(arr[o:o + CH]).tobytes())
    return h.hexdigest()

regen_sha = stream_sha(regen)
canon_sha = sha256(Path("/tmp/opencode/specimen100-m1-lisp.mb").read_bytes()).hexdigest()

res = {
    "schema": "specimen100.m4.union.v1",
    "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "op_bin": {"path": str(OP), "bytes": N, "sha256": sha256(OP.read_bytes()).hexdigest()},
    "canonical_lisp_mb_sha256": canon_sha,
    "header_bytes": HEADER,
    "minrun": MINRUN,
    "layers_order": LAGS,
    "control_lag_scan": ctl,
    "layers": layer_stats,
    "covered_bytes": covered,
    "covered_frac": round(covered / N, 6),
    "deviation_bytes": dev_bytes,
    "deviation_frac": round(dev_bytes / N, 6),
    "deviation_spans": span_count,
    "deviation_span_hist": hist,
    "first_deviation": first_dev,
    "covered_exactness_mismatches": bad,
    "regen_sha256": regen_sha,
    "devmap_v1": {"file": "devmap_v1.bin", "bytes": len(buf), "sha256": dev_sha},
    "seconds": round(time.time() - t0, 1),
}
(M4 / "union.json").write_text(json.dumps(res, indent=2) + "\n")
print(json.dumps({k: res[k] for k in ("covered_bytes", "covered_frac", "deviation_bytes",
                                      "deviation_spans", "first_deviation", "regen_sha256",
                                      "seconds")}, indent=2))

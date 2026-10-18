# Gate L1 — loader convention bridge on the vendored fixed-3^19 VM

`DATE`: 2026-10-18 · `STATUS`: **DEMONSTRATED (scoped)** · `RUNNER`: `run_gate.py`

## Question

`docs/SYNTHESIS_FEASIBILITY.md` leaves `branch_zero`, `store_load`, `add_sub`,
`countdown` and `call_return` `NOT_DEMONSTRATED` for the search-based lowering,
and `docs/PARITY_MATRIX.md` leaves *independent backend agreement*
`[NOT_DEMONSTRATED]`. Meanwhile the sibling forensics line records
(`malbolge-lisp-forensics/evidence/loader_convention_v1/FINDINGS.md`) that two
image conventions coexist and that `--loader canonical` makes an external
HeLL/LMFAO product run on the same VM source this repository vendors.

## Null hypothesis

**H0 — our vendored VM cannot correctly run an opcode-aligned-text image
produced by the HeLL/LMFAO line**: the canonical accept set and the
`pos mod 564` advance do not reproduce the canonical engine, so a compiled
program is not available as a route to a Lisp guest and the search-based
lowering stays the only option.

## Method

Same artifact, same inputs, three legs, five cases (`2n+1` for `n = 0..4`):

| leg | engine | loader | role |
|---|---|---|---|
| `canonical` | this repo's `build/bolge19` | `--loader canonical` | candidate |
| `raw` | this repo's `build/bolge19` | `--loader raw` (default) | negative control |
| `unshackled` | upstream `Unshackled` VM | its own canonical loader | independent backend |

Accepted stdout is compared byte-for-byte against the sealed per-input oracles
`observed_{0..4}.bin` from the artifact's own evidence set, and the candidate
leg is compared against the independent backend leg.

`artifact.mu` (2,888,171 B, SHA-256 `3b9bdf37…`) and `src/bolge19.zig` (SHA-256
`47758a3f…`, the verbatim vendored pin in `THIRD_PARTY_NOTICES.md`) are
re-hashed before any measurement; a moved input exits `2` as `DRIFTED` instead
of producing a number. External specimens are referenced by hash and path and
are **not** copied into this repository.

## Result — H0 rejected

| verdict | value |
|---|---|
| `canonical_matches_sealed_5_of_5` | **true** |
| `unshackled_matches_sealed_5_of_5` | **true** |
| `canonical_agrees_with_unshackled` | **true** |
| `raw_control_matches_sealed` | **false** (as expected) |
| `raw_control_identical_garbage_across_inputs` | **true** |

The candidate emits `1\n 3\n 5\n 7\n 9\n`, byte-identical to the sealed
oracles and to the independent engine. Under `--loader raw` the same binary on
the same file prints the two bytes `0x02 0xCE` for **all five** inputs: the
trailing CR/LF become cells, the epochal chain seeds from them
(`pat=[10,581130723,10…]` instead of `pat=[81,581130652,81…]`) and the machine
halts with garbage **without failing loudly**. The loader warning on the raw
path exists to disarm exactly that silent failure.

## What this does NOT show

- Not MalbolgeLISP conformance. `artifact.mu` is a Translator-product-class
  specimen (hand-written EIR → `elc` → HeLL → LMFAO); it says nothing about
  MalbolgeLISP semantics, and `lisp.mb` / `core.mb` are raw cell dumps that the
  canonical loader correctly **refuses** (forensics `raw/07`, `raw/08`).
- Not a Lisp interpreter. Nothing here runs Lisp; it shows a *compiled* program
  reaches the VM, which is the prerequisite the search route kept missing.
- Not general Unshackled parity. One specimen, five inputs, one program shape.
  `PARITY_MATRIX.md` is updated with a scoped row, not a blanket upgrade.
- Not that LMFAO output is reproducible here: the toolchain is GPLv3 and lives
  in another repository, which the workspace L0 rule keeps separate. Any reuse
  is copy-and-revalidate, not import.

## Falsification

The gate is refuted by any input where the `canonical` leg differs from the
sealed oracle or from the independent backend, or by a `raw` leg that happens to
agree (which would mean the two conventions are not actually distinct).

## Side effect on sealed evidence

Editing `docs/PARITY_MATRIX.md` and `README.md` moves two hashes that
`evidence/specimen100/m6/documentation_hashes.json` pins. The M6 snapshot is
sealed evidence and was **not** rewritten; the old→new pairs and the fact that
no test catches the drift are recorded in
[`documentation_drift.json`](documentation_drift.json).

## Reproduce

```sh
./tools/build.sh
python3 evidence/loader_gate_v1/run_gate.py
sha256sum -c evidence/loader_gate_v1/SHA256SUMS.txt
```

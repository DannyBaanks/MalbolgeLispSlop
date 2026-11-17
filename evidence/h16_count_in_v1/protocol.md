# H16 — countdown whose exit is decided inside the image (2026-11-17)

Question: H14 (`../h14_countdown_v1/protocol.md`) loops with a counter rewritten
every pass, but its last dispatch reads the cell `3^17 + delta`, which lies
**above the image**; the exit there depends on the VM's fill of memory above the
image (the last two image bytes). Can the same countdown stop on an `halt` that
is inside the image, with no read above it at all?

## What was built

`slopsynth/native_count_in.py` builds `count_in(n)`, 0 ≤ n ≤ 6: it prints
3^(n-1), …, 9, 3, 1 and halts, exactly like H14, but it dispatches **before**
rotating the counter, on the current value `v`:

```
pass k   move      reads the counter cell Z: D = v, the value 3^(n+1-k)
         jump      reads the table cell v + 5 + slack_a
                   v == 1 -> halt - 1 (the in-image halt), otherwise `resume`
resume   move      D back to Z - 93 so the next lap's rotate sees D = Z
         rotate Z  A = v / 3, written back into Z
         output    prints v / 3
         move+jump back to the loop head
```

The dispatch table has one entry per dispatched value, {3^n, …, 3, 1}. Every
table cell `v + delta` is small (≤ 804 for n = 6) and inside the image; the entry
for `v == 1` holds `halt - 1 = 243`, and the `halt` opcode sits at cell 244. The
loop never reads above the image, so the exit does not depend on the VM's memory
fill — the dependency H14 documents.

All images are 13 350 cells, largest byte 126, so upstream `fast20.c` loads them
as signed chars. `resume` is 13 122 (seed 2 rotated 10 times in the prologue) and
`jump_b` is 13 349, the last cell of every image. The prologue at `FAR` = 2 106
rotates each far table cell up from its byte seed and fills the entry pointer;
for n ≤ 4 the counter 3^n is itself a byte in the image, for n = 5, 6 it is
built by rotation (12 rotations of the seed 1). Layouts are per-n, found by a
seeded search and frozen in `FROZEN`; the build checks every cell claim, so a
bad set raises `Conflict` instead of emitting a wrong image.

## Method

`python3 -B tools/verify_h16_count_in.py` builds every count, seals the images
and runs each unchanged on upstream `fast20.c` (revision `0dc37eb`, see
`../h9_fast20_crosscheck_v1/`), on `bolge19 --loader raw`, and on the Python
model with stdin closed. The model runs with `max_address = len(image) - 1`:
any read at or above the first cell past the image would return `MODEL_BOUND`,
so a `HALT` proves no access left the image; the access trace is checked too
(`max_access < len(image)`).

A case passes only if all of these hold: the model, `bolge19` and `fast20`
print the expected bytes and end by themselves; `bolge19` reports `HALT` after
exactly the model's step count; the model stops at the in-image halt stub
(`final_c == cells["halt"]`); the largest traced memory access is below the image
length; every image byte is below 128.

Negative controls (count 4): the first dispatch entry (v = 3^4) flipped, the
halt entry (v = 1) re-seeded to point at the resume path instead of the halt
(so the loop runs one pass too many and prints `1b 09 03 01 00 c3`), and the
counter seed incremented (the first dispatch then reads an empty cell). All
three must differ from the reference on both VMs. (A first attempt that only
XOR-ed the halt-entry byte still halted with the right output — the v = 1 jump
then landed on cell 1 and the bootstrap walk met a halt by accident — so that
control was replaced by the resume-pointing re-seed, which does discriminate.)

## Result — `runs/20261117T082734Z-7cd98f77`

| n | cells | image sha256 | VM steps | max access | pass |
|---:|---:|---|---:|---:|:---:|
| 0 | 13 350 | `353b4d5f…123c42` | 2 532 | 4 608 | ✓ |
| 1 | 13 350 | `73afb0c0…90d539` | 2 993 | 13 349 | ✓ |
| 2 | 13 350 | `ff2622ab…5e8cb7` | 3 259 | 13 349 | ✓ |
| 3 | 13 350 | `adaee371…8727e8` | 3 655 | 13 349 | ✓ |
| 4 | 13 350 | `6d41dc05…384d8d` | 4 051 | 13 349 | ✓ |
| 5 | 13 350 | `25b06aa3…841128` | 5 533 | 13 349 | ✓ |
| 6 | 13 350 | `6185888f…807fbb` | 8 979 | 13 349 | ✓ |

| Check | Result |
|---|---:|
| Counts 0..6 correct and self-halting on `fast20.c`, `bolge19` and the model | 7 / 7 |
| Model bound `len(image) − 1`: any read above the image would be `MODEL_BOUND` | held for all 7 |
| Largest traced memory access below the image | 13 349 < 13 350 (all counts) |
| `bolge19` step count equals the model's | 7 / 7 |
| Negative controls that differ on both VMs | 3 / 3 |

## Scope

**DEMONSTRATED:** the H14 countdown body with the dispatch moved before the
rotate, so the exit table is entirely inside the image and the loop halts on an
in-image `halt` with no read above the image, for every count the builder
supports (0..6), on both reference VMs and the model under the strict bound.

**NOT_DEMONSTRATED:**

- A compiler from IR: each count has a generated layout (frozen in `FROZEN`),
  and the body is always this one countdown; H15's IR lowering is a different CFG.
- Counts above 6: the dispatch table spreads over the low image and competes
  with the bootstrap and the prologue's far-pointer slots (cells 42..126); no
  layout was searched past 6 for this body.
- Loop bodies that compute with several cells, or branch on more than the counter.
- Loading with the canonical loader: the images contain inert cells that are not
  valid opcodes, so they need `--loader raw` (as H13a/H13b/H14 do).

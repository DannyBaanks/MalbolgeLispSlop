# H18 — lap-safe `crazy` arithmetic on a data cell inside the re-executing loop (2026-11-17)

Question: H16's countdown rewrites the counter with `rotate` every pass. H4 showed
that `st`/`ld` through `crazy` is one-shot (the mask cell is left in `f(A)`), and
H13b restores two constants per pass with a fixpoint `crazy` chain. Can a *data
cell* be rewritten by `crazy` on **every** pass of a re-executing native loop —
lap-safe `crazy` arithmetic — while the loop still halts inside the image? And can
that be a real decrement (`sub 1`)?

## What was built

`slopsynth/native_arith_loop.py` builds `arith_loop(n)`, 0 ≤ n ≤ 6, on top of the
H16 machinery (pre-rotate dispatch table on `v = Z`, in-image `halt` at cell 244,
no read above the image). The resume path of each pass is:

```
rotate Z    A = Z' = rotate(Z);  Z = Z'
output      print Z' & 0xFF
access ACC  ACC' = crazy(ACC, A=Z')  (tritwise TBL[ACC][Z']);  A = ACC'
output      print ACC' & 0xFF
move+jump   back to the loop head
```

So every non-final pass rewrites the accumulator cell `ACC` with a `crazy` whose
mask is A (the just-rotated counter) — a data-cell `crazy` update that runs on the
**same cells every pass**. The dispatch still reads `v = Z` before rotating, so
`v == 1` halts in-image. Each pass prints two bytes: `Z' mod 256`, `ACC' mod 256`.
`reference(n)` computes the expected bytes from the op order alone with the model
primitives `_rotate`/`_crazy` (not from the image).

All images are 13 444 cells, largest byte below 128, raw loader only. Layouts are
per-n, found by a seeded search (H16's frozen parameters plus the accumulator cell
per count) and frozen in `FROZEN`; the build checks every cell claim.

## Method

`python3 -B tools/verify_h18_arith_loop.py` builds every count and runs each image
unchanged on upstream `fast20.c` (revision `0dc37eb`), on `bolge19 --loader raw`,
and on the Python model with stdin closed and `max_address = len(image) - 1` (any
read above the image would return `MODEL_BOUND`; the access trace is checked too).

A case passes only if all three print the reference bytes and end by themselves,
`bolge19` reports `HALT` after exactly the model's step count, the model stops at
the in-image halt stub, the largest traced access is below the image length, and
every image byte is below 128.

Negative controls (count 4): first dispatch entry flipped, halt entry re-seeded to
the resume path (prints two extra bytes `0009`), counter seed incremented. All
three must differ on both VMs.

## Result — `runs/20261117T213050Z-64631c8d`

| n | image sha256 | VM steps | max access | output (hex) | pass |
|---:|---|---:|---:|---|:---:|
| 0 | `5bf6768e…786fc9` | 2 532 | 4 608 | (empty) | ✓ |
| 1 | `29c4dc4d…2884d8` | 3 087 | 13 443 | `01ee` | ✓ |
| 2 | `7f5914f4…0e74ce` | 3 447 | 13 443 | `03eb01ee` | ✓ |
| 3 | `a2cbf936…093eb1` | 3 937 | 13 443 | `09e503eb01ee` | ✓ |
| 4 | `7cffe560…8df2ec` | 4 427 | 13 443 | `1bd309e503eb01ee` | ✓ |
| 5 | `5aa87dad…8b3c26` | 6 003 | 13 443 | `519d1bd309e503eb01ee` | ✓ |
| 6 | `579e307c…7c883c` | 9 543 | 13 443 | `f3fb519d1bd309e503eb01ee` | ✓ |

| Check | Result |
|---|---:|
| Counts 0..6 correct and self-halting on `fast20.c`, `bolge19` and the model | 7 / 7 |
| Model bound `len(image) − 1` held; max traced access 13 443 < 13 444 | 7 / 7 |
| `bolge19` step count equals the model's | 7 / 7 |
| Accumulator rewritten by `crazy` exactly once per rotating pass | checked for n=4 in tests |
| Negative controls that differ on both VMs | 3 / 3 |

## Scope

**DEMONSTRATED:** a data cell rewritten by `crazy` on every pass of a re-executing
native lapped loop (lap-safe `crazy` arithmetic, the primitive a looping ALU would
need), combined with `rotate` on the counter and an in-image exit, for counts 0..6,
on both reference VMs and the model under the strict bound.

**NOT_DEMONSTRATED:**

- A true decrement (`sub 1`) inside a re-executing loop. fixed19 has no store
  opcode (`move` only sets `D = mem[D]`; stores go through `crazy`/`rotate`) and
  `crazy` is tritwise, so carry is not expressible as one `crazy`; H7 lowered
  `sub n, n, 1` straight-line with landing cascades, not in a re-executing loop.
  H18 demonstrates the lap-safe cell-update primitive, not borrow arithmetic.
- Counts above 6 (dispatch table vs. bootstrap/prologue slot budget, as in H16).
- More than one `crazy` per pass on the accumulator, or arithmetic mixing more
  than two cells per pass.
- Loading with the canonical loader (inert cells).

# H14 — native countdown loop with state rewritten on every pass (2026-11-13)

Question: H13b (`../h13_cat_v1/protocol.md`) loops and halts, but its generator
is one hand-shaped function. Can the machinery be shared, and does it support a
second loop whose *own state* changes on every pass and decides when it ends?

## What was built

`slopsynth/native_asm.py` now holds the pieces both programs use: `Memory`
(every use of a cell is recorded; two uses that disagree, or a value that does
not fit in a signed char, raise `Conflict`), `Once` (straight-line one-shot
code with D tracked), `Laps` (alternating-pair cells placed at their residues
in laps of 94) and `bootstrap`. The refactor is checked by an unchanged image:
`native_cat` still builds sha256 `b4e4b2c0…ab8e2` (a test).

`slopsynth/native_count.py` builds `countdown(n)`, 0 ≤ n ≤ 5: it prints
3^(n-1), …, 9, 3, 1 and halts. The counter is a memory cell holding 3^n.

- lap 1: `rotate` on the counter divides it by 3 in place (A = new value);
- `output` prints A;
- a `move` reads the counter itself, so D becomes the counter value; the next
  `jump` reads the cell at that address + 5 + slack: a table with one entry per
  counter value (`resume`, a far address built by rotation in the prologue);
- after 3^0 the next rotation wraps to 3^17: the jump reads memory above the
  image, which the VM fills from the image's last two bytes. The builder
  picks those two bytes so that the value read there is a small address whose
  next cell holds `halt`. `pattern_values` reproduces the VM's fill without
  running it cell by cell (a test compares it with the model's memory).

## Method

`python3 -B tools/verify_h14_countdown.py` builds every count and runs it
unchanged on upstream `fast20.c` (revision `0dc37eb`), `bolge19 --loader raw`
and the Python model with stdin closed. A case passes if all three print the
expected bytes and end by themselves, `bolge19` reports HALT after the model's
step count, the model stops at the halt stub, and every image byte is below 128.

Negative controls (count 3): one table cell corrupted, and the counter seed
changed. Both must differ on both VMs. (A first control that only deleted the
`halt` cell was dropped: cells never written hold 0, which decodes to `halt`
at address 81, so the run still ended and the control proved nothing.)

## Result — `runs/20261113T030638Z-ccc541cb`

| Check | Result |
|---|---:|
| Counts 0..5 correct and self-halting on `fast20.c`, `bolge19` and the model | 6 / 6 |
| Steps for counts 0..5 | 739, 1136, 1535, 1857, 1942, 2827 |
| Negative controls that differ | 2 / 2 |

## Scope

**DEMONSTRATED:** native loops whose body rewrites a data cell on every pass and
whose exit depends on that cell, for counts 0 to 5, on both reference VMs.

**NOT_DEMONSTRATED:**

- A compiler from IR to native loops. Layouts come from a seeded search, one per
  count (frozen in `FROZEN`), and the body is always `rotate; output; exit`.
- Counts above 5. For n ≥ 6 the search found no layout: the one-shot prologue
  needs a free pointer cell for every constant it builds and runs out.
- Loop bodies with several cells, arithmetic or other exits. H13b's `cat` shows
  an input-driven exit; the two exits are not combined.
- The canonical loader (the images contain inert cells that are not valid opcodes).
- Dependence on the filler: the exit relies on the VM's fill of memory above the
  image, which both reference VMs agree on (H9 cross-check) but which is not part
  of any Malbolge specification.

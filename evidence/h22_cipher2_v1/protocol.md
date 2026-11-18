# H22 — chained two-accumulator cipher (2026-11-18)

Question: H20 rewrites one accumulator cell with `crazy` per pass (mask = the input
byte). Can a pass run a **chain** of two `crazy` cell updates — the second one's
mask being the first one's fresh result — all lap-safe in the re-executing loop?

## What was built

`slopsynth/native_cipher2.py` builds `cipher2()`, on H20's two-read loop (selector +
payload, H13b EOF identity, in-image `halt`). In the resume path, after reading the
payload `b` (A = b):

```
access(ACC1)   ACC1' = crazy(ACC1, A=b)     TBL[ACC1][b];  A = ACC1'
access(ACC2)   ACC2' = crazy(ACC2, A=ACC1') TBL[ACC2][ACC1']; A = ACC2'
output         print ACC2' & 0xFF
```

Both data cells are rewritten by `crazy` every pass; the chain flows through A, so
no mask needs restoring. The loop halts inside the image at a zero selector or EOF;
no memory above the image is read (model bound `max_address = len(image) - 1`).

`reference(stdin)` computes the expected bytes from the op order alone with
`_crazy`; `chains(stdin)` returns both full accumulator chains for write traces.
Image: 4 979 cells, largest byte below 128, sha256
`0b4d897643b963bcffbf390c40e5eaeb34e761e6aed4370b7ea9372f368c553a`, raw loader
only. Layout: H20's frozen addresses plus `ACC2 = 43`; the build checks every claim.

## Method

`python3 -B tools/verify_h22_cipher2.py` seals the image and runs 50 cases unchanged
on upstream `fast20.c` (revision `0dc37eb`), on `bolge19 --loader raw`, and on the
Python model with `max_address = len(image) - 1` (access trace checked). Campaign:
empty, zero selector, single/multi pass, truncated payload, 64-pass, all byte
values 1..127, 100-byte runs, 40 seeded random inputs (half zero-terminated). A case
passes only if all three print the reference bytes and end by themselves, `bolge19`
reports `HALT` after exactly the model's step count, and the model stops at the
in-image halt stub. Both accumulator write chains are checked against `chains` via
`trace_writes` on a 3-pass input.

Negative controls (input `02 41 02 42`, must differ from the reference on both VMs):
selector-2 dispatch entry flipped, ACC1 seed incremented, ACC2 seed incremented.

## Result — `runs/20261118T014700Z-577fc1c1`

| Check | Result |
|---|---:|
| Cases correct and self-halting on `fast20.c`, `bolge19` and the model | 50 / 50 |
| Model bound `len(image) − 1` held; max traced access below the image | yes |
| `bolge19` step count equals the model's | 50 / 50 |
| Both accumulator chains rewritten once per pass (write trace matches `chains`) | yes |
| Negative controls that differ on both VMs | 3 / 3 |

## Scope

**DEMONSTRATED:** a pass of a re-executing native loop can run a *chain* of two
`crazy` data-cell updates (mask of the second = result of the first), input-driven,
with an in-image halt and no read above the image, on both reference VMs and the
model under the strict bound.

**NOT_DEMONSTRATED:**

- A compiler from IR for this two-accumulator chain: the IR lowering covers the
  H17/H19/H21 CFGs, not yet this one.
- Borrow-based arithmetic per pass (no store opcode; `crazy` is tritwise).
- Loading with the canonical loader (inert cells).
- A proof for all inputs: the campaign is 50 finite cases.

# H20 — input-driven cipher loop with lap-safe `crazy` (2026-11-18)

Question: H18 made a data cell lap-safe under `crazy` driven by the loop's own
counter. Can the same lap-safe `crazy` be driven by **input** — one `crazy` per
read byte inside the re-executing loop, with an in-image halt at end of input?

## What was built

`slopsynth/native_cipher.py` builds `cipher()`, on top of H15's two-read loop
(selector + payload, H13b's EOF identity `byte -> b`, `EOF -> 1700`, in-image
`halt`). Each pass:

```
read selector s          byte s, or the EOF word
identity (two crazy)     A = s, or 1700 for EOF
table dispatch on s      s == 0 or EOF -> in-image halt; else resume
restore Y and W          (A still holds the selector, as in H15)
read payload b           A = b (or the EOF word on truncated input)
access(ACC)              ACC' = crazy(ACC, A=b)  tritwise TBL[ACC][b]; A = ACC'
output                   print ACC' & 0xFF
move+jump                back to the head
```

The accumulator cell `ACC` (seed 5) is rewritten by a `crazy` whose mask is the
*input byte* on every pass — input-driven lap-safe arithmetic — and the loop
halts inside the image at a zero selector or EOF. The same cells run every pass;
no memory above the image is read (model bound `max_address = len(image) - 1`).

`reference(stdin)` computes the expected output from the op order alone with the
model primitive `_crazy` (reads selector/payload pairs, stops at a zero selector,
appends `ACC' & 0xFF` per pass; truncated payload uses the profile EOF word).

The image is 4 791 cells, largest byte below 128, sha256
`c7ef70e4b959c31400c64e250698beba19cf49877e064283b307f0037656610f`, raw loader
only. Addresses were found by a seeded search and frozen in `PARAMS`; the build
checks every cell claim.

## Method

`python3 -B tools/verify_h20_cipher.py` seals the image and runs 50 cases
unchanged on upstream `fast20.c` (revision `0dc37eb`), on `bolge19 --loader raw`,
and on the Python model with `max_address = len(image) - 1` (any read above the
image would return `MODEL_BOUND`; the access trace is checked too). Cases:
empty, zero selector, single/multi pass, truncated payload, 64-pass runs,
100-byte runs, all byte values 1..127, and 40 seeded random inputs (half
zero-terminated, half EOF-terminated). A case passes only if all three print the
reference bytes and end by themselves, `bolge19` reports `HALT` after exactly the
model's step count, and the model stops at the in-image halt stub. The
accumulator write chain on a 3-pass input is checked against `acc_chain` via
`trace_writes`.

Negative controls (each on a tailored input, must differ from the reference on
both VMs): dispatch entry of selector 2 flipped (input `02 41 02 42`), dispatch
entry of selector 3 flipped (input `03 58 03 59 00`), accumulator seed
incremented (input `02 41 02 42`). (A control that flipped the EOF/halt pointer
byte or the halt stub did not discriminate — the output is already printed before
the halt and the run still ends — so those were replaced by output-changing
controls.)

## Result — `runs/20261118T002728Z-d104dc03`

| Check | Result |
|---|---:|
| Cases correct and self-halting on `fast20.c`, `bolge19` and the model | 50 / 50 |
| Model bound `len(image) − 1` held; max traced access below the image | yes (max < 4 791) |
| `bolge19` step count equals the model's | 50 / 50 (1 091 .. ~20 000 steps) |
| Accumulator rewritten by `crazy` once per pass (write trace matches `acc_chain`) | yes |
| Negative controls that differ on both VMs | 3 / 3 |

## Scope

**DEMONSTRATED:** an input-driven native lapped loop that rewrites a data cell
with `crazy` (mask = the byte just read) on every pass and halts inside the image
at a zero selector or EOF, on both reference VMs and the model under the strict
bound.

**NOT_DEMONSTRATED:**

- A compiler from IR for this loop: the IR lowering (H17/H19) covers the counter
  loops, not yet the selector+payload cipher CFG.
- Borrow-based arithmetic (add/sub with carry) per pass: no store opcode and
  `crazy` is tritwise (see H18).
- Loading with the canonical loader (inert cells).
- A proof for all inputs: the campaign is 50 finite cases, not every byte string.

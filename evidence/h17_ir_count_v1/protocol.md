# H17 — the countdown lowered from an IR module (2026-11-17)

Question: H16 built the in-image countdown by hand (`native_count_in.py`), and
H15 lowered H3's loop from IR. Can the IR now *express* a loop that mutates a
memory cell every pass and branches on its value — i.e., can a compiler take a
countdown module and emit the native H16 image?

## What was built

The IR gains two operations (`slopsynth/ir.py`, with parser mnemonics in
`lang.py` and JSON fields in `ir_json.py`):

- `Rotate(address)` — `rot <addr>`: `A = rotate(mem[addr])` one trit to the right,
  `mem[addr] = A`.
- `BranchEq(value, rhs, eq_target, ne_target)` — `breq <v>, <rhs>, <eq>, <ne>`:
  branch on `value == rhs`.

With them the countdown is an ordinary module (`examples/ir_count.slop`, n = 4):

```
entry init
init:  st Z, 81            ; counter cell starts at 3^4
       jump top
top:   ld v, Z
       breq v, 1, done, body
body:  rot Z              ; counter /= 3, A = new value
       write              ; print A
       jump top
done:  halt
```

`slopsynth/native_ir_count.py` accepts exactly that CFG (one parameterless
function, four blocks: `init` = `st <cell>, 3^n; jump top`, `top` = `ld <v>,
<cell>; breq <v>, 1, done, body`, `body` = `rot <cell>; write; jump top`, `done`
= `halt`) and checks every declared case against the reference before emitting
anything; anything else raises `AssemblyError`. The `breq v, 1` lowers to H16's
native dispatch table on the counter value (the entry for `v == 1` is the
in-image `halt`), and `rot` lowers to the lapped `rotate` pair. `lower()` emits
through `native_count_in`'s frozen layouts keyed by the module's `n`, so **the
IR-compiled image is byte-identical to the sealed H16 image** for every count
(checked in the campaign). The module's cell name is bound to the frozen `Z`
cell.

The program reads no input: every case's stdin is ignored and its stdout must be
3^(n-1), …, 9, 3, 1.

## Method

`python3 -B tools/verify_h17_ir_count.py` compiles every count through the IR
path (`parse_placed(module_source(n))` → `check_module` → `lower`), writes the
module source and image, and runs each image unchanged on upstream `fast20.c`
(revision `0dc37eb`), on `bolge19 --loader raw`, and on the Python model with
stdin closed and `max_address = len(image) - 1` (any read above the image would
return `MODEL_BOUND`; the access trace is checked too).

A case passes only if the model, `bolge19` and `fast20` print the reference
bytes and end by themselves, `bolge19` reports `HALT` after exactly the model's
step count, the model stops at the in-image halt stub, the largest traced access
is below the image length, the image equals `build_count_in(n).image`, and every
image byte is below 128.

Refusals: six mutated modules (breq rhs 2, counter not a power of three, counter
3^7, cell mismatch, contradicted case, body without `write`) must each raise
`AssemblyError` before any image is emitted. Image-level negative controls
(count 4), as in H16: first dispatch entry flipped, halt entry re-seeded to the
resume path (prints `1b 09 03 01 00 c3`), counter seed incremented — all three
must differ on both VMs.

## Result — `runs/20261117T095119Z-cd7cc58f`

| n | image sha256 | VM steps | pass |
|---:|---|---:|:---:|
| 0 | `353b4d5f…123c42` | 2 532 | ✓ |
| 1 | `73afb0c0…90d539` | 2 993 | ✓ |
| 2 | `ff2622ab…5e8cb7` | 3 259 | ✓ |
| 3 | `adaee371…8727e8` | 3 655 | ✓ |
| 4 | `6d41dc05…384d8d` | 4 051 | ✓ |
| 5 | `25b06aa3…841128` | 5 533 | ✓ |
| 6 | `6185888f…807fbb` | 8 979 | ✓ |

The hashes are identical to H16's sealed images (`../h16_count_in_v1/`), because
the IR path emits through the same frozen layouts.

| Check | Result |
|---|---:|
| Counts 0..6 compiled from IR and self-halting on `fast20.c`, `bolge19` and the model | 7 / 7 |
| Emitted image byte-identical to the H16 builder for the same n | 7 / 7 |
| Model bound `len(image) − 1` held; max traced access 13 349 < 13 350 | 7 / 7 |
| `bolge19` step count equals the model's | 7 / 7 |
| Mutated modules refused before emission | 6 / 6 |
| Image-level negative controls differing on both VMs | 3 / 3 |

## Scope

**DEMONSTRATED:** the IR can express `rotate` on a memory cell and a branch on a
cell's value, and `native_ir_count.lower` compiles exactly that countdown CFG to
a native lapped image (byte-identical to H16) that halts inside the image with
no read above it, for every count 0..6, on both reference VMs and the model.

**NOT_DEMONSTRATED:**

- Any CFG other than this countdown: `check_module` refuses every other block
  shape, any `breq` with rhs ≠ 1, and any counter outside 3^0..3^6.
- `Rotate`/`BranchEq` in the predicated compiler (`predicated.py`): those ops
  still have no lowering there.
- A layout search driven by the module: layouts are the frozen H16 ones keyed by
  n; the compiler binds the module's cell name to the frozen `Z` address.
- Arithmetic in general inside a native loop body (H17 adds only the single
  `rotate`); comparisons other than `== 1` on the counter.
- Loading with the canonical loader: the images contain inert cells.

# H19 — the arithmetic loop lowered from an IR module (2026-11-17)

Question: H17 lowered the countdown from IR after adding `rot`/`breq`; H18 added
lap-safe `crazy` arithmetic on a data cell in the native loop. Can the IR now
express *that* loop — a counter plus an accumulator updated by `crazy` every
pass — and compile it to the sealed H18 image?

## What was built

The IR gains `CrazyCell` (`craz <cell>`): `mem[cell] = crazy(mem[cell], A)`
tritwise (mask in A); `A = result`. With it the H18 loop is an ordinary module
(`examples/ir_arith.slop`, n = 4):

```
entry init
init:  st Z, 81            ; counter = 3^4
       st ACC, 5           ; accumulator seed
       jump top
top:   ld v, Z
       breq v, 1, done, body
body:  rot Z              ; Z' = rotate(Z); A = Z'
       write              ; print Z'
       craz ACC           ; ACC' = crazy(ACC, A=Z'); A = ACC'
       write              ; print ACC'
       jump top
done:  halt
```

`slopsynth/native_ir_arith.py` accepts exactly that CFG (one parameterless
function, four blocks) and checks every declared case against
`native_arith_loop.reference` before emitting anything; anything else raises
`AssemblyError`. `lower()` emits through `native_arith_loop`'s frozen layouts
keyed by the module's `n`, so **the IR-compiled image is byte-identical to the
sealed H18 image** for every count (checked in the campaign). The module's two
cell names are bound to the frozen `Z`/`acc` cells. The program reads no input.

## Method

`python3 -B tools/verify_h19_ir_arith.py` compiles every count through the IR
path (`parse_placed(module_source(n))` → `check_module` → `lower`), writes the
module source and image, and runs each image unchanged on upstream `fast20.c`
(revision `0dc37eb`), on `bolge19 --loader raw`, and on the Python model with
stdin closed and `max_address = len(image) - 1` (any read above the image would
return `MODEL_BOUND`; the access trace is checked too).

A case passes only if the model, `bolge19` and `fast20` print the reference bytes
and end by themselves, `bolge19` reports `HALT` after exactly the model's step
count, the model stops at the in-image halt stub, the largest traced access is
below the image length, the image equals `build_arith_loop(n).image`, and every
image byte is below 128.

Refusals: six mutated modules (breq rhs 2, counter not a power of three,
accumulator seed changed, `craz` on the counter, `craz` removed, contradicted
case) must each raise `AssemblyError` before any image is emitted. Image-level
negative controls (count 4), as in H16/H18: first dispatch entry flipped, halt
entry re-seeded to the resume path, counter seed incremented — all three must
differ on both VMs.

## Result — `runs/20261117T221539Z-54ccf087`

| n | image sha256 | VM steps | pass |
|---:|---|---:|:---:|
| 0 | `5bf6768e…786fc9` | 2 532 | ✓ |
| 1 | `29c4dc4d…2884d8` | 3 087 | ✓ |
| 2 | `7f5914f4…0e74ce` | 3 447 | ✓ |
| 3 | `a2cbf936…093eb1` | 3 937 | ✓ |
| 4 | `7cffe560…8df2ec` | 4 427 | ✓ |
| 5 | `5aa87dad…8b3c26` | 6 003 | ✓ |
| 6 | `579e307c…7c883c` | 9 543 | ✓ |

The hashes are identical to H18's sealed images (`../h18_arith_loop_v1/`).

| Check | Result |
|---|---:|
| Counts 0..6 compiled from IR and self-halting on `fast20.c`, `bolge19` and the model | 7 / 7 |
| Emitted image byte-identical to the H18 builder for the same n | 7 / 7 |
| Model bound `len(image) − 1` held; max traced access below the image | 7 / 7 |
| `bolge19` step count equals the model's | 7 / 7 |
| Mutated modules refused before emission | 6 / 6 |
| Image-level negative controls differing on both VMs | 3 / 3 |

## Scope

**DEMONSTRATED:** the IR can express `craz` on a cell (crazy with the mask in A),
and `native_ir_arith.lower` compiles exactly that arithmetic-loop CFG to a native
lapped image (byte-identical to H18) that halts inside the image with no read
above it, for every count 0..6, on both reference VMs and the model.

**NOT_DEMONSTRATED:**

- Any CFG other than this arithmetic loop: `check_module` refuses every other
  block shape.
- `CrazyCell` in the predicated compiler (`predicated.py`): no lowering there.
- Borrow-based arithmetic (add/sub with carry) in a re-executing loop: fixed19
  has no store opcode and `crazy` is tritwise (see H18); H7 lowered `sub`
  straight-line only.
- A layout search driven by the module: layouts are the frozen H18 ones keyed by n.
- Loading with the canonical loader (inert cells).

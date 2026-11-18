# H21 — the cipher loop lowered from an IR module (2026-11-18)

Question: H20 built the input-driven cipher loop natively. Can the IR lowering
(H17/H19) now compile *that* CFG too, so the compiler covers both the counter
loops and the selector+payload loop?

## What was built

`slopsynth/native_ir_cipher.py` accepts exactly this module
(`examples/ir_cipher.slop`):

```
entry init
init:  st ACC, 5            ; accumulator seed
       jump top
top:   read s
       brz s, zero, echo    ; zero selector halts (EOF halts via the table)
zero:  halt
echo:  read b
       craz ACC             ; ACC' = crazy(ACC, A=b); A = ACC'
       write                ; print ACC' & 0xFF
       jump top
```

`check_module` requires one parameterless function with those four blocks in
that exact op shape, and checks every declared case against
`native_cipher.reference` before emitting anything; anything else raises
`AssemblyError`. `lower()` emits through `native_cipher`'s frozen `PARAMS`, so
**the IR-compiled image is byte-identical to the sealed H20 image** (sha256
`c7ef70e4…56610f`, 4 791 cells) and no memory above it is read.

## Method

`python3 -B tools/verify_h21_ir_cipher.py` compiles `examples/ir_cipher.slop`
through the IR path (`parse_placed` → `check_module` → `lower`), writes the
module and image, and runs 50 campaign inputs unchanged on upstream `fast20.c`
(revision `0dc37eb`), on `bolge19 --loader raw`, and on the Python model with
`max_address = len(image) - 1` (any read above the image would return
`MODEL_BOUND`; the access trace is checked too). Campaign: empty, zero selector,
single/multi pass, truncated payload, 64-pass, all byte values 1..127, 100-byte
runs, 40 seeded random inputs (half zero-terminated, half EOF-terminated).

A case passes only if all three print the reference bytes and end by themselves,
`bolge19` reports `HALT` after exactly the model's step count, the model stops at
the in-image halt stub, and the image equals `native_cipher._build(PARAMS).image`.

Refusals: six mutated modules (brz targets swapped, accumulator seed 6, `craz`
on another cell, payload `write` removed, contradicted case, `breq` instead of
`brz`) must each raise `AssemblyError` before any image is emitted. Image-level
negative controls on input `02 41 02 42`: selector-2 dispatch entry flipped and
accumulator seed incremented — both must differ from the reference on both VMs.

## Result — `runs/20261118T010652Z-6a3d3f2f`

| Check | Result |
|---|---:|
| Cases correct and self-halting on `fast20.c`, `bolge19` and the model | 50 / 50 |
| Emitted image byte-identical to the H20 builder | yes |
| Model bound `len(image) − 1` held; max traced access below the image | yes |
| `bolge19` step count equals the model's | 50 / 50 |
| Mutated modules refused before emission | 6 / 6 |
| Image-level negative controls differing on both VMs | 2 / 2 |

## Scope

**DEMONSTRATED:** the IR lowering now covers both the counter loops (H17/H19) and
the selector+payload cipher loop (H21), each compiled to a native lapped image
that halts inside the image with no read above it, on both reference VMs and the
model under the strict bound.

**NOT_DEMONSTRATED:**

- Any CFG other than these: `check_module` refuses every other block shape.
- `craz`/`rot`/`breq` in the predicated compiler (`predicated.py`): no lowering there.
- Borrow-based arithmetic (add/sub with carry) in a re-executing loop: no store
  opcode and `crazy` is tritwise (see H18/H20).
- Loading with the canonical loader (inert cells).
- A proof for all inputs: the campaign is 50 finite cases.

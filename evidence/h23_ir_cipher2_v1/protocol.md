# H23 — the two-accumulator cipher loop lowered from an IR module (2026-11-18)

Question: H22 chained two lap-safe `crazy` accumulator updates per pass natively.
Can the IR lowering (H17/H19/H21) compile that two-`craz` CFG too? And — the
open question this milestone also settles — is carry-based arithmetic possible
at all inside a re-executing loop in fixed19?

## What was built

`slopsynth/native_ir_cipher2.py` accepts exactly this module
(`examples/ir_cipher2.slop`):

```
entry init
init:  st ACC, 5
       st ACC2, 7
       jump top
top:   read s
       brz s, zero, echo
zero:  halt
echo:  read b
       craz ACC         ; ACC1' = crazy(ACC, A=b); A = ACC1'
       craz ACC2        ; ACC2' = crazy(ACC2, A=ACC1'); A = ACC2'
       write            ; print ACC2' & 0xFF
       jump top
```

`check_module` requires one parameterless function with those four blocks in
that exact op shape, and checks every declared case against
`native_cipher2.reference` before emitting anything; anything else raises
`AssemblyError`. `lower()` emits through `native_cipher2`'s frozen `PARAMS`, so
**the IR-compiled image is byte-identical to the sealed H22 image** (sha256
`0b4d8976…553a`, 4 979 cells) and no memory above it is read.

## Method

`python3 -B tools/verify_h23_ir_cipher2.py` compiles `examples/ir_cipher2.slop`
through the IR path (`parse_placed` → `check_module` → `lower`), writes module
and image, and runs 50 campaign inputs unchanged on upstream `fast20.c`
(revision `0dc37eb`), on `bolge19 --loader raw`, and on the Python model with
`max_address = len(image) - 1` (access trace checked). Campaign: empty, zero
selector, single/multi pass, truncated payload, 64-pass, all byte values 1..127,
100-byte runs, 40 seeded random inputs (half zero-terminated). A case passes only
if all three print the reference bytes and end by themselves, `bolge19` reports
`HALT` after exactly the model's step count, the model stops at the in-image halt
stub, and the image equals `native_cipher2._build(PARAMS).image`.

Refusals: six mutated modules (brz swapped, ACC seed 6, ACC2 seed 8, craz order
swapped, one craz removed, contradicted case) must raise `AssemblyError` before
any image is emitted. Image-level negative controls on input `02 41 02 42`:
selector-2 dispatch entry flipped, ACC seed and ACC2 seed incremented — all must
differ from the reference on both VMs.

## Result — `runs/20261118T031812Z-6facd276`

| Check | Result |
|---|---:|
| Cases correct and self-halting on `fast20.c`, `bolge19` and the model | 50 / 50 |
| Emitted image byte-identical to the H22 builder | yes |
| Model bound `len(image) − 1` held; max traced access below the image | yes |
| `bolge19` step count equals the model's | 50 / 50 |
| Mutated modules refused before emission | 6 / 6 |
| Image-level negative controls differing on both VMs | 3 / 3 |

## The structural finding on carry arithmetic in a re-executing loop

The fixed19 profile has exactly 8 opcodes: `jump, output, input, rotate, move,
crazy, nop, halt` (`profiles/fixed19.json` dispatch). There is **no store
opcode**: `move` only sets `D = mem[D]`; `input` under the raw loader only sets
A; the only cell writes are `rotate` (`mem[D] := rotate(mem[D])`) and `crazy`
(`mem[D] := TBL[mem[D]][A]`) — both functions of the cell's own current value.
Consequences:

- An arbitrary computed value cannot be written into a designated cell, so a
  carry-correct sum cannot be persisted into an accumulator across passes.
- An input byte cannot be stashed exactly into a cell (the canonical loader's
  input slot trick that H9 v3 relies on does not exist under the raw loader).
- `crazy` is tritwise, so carry never arises in one op.

Hence carry-based arithmetic (add/sub) inside a re-executing lapped loop is
**impossible in this VM, not merely not found**. H9 v3's carry adder works only
as an acyclic canonical circuit whose result lives in A and is printed
(`write_decimal`), never stored. Inside lapped loops the only lap-safe cell
updates are functions of the cell itself: `rotate` (÷3, H16) and `crazy` with
the mask in A (H18/H20/H22).

## Scope

**DEMONSTRATED:** the IR lowering now covers four CFGs — the countdown (H17),
the arithmetic loop (H19), the cipher (H21) and the two-accumulator cipher
(H23) — each compiled to a native lapped image (byte-identical to its native
sealed counterpart) that halts inside the image with no read above it, on both
reference VMs and the model under the strict bound.

**NOT_DEMONSTRATED:**

- Carry-based arithmetic (add/sub with carry) in a re-executing loop —
  structurally impossible in fixed19 (no store opcode; see above).
- Any CFG other than these four: `check_module` refuses every other shape.
- `craz`/`rot`/`breq` in the predicated compiler (`predicated.py`).
- Loading with the canonical loader (inert cells).
- A proof for all inputs: the campaign is 50 finite cases.

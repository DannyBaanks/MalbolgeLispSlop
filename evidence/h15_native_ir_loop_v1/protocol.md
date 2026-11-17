# H15 — first native loop emitted from IR (2026-11-17)

Question: H13a/H13b/H14 loop on the same cells every pass, but each image comes
from one hand-shaped builder for one program. H3 lowered an IR module to a loop
that does not iterate (see `../h3_h7_loop_audit_v1/`). Can a compiler take an IR
module, check it, and emit a native lapped loop that halts by itself — the same
shape H3 declares, this time actually looping?

## What was built

`slopsynth/native_ir_loop.py` lowers exactly one CFG, H3's loop:

```
top:  read
      brz A, zero, echo
zero: halt
echo: read
      write
      jump top
```

`check_module()` accepts only that shape (one function, one parameterless entry
block, `read`; `brz A`; a zero block that is only `halt`; a nonzero block that is
`read`; `write`; `jump` to the entry) and checks every declared case against the
reference semantics before emitting anything. Everything else raises
`AssemblyError`. `lower()` then builds the image with the shared pieces of
`native_asm.py` (`Memory`, `Once`, `Laps`, `bootstrap`).

The module is `examples/ir_loop.slop` with three declared cases (`00` → silence,
`024100` → `41`, `0241024200` → `4142`). The emitted image is 4 795 cells; its
largest byte is 126, so upstream `fast20.c` loads it as signed chars.

Per pass (2 074 VM steps; the same cells every time):

1. `input`; `crazy` on Y (all nineteen trits 1) and W (850). For a byte `b` the
   result is `b`; for EOF (nineteen 2s) it is 1700. W keeps it.
2. A `move` with D at W: D becomes `b + 1` or 1701. A second `move`, four laps
   later, reads a dispatch table laid out where D drifts, one entry per byte
   address plus the cell at 2076 for EOF. Selector 0 and EOF point to the halt
   pointer; the other 255 entries point to the resume path. The `jump` after the
   second move therefore continues the loop for a byte and lands beside an
   in-image `halt` (cell 99) otherwise.
3. On the resume path: `output` is not yet reached — A still holds the selector,
   so first the seven `crazy` and one `rotate` of H13b restore Y and W, reading
   two constants (1700 and its complement) without changing them. Then the
   payload is read, printed, and a `move` + `jump` returns to the head.

Because the selector is tested before the payload is read, a truncated input does
not need a special case: the loop reads the payload as EOF, prints `0xDA`, and the
next pass reads EOF as the selector and halts. That is observably the same
behaviour as H3's host loop, which stops at end of input.

Nothing above the image is read: the halt pointer and the loop-back target are
constants built by the one-shot prologue, so the exit does not depend on the VM's
memory fill (the dependency H14 documents). The model run with
`max_address=len(image)` would have refused any read above the image, and none
was attempted.

Values above 127 cannot be loaded, so the prologue at `FAR` (address 2107) makes
them: jump targets by `rotate` (18 − k rotations multiply a byte by 3^k), and
Y, W, U, V by `crazy` from byte seeds. A 31-cell bootstrap at address 0 builds
the prologue's own address the same way. Every address in `PARAMS` is frozen; the
build checks each claim, and a layout that disagrees raises `Conflict` instead of
emitting a wrong image.

## Method

`python3 -B tools/verify_h15_native_ir_loop.py` builds the module, seals the image
and runs it unchanged on upstream `fast20.c` (revision `0dc37eb`, see
`../h9_fast20_crosscheck_v1/`), on `bolge19 --loader raw`, and (inputs up to 300
bytes) on the Python model.

A case passes only if stdout equals the reference **and** the run ends by itself:
`fast20` exits with status 0; `bolge19` and the model report HALT after exactly
`1279 + 2074 × passes` steps, where a pass is a nonzero selector. `bolge19` is run
with `--max-steps steps + 1` and must print `HALT steps=steps`.

Inputs (390): empty; each of the 256 single bytes; 37 single bytes with a zero
tail; 51 byte pairs `(b, 255−b)`; 29 such pairs with a zero tail; a ramp
`01..ff`; text; 500 × `0x00`; 500 × `0xDA` (low byte of the EOF word); seeded
random inputs of 2 to 100 000 bytes; one of 1 000 000; and 1 000 000 bytes with
no zero (`(i % 255) + 1`), which reaches 500 000 passes.

Negative controls: the dispatch entry of selector 0 overwritten with the resume
pointer (the loop must not stop on a zero selector), and the dispatch entry of
`M` overwritten with the halt pointer (it must stop early). Both must differ from
the reference on both VMs. A control that only corrupted the payload path would
not test the branch, so only branch cells are mutated.

## Result — `runs/20261117T053249Z-9844f058`

| Check | Result |
|---|---:|
| Cases correct and halted on `fast20.c`, `bolge19` and the model | 390 / 390 |
| Longest input | 1 000 000 bytes, 500 000 passes, 1 037 001 279 VM steps |
| Startup + exit, steps per pass | 1 279, 2 074 (checked for 0, 1, 2 and 500 000 passes) |
| Negative controls that differ from the reference | 2 / 2 |
| Image | 4 795 cells, largest byte 126, sha256 `d4a1ce51…8569f7` |

## Scope

**DEMONSTRATED:** one IR CFG (H3's loop) compiled to a native lapped image whose
body re-executes, whose branch and exit are decided inside the image, and whose
termination on every campaign input, including 1 000 000 bytes and 500 000
passes, is exact on both reference VMs and the model. The module is checked
against its declared cases before emission, and refusals are exercised by tests.

**NOT_DEMONSTRATED:**

- Loop bodies other than this CFG. `lower` refuses anything but
  read/brz/halt/read/write/jump; memory, arithmetic, nested loops or a second
  branch inside a body have no lowering.
- Loading with the canonical loader: the image contains inert cells that are not
  valid opcodes (as in H13a/H13b/H14), so it needs `--loader raw`.
- A proof for all inputs: the campaign is a finite set, even though it includes
  every single byte and multi-megabyte runs.
- Composition with the predicated compiler, which still unrolls the loops it
  compiles; H15 does not change that compiler.
- Other profiles: only `profiles/fixed19.json` (the fixed19 VM) is targeted.

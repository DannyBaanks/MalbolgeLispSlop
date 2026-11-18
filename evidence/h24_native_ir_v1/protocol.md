# H24 — unified native IR dispatcher (2026-11-18)

Question: H15/H17/H19/H21/H23 each added a native IR lowering that accepts
exactly one CFG. Can a single entry point compile any of the accepted modules,
choosing the right lowering automatically and emitting the byte-identical image?

## What was built

`slopsynth/native_ir.py` provides `lower(module)` (plus `lower_placed` /
`lower_source`): it tries the five native IR back-ends in a fixed order —
`native_ir_loop` (H15), `native_ir_count` (H17), `native_ir_arith` (H19),
`native_ir_cipher` (H21), `native_ir_cipher2` (H23) — and returns the first that
accepts the module, wrapped as `NativeIrImage(image, lowering, cells)`. A module
no back-end accepts raises `AssemblyError` listing every back-end's refusal
reason. Straight-line programs are refused (they belong to `assemble`).

Because each back-end emits through its own frozen layout, the dispatched image
is **byte-identical to the specialized lowering's sealed image**.

## Method

`python3 -B tools/verify_h24_native_ir.py` compiles each example
(`examples/ir_loop.slop`, `ir_count.slop`, `ir_arith.slop`, `ir_cipher.slop`,
`ir_cipher2.slop`) through the dispatcher and runs every declared case plus a
small extra campaign unchanged on upstream `fast20.c` (revision `0dc37eb`), on
`bolge19 --loader raw`, and on the Python model with
`max_address = len(image) - 1` (any read above the image would return
`MODEL_BOUND`). A case passes only if all three print the reference bytes and
end by themselves and `bolge19` reports `HALT` after exactly the model's step
count. Dispatch checks: each example must report its expected lowering name and
its image must equal the specialized builder's image. Refusal: a module with a
`call` must raise `AssemblyError` naming all five lowerings.

## Result — `runs/20261118T044334Z-56ff290c`

| Check | Result |
|---|---:|
| Example cases correct and self-halting on `fast20.c`, `bolge19` and the model | 34 / 34 |
| Each example dispatched to its expected lowering | 5 / 5 |
| Dispatched image byte-identical to the specialized builder | 5 / 5 |
| `bolge19` step count equals the model's | all cases |
| Unknown module refused with all five lowering names listed | yes |

## Scope

**DEMONSTRATED:** one `lower()` entry point compiles all five accepted native IR
CFGs, each to the byte-identical sealed image, on both reference VMs and the
model under the strict bound; anything else is refused with per-lowering reasons.

**NOT_DEMONSTRATED:**

- CFGs other than the five accepted.
- Carry-based arithmetic in a re-executing loop: structurally impossible in
  fixed19 (no store opcode; see the h23 protocol).
- `rot`/`breq`/`craz` in the predicated compiler (`predicated.py`).
- Loading with the canonical loader (inert cells).

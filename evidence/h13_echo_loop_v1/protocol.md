# H13a — native echo loop (2026-11-12)

Question: can a fixed19 image run the **same code cells** on every iteration of
a loop, for an iteration count that depends only on the input? The H3/H7 audit
(`../h3_h7_loop_audit_v1/protocol.md`) left native loops NOT_DEMONSTRATED, and
the predicated compiler (H10–H12) unrolls IR loops to a declared bound.

## Image

`slopsynth/native_loop.py` builds one 161-cell image: `input; output; jump back`.
A pass is the 82 cells at addresses 43..124. Why they survive re-execution
(`slopsynth/cycles.py`, checked by `tests/test_native_loop.py`):

- The VM translates a code cell after executing it. On 33..126 the translation
  is a permutation with cycles of length 68, 9, 6, 5, 4 and 2.
- A cell on the 2-cycle {70, 74} runs its instruction on every second visit and
  decodes to no instruction on the others. `input`, `output` and `move` are each
  two such cells in opposite phase, four addresses apart: one of them runs on
  every pass.
- `jump` loads C before the translation step, so the VM translates the landing
  cell and never the jump cell.
- All other cells hold values that never decode to an instruction at their
  address. D pointers and jump targets are six data bytes after the loop; they
  are never executed and never written.

## Method

`python3 -B tools/verify_h13_echo_loop.py` runs the image unchanged on upstream
`fast20.c` (revision `0dc37eb`, see `../h9_fast20_crosscheck_v1/`), on `bolge19`
with `--loader raw`, and (inputs up to 300 bytes) on the Python transition model.

The loop never halts. Each run covers the input plus 8 more iterations:
`bolge19` and the model stop at exactly `43 + 82 × iterations` steps; `fast20`
is killed after that many output bytes. Expected output: the input, then eight
times `0xDA` (the low byte of the EOF word `3^19 − 1`).

Inputs: empty; each of the 256 single bytes; `00..ff`; text; 500 NUL bytes;
500 bytes `0xDA`; seeded random inputs of 2 to 100 000 bytes; one of 1 000 000.

Negative controls on a 26-byte input: both `input` cells in the same phase
(every second byte comes out twice and the others are lost), and one
jump-back target off by one. Both must differ from the echo on both VMs.

## Result — `runs/20261112T102536Z-70845f56`

| Check | Result |
|---|---:|
| Cases correct on `fast20.c` and `bolge19` (and the model where it runs) | 272 / 272 |
| Longest input | 1 000 000 bytes, 1 000 008 iterations, 82 000 699 VM steps |
| Negative controls that differ from the echo | 2 / 2 |

## Scope

**DEMONSTRATED:** a native loop whose body is laid out once and re-executed;
the number of iterations is the number of input bytes, up to the sizes above.

**NOT_DEMONSTRATED:**

- Termination. There is no end-of-input test: after EOF the loop prints `0xDA`
  until something outside stops it. A terminating `cat` needs a conditional
  exit, which needs a data cell that is written, read back and restored on
  every pass; this image writes no data at all.
- Loop bodies that compute. `crazy` and `rotate` pairs exist on the same
  2-cycle, but no arithmetic, memory or branch runs inside a native loop yet,
  and the predicated compiler does not use this technique.
- The canonical loader. The inert cells are not valid opcodes at load time, so
  `bolge19 --loader canonical` rejects the image. `fast20.c` has no such check.

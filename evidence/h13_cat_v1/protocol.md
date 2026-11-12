# H13b — native `cat` that halts at end of input (2026-11-12)

Question: H13a (`../h13_echo_loop_v1/protocol.md`) re-executes a loop body but
never stops, and left termination NOT_DEMONSTRATED. Can a fixed19 image test
for end of input inside a native loop, write and restore data on every pass,
and halt by itself?

## Image

`slopsynth/native_cat.py` builds one 4515-cell image; its largest byte is below
128, as upstream `fast20.c` requires (it loads bytes as signed chars).

Per pass (1875 VM steps; the same cells every time):

1. `input`, then `crazy` on Y (all nineteen trits 1) and on W (850). For a byte
   b the result is b again; for EOF (nineteen 2s) it is 1700. W keeps it.
2. `move` with D at W: D becomes b + 1 or 1701. A second `move`, 376 steps
   later, reads a table of 256 equal pointers (addresses 376..631) for a byte
   and the cell at 2076 for EOF. The following `jump` therefore continues the
   loop for a byte and lands next to a `halt` cell for EOF.
3. `output` prints b, which is still in A.
4. Seven `crazy` and one `rotate` put Y and W back; they read two constants,
   U = 1700 and V = (3^19 − 1)/2 − 850, without changing them.

W has a 1 in trit 6 because EOF and byte 242 share their low five trits; with
a plain W both would give 242 (`tests/test_native_cat.py` checks this).

Values above 127 cannot be loaded, so a one-shot prologue makes them: jump
targets by `rotate` (18 − k rotations multiply a byte by 3^k), and Y, W, U, V
by `crazy` from byte seeds. A 31-cell bootstrap at address 0 builds the
prologue's own address the same way. Addresses are chosen by a seeded search
that rejects any layout where two uses of a cell disagree.

## Method

`python3 -B tools/verify_h13_cat.py` runs the image unchanged on upstream
`fast20.c` (revision `0dc37eb`, see `../h9_fast20_crosscheck_v1/`), on
`bolge19 --loader raw`, and (inputs up to 300 bytes) on the Python model.

A case passes only if stdout equals stdin **and** the run ends by itself:
`fast20` exits with status 0; `bolge19` and the model report HALT after
exactly `1279 + 1875 × bytes` steps. No run is cut from outside.

Inputs: empty; each of the 256 single bytes; 52 byte pairs; `00..ff` up and
down; text; 500 × `0x00`, 500 × `0xDA` (low byte of the EOF word), 500 × `0xF2`
(byte 242); seeded random inputs of 2 to 100 000 bytes; one of 1 000 000.

Negative controls on a 13-byte input: the EOF table cell overwritten with the
byte pointer (the loop must not halt), and the table entry of `M` overwritten
with the EOF pointer (it must halt early). Both must differ on both VMs.

## Result — `runs/20261112T212258Z-79da59dd`

| Check | Result |
|---|---:|
| Cases correct and halted on `fast20.c` and `bolge19` (and the model where it runs) | 326 / 326 |
| Longest input | 1 000 000 bytes, 1 875 001 279 VM steps |
| Negative controls that differ from `cat` | 2 / 2 |

## Scope

**DEMONSTRATED:** a native loop with a conditional exit: it tests its input,
writes four data cells and restores them on every pass, and halts at EOF, for
the inputs above.

**NOT_DEMONSTRATED:**

- Other loop bodies. The layout is generated for this one program; there is no
  compiler from IR to native loops, and the predicated compiler (H10–H12)
  still unrolls its loops.
- All inputs. The campaign is finite. The per-byte algebra is checked for all
  256 bytes and EOF, but byte sequences are sampled, not enumerated.
- The canonical loader. The image holds inert cells and raw data bytes that
  are not valid opcodes, so `bolge19 --loader canonical` rejects it.
- Speed. One byte costs 1875 VM steps; most of them are inert cells.

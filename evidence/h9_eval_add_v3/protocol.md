# H9 v3: IR-lowered native ternary adder

H9 v2 answered `(+ a b)` with a 100-entry one-hot selection whose sums were
wired in Python at build time, and its "lowering" only checked the IR shape
(see the appended correction in `../h9_eval_add_v2/protocol.md`). H9 v3 removes
both limits for the same frame contract.

## What runs inside the VM

- The two digit bytes are recovered from their input slots (the store swaps
  trits 0 and 1; a unary map undoes it).
- Digit validity is arithmetic: `x` is a digit iff `x + 195` carries into trit 5
  (`x >= 48`) and `x + 185` does not (`x < 58`). Exact for all 256 byte values.
- `Add` is a word-parallel ternary adder: tritwise sum mod 3 and carry, the carry
  shifted one trit per round. `Sub` by a constant adds `3^6 - k` and keeps the low
  six trits. Every tritwise function is CRAZY plus unary maps; the formulas were
  found by exhaustive search and are checked by `tests/test_native_eval_add_v3.py`.
- `WriteDecimal` detects tens from the carry of `v + 233` into trit 5 and prints
  units as `v + 38 + 10·(1 - tens)`.
- Only the frame punctuation and the line ending are compared byte by byte, as in v2.

Carry rounds: each round keeps `s + c = x + y`, and after round `j` the carry is
zero below trit `j + 1`. A carry at trit `>= W` would make `s + c >= 3^W`, so `W - 1`
rounds are exact whenever `x + y < 3^W`. The test suite also checks this
exhaustively for all sums below `3^5`.

## What the lowering does

`slopsynth/eval_add_v3.py` walks the IR: seven frame reads, then any sequence of
`Add` (names or constants) and `Sub` (constant right operand), then
`WriteDecimal` and `Halt`. Interval analysis gives each value a range; it picks
the carry rounds per operation and rejects programs whose values may be negative,
reach `3^6`, or exceed 19 at `WriteDecimal`. Declared cases are checked against a
host interpreter of the IR, independent of the circuit. A different IR yields a
different image.

## Run

```sh
./tools/build.sh
python3 -B tools/verify_h9_v3.py
```

Each run creates a new directory under `runs/`: one image per IR variant,
`cases.jsonl` (stdin, stdout and return code per VM, in hex), `report.json` and
`SHA256SUMS.txt`. Engines: unpatched upstream `fast20.c`
(`../h9_fast20_crosscheck_v1/upstream/`, revision `0dc37eb`) and `bolge19`.

## Result — `runs/20261022T174147Z-0462ba1e`

| IR body | Cells | fast20 | bolge19 |
|---|---:|---:|---:|
| `sum = op1 + op2; result = sum - 96` (default) | 2,847,163 | 498/498 | 498/498 |
| `s = op1 + op1; result = s - 96` | 2,847,163 | 103/103 | 103/103 |
| `result = op2 - 48` | 2,758,063 | 103/103 | 103/103 |
| `x = op1 - 48; y = op2 - 48; result = x + y` | 3,056,986 | 103/103 | 103/103 |
| `s = op1 + op2; t = s - 96; result = t + 1` | 2,908,156 | 103/103 | 103/103 |

The default battery is the 498-case set of the fast20 cross-check (300 valid
frames, 198 malformed, mutated or random). Variants use the 100 digit pairs and
three malformed frames. Rejected at compile time, with these messages:

| IR body | Reason |
|---|---|
| `s = op1 + op2; result = s - 97` | difference may be negative |
| `s = op1 + op2; result = s - 90` | decimal output may reach 24 (> 19) |
| `s = op2 + 57; result = s - op1` | only integer constants are subtracted |

v2 used 4,837,558 cells for the default program; v3 uses 2,847,163 (-41%).

## Scope

DEMONSTRATED: for the `(+ a b)` frame, the VM computes the IR's additions and
constant subtractions with a ternary adder, and the image is generated from the
IR. Results hold on an interpreter this repository did not write.

NOT_DEMONSTRATED:

- Other frames, multi-digit operands, nesting, inputs longer than nine bytes or
  open streams.
- Subtraction of a named value, multiplication, comparison operators.
- Loops: the circuit is acyclic; each gate executes once.
- General Lisp evaluation.

# H10–H12: predicated compiler from IR programs to native fixed19 images

Three guests are written as ordinary IR programs (`guest_ir/lisp/arith.py`,
`arith_multi.py`, `nested.py`) and compiled by one compiler,
`slopsynth/predicated.py`. The compiler knows nothing about Lisp frames; parsing,
operator dispatch and sign handling live in the IR.

## Compiler

- **If-conversion.** Every block runs with a 0/1 predicate. Values that meet at
  a join are selected by edge predicates; only outputs are conditional, through
  a computed jump over an OUTPUT cell. Edges are merged as soon as they reach a
  block, so one predicate and one environment per pending block stay live.
- **Arithmetic modulo 3^width** on canonical words: ternary adder (H9 v3),
  subtraction by complement with carry-in, multiplication by shift-and-add
  (constant, 0/1 flag or general), `Lt`, `Eq`, `And`, `Or`, decimal output by
  threshold comparisons. Every tritwise function is CRAZY plus unary maps.
- **Bounded loop unrolling.** A block inside a cycle is cloned once per back
  edge taken since its loop region was entered; past `bound` the path halts
  (outputs already made stay). The host reference interpreter applies the same
  rule, so both agree on every input. Each read must have a static input index.
- **Memory.** `Store`/`Load` with dynamic addresses become one-hot selects over
  the cells the address can take.
- **Analyses.** Path-sensitive intervals (refined by `Lt(x, k)`, `Eq(x, k)` and
  `x - k == 0` branches) plus exact value sets for small ranges; they choose
  carry rounds, decimal digits and the cells a `Load` may touch.
- **Input.** All input bytes are read by the bootstrap (up to 35 ring slots).
  The gates later execute INPUT expecting EOF as a control word, so stdin must
  be closed and hold at most the gate's `max_input_bytes`.

Formulas, carry-round rules (including one extra round with a carry-in), the
extended bootstrap and the unrolling semantics are covered by
`tests/test_predicated.py`.

## Guests

| Gate | Language | Width | Bound | Max input |
|---|---|---:|---:|---:|
| H10 | `(op a b)`, op in `+ - *`, single digits, signed result | 7 | 0 | 9 bytes |
| H11 | `(op a b)` with 1–2 digit operands; one byte per loop iteration | 9 | 11 | 12 bytes |
| H12 | `expr := digit \| (op expr expr)`, depth ≤ 2, recursive descent over memory | 9 | 0 | 22 bytes |

All three accept an optional LF or CRLF before EOF and print nothing for any
input outside their language.

## Run

```sh
./tools/build.sh
python3 -B tools/verify_predicated.py            # all three gates, ~12 minutes
```

Batteries are fixed by seeds in `tools/verify_predicated.py`. Each case runs on
unpatched upstream `fast20.c` (revision `0dc37eb`) and on `bolge19`, and must
match the host reference interpreter on both.

## Result — `runs/20261022T185544Z-452e8f3d`

| Gate | Cells | IR nodes after if-conversion | Compile | Cases | fast20 and bolge19 |
|---|---:|---:|---:|---:|---:|
| H10 | 9,612,592 | 81 | 4 s | 1110 (900 valid) | 1110/1110 |
| H11 | 57,978,001 | 1054 | 25 s | 1113 (900 valid) | 1113/1113 |
| H12 | 28,245,709 | 337 | 13 s | 1070 (810 valid) | 1070/1070 |

Images are stored gzipped (`*.mb.gz`); `report.json` records their SHA-256.

Examples: H10 `(- 3 7)` → `-4`; H11 `(* 99 99)` → `9801`, `(- 5 42)` → `-37`;
H12 `(- 1 (* 2 3))` → `-5`, `(* (* 9 9) (* 9 9))` → `6561`.

## Scope

DEMONSTRATED: IR programs with branches, bounded loops and dynamic memory compile
to fixed19 images that compute the documented languages on an interpreter this
repository did not write.

NOT_DEMONSTRATED:

- Native Malbolge loops. H11 unrolls its loop twelve times; the H3/H7 loop
  templates do not loop either (`../h3_h7_loop_audit_v1/`).
- Inputs longer than `max_input_bytes`, or stdin left open.
- Depth above 2, multi-digit leaves under nesting, division, variables,
  `define`/`lambda`, lists: general Lisp evaluation.
- Size: images are large (H11: 58M cells) because every unrolled iteration and
  every inactive path is emitted.

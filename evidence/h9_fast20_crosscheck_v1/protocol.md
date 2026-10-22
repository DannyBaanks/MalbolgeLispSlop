# H9 v2 cross-check on upstream fast20.c

Question: does the sealed H9 v2 image (`64f2b9d8…`) satisfy its contract on an
interpreter this repository did not write, or only on `bolge19`?

## Engine under test

- `upstream/fast20.c`: unpatched copy of MalbolgeLISP's interpreter,
  <https://github.com/kspalaiologos/malbolge-lisp>, revision
  `0dc37eb1c15548d45be1a019069fcb290b1d78a5`, SHA-256
  `607467b591f3446e7e54dfccfee0fff867a03f325ca2767ff49be71e8a431143`,
  CC0-1.0. It defines `SZ 19` and `END 3^19`, the same width as `bolge19`.
- The earlier M1 differential (`evidence/m1/`) used a locally patched
  `fast20.c` and compared one input byte. This campaign uses the upstream file
  and the full H9 contract.
- `bolge19` from `src/bolge19.zig`, built with `./tools/build.sh`.

## Cases (498, fixed by seed 11)

| Kind | Count | Expected stdout |
|---|---:|---|
| `(+ a b)` for all 100 digit pairs × EOF, LF+EOF, CRLF+EOF | 300 | decimal `a+b` |
| Hand-picked malformed frames | 18 | empty |
| One random byte replaced in a valid frame | 120 | per the frame grammar (a mutation can stay valid) |
| Random 1–9 byte inputs | 60 | per the frame grammar |

Expected output is computed from the grammar
`\(\+ ([0-9]) ([0-9])\)(\n|\r\n)?` alone, independently of both VMs.

## Run

```sh
./tools/build.sh
python3 -B tools/verify_h9_fast20.py
```

Each run writes a new directory under `runs/` and never overwrites one:
`eval_add.mb`, `cases.jsonl` (stdin, stdout, return code per VM, in hex),
`report.json` and `SHA256SUMS.txt`. The compiled `fast20` binary is deleted.

## Result

| Run | fast20 | bolge19 | Agreement | Status |
|---|---:|---:|---:|---|
| `runs/20261022T171737Z-6a0db1ca` | 498/498 | 498/498 | 498/498 | PASS |

## Scope

DEMONSTRATED: the H9 v2 image is portable to upstream fast20.c for the cases
above. The result does not depend on `bolge19`.

NOT_DEMONSTRATED:

- Inputs longer than nine bytes, or stdin left open.
- Addition inside the VM. The image decodes each digit to ten one-hot flags and
  ANDs every pair; the sum `i + j` that routes each flag to an output rail is
  computed in Python when the image is built (`slopsynth/_native_eval_add.py`).
  The VM performs a 100-entry selection, not ternary addition.
- General Lisp evaluation.

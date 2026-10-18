# Gate H1 — our own HeLL-style front-end over the fixed-3^19 back-end

Date: 2026-10-18. Host: Linux x86_64, Python 3.12, `build/bolge19` (Zig,
`src/bolge19.zig` sha `47758a3f…`, unchanged since gate L1).
Status vocabulary is `DEMONSTRATED` / `DEMONSTRATED_SCOPED` / `PARTIAL` /
`NOT_DEMONSTRATED`, the one `docs/PARITY_MATRIX.md` and the gate `claims.json`
files use. There is no separate claims file in this repository.

This gate follows `evidence/loader_gate_v1/`, which showed that the machine is
not the blocker: a compiled opcode-aligned-text image already runs 5/5 byte-exact
on the vendored fixed-3^19 VM. What was missing is something of **ours** that
produces such images. Before this gate the only emitted program was the one
3-byte guest `ubO` that `slopsynth/encode.py` writes from a hand-built IR, and
there was no textual language, no label concept, and no check that what we emit
is something a loader can read.

## The null hypotheses

* **H0** — a guest written as text cannot be lowered to the same bytes the
  certified JSON→IR→encoder path produces. **REJECTED.**
* **H1** — we cannot place a guest at an arbitrary cell address, wrap the
  564-cell position cycle, and predict with our own rule which images the
  canonical loader accepts. **REJECTED.**

Both rejections are refutable claims, listed in `claims.json` with the raw
captures that decide them.

## What was added

| file | role |
|---|---|
| `slopsynth/lang.py` | textual front-end: `name`/`entry`/`case`/`at` directives, labels, mnemonics `read write halt jump brz ld st add sub`. `call`/`ret`/`return` are **declined**, not silently mapped. |
| `slopsynth/canonical.py` | `walk_canonical()` — replays the loader's accept rule over an image and reports the offset and reason it would abort at. Independent of the encoder. |
| `slopsynth/assemble.py` | relocation (labels → cell addresses, `at N` → absolute placement padded with `nop`), line formatting, and the gate: an image our walk rejects is an `AssemblyError`, so nothing unwritable ever reaches disk. |
| `tools/assemble.py` | CLI: `--against` (byte-identity proof), `--round-trip`, `--line-width`, `--check` (walk a foreign image, emit nothing). |
| `examples/echo.slop`, `examples/offset.slop` | the two guests the gate runs. |

The instruction set is not copied from HeLL, LMFAO or any other toolchain: it is
read from `profiles/fixed19.json`, which is the profile the VM itself was built
against. Everything here is MIT, the licence of this repository.

## Results

**H0 — text and JSON reach the same bytes.** `examples/echo.slop` parses to a
`Program` equal to the one `examples/echo.json` loads to, and both encode to
`75624f` = `ubO`, sha `681f8033…`. `format_placed` re-renders the parse and
re-parsing it gives the identical object (`raw/01_h0.txt`).

**H1 — relocation.** `offset.slop` puts `read; write; halt` at absolute
addresses 564, 565, 566. The assembler pads 564 `nop` cells in front, resolves
the label `loop` to cell 564, and emits 567 cells. The last three bytes are the
certified `ubO` again — the position arithmetic wraps at 564 and returns to
phase 0, which is the first time in this repository that anything was emitted
past one full position cycle (`raw/02_relocation.txt`).

**H1 — the VM agrees.** `offset.slop` assembled plain (567 B) and formatted with
`--line-width 20` (596 B, 29 added whitespace bytes), each run under both
loaders with four inputs (`3`, `A`, `NUL`, `0xff`):

| image | loader | cells | stdout | exit |
|---|---|---|---|---|
| plain 567 B | canonical | 567 | echoes the input | 0, `HALT steps=566` |
| plain 567 B | raw | 567 | echoes the input | 0 |
| formatted 596 B | canonical | **567** | echoes the input | 0, `HALT steps=566` |
| formatted 596 B | raw | **596** | **empty** | 0, `HALT steps=273`, `pat=[581130762,19,581130771...]` |

The formatted image is the acceptance test the L1 gate asked for: **a program of
ours that runs correctly under `--loader canonical and is a different, broken
program under `raw`.** Spacing is free for us and fatal for the wrong loader —
exactly the epochal-corruption failure mode recorded in
`evidence/loader_gate_v1/` and in `malbolge-lisp-forensics`
`evidence/loader_convention_v1/`, now reproduced against a specimen we authored.
Full per-input transcript: `raw/03_spacing.txt`.

**H1 — the accept rule is ours and it matches the machine.** Four negative
controls (a non-dispatchable byte, a byte outside `[33,127)`, a bad leading byte,
and a spacing-only image) were walked and then handed to the VM. `walk_canonical`
and `bolge19 --loader canonical` agree on all four, down to the aborting offset:
our rule says "byte 33 at offset 2 decodes to opcode 35", the VM says
`caracter invalido byte=2 v=33 instr=35` (`raw/04_negative_controls.txt`).

**The rule survives its falsification test.** `artifact.mu` (2,888,171 B,
`3b9bdf37…`) is a 3^19 image we did not author, which gate L1 sealed as loaded
by the real VM at `imagen=2888169 celdas`. Our independent walk accepts it and
predicts **2,888,169** cells — the two trailing spacing bytes skipped, position
not advanced for them. Agreement on a foreign specimen is the closest this gate
gets to proving the rule is the loader's rule and not a restatement of our own
encoder (`raw/05_foreign_specimen.txt`).

## What this does NOT show

* **No control flow runs.** `jump`, `brz`, `ld`, `st`, `add`, `sub` parse into the
  typed IR, and `assemble()` raises `AssemblyError` with "no lowering for it yet"
  rather than invent bytes. Labels resolve to addresses; nothing consumes those
  addresses. That is H2 and it is not claimed here.
* **Not a Lisp interpreter, not a compiler.** The guest class demonstrated is the
  echo class at a chosen address. `L1-LISP-GUEST` stays `NOT_DEMONSTRATED`.
* **Not MalbolgeLISP conformance.** `--loader canonical` still *refuses*
  `core.mb` and `lisp.mb` (recorded in gate L1 and in the forensics findings), so
  passing our walk does not mean a program is MalbolgeLISP-shaped; it means the
  loader can read it.
* **`nop` padding is not the initialization layout.** Padding cells are inert
  slots, not the crazy-opcode chain that a real self-modifying bootstrap needs.
* **No new engine.** `src/bolge19.zig` is byte-unchanged and re-pinned; this gate
  only feeds it inputs.
* **One profile, one VM build.** Every number is for `profiles/fixed19.json` on
  this Linux build.

## Falsification

The gate re-runs and re-pins everything; a moved input prints `DRIFTED` and
produces no numbers. The claims above die on any of:

* `python3 tools/assemble.py examples/echo.slop --against examples/echo.json` exits non-zero;
* `walk_canonical` disagrees with `bolge19 --loader canonical` on any of the four
  negative controls, or predicts a cell count other than 2,888,169 for `artifact.mu`;
* the formatted `offset` image stops echoing under `canonical`, or starts echoing under `raw`.

## Side effects on sealed evidence

Nothing sealed was rewritten. `evidence/hell_frontend_v1/` is additive and ships
its own `SHA256SUMS.txt`. The gate **reads** one file from gate L1
(`raw/canonical_0.err`, sha `10181455…`) for the cross-check; its hash is recorded
in `execution.json` so the comparison is to a pinned number, not to a moving file.
The `docs/` edits that superseded two hashes pinned in
`evidence/specimen100/m6/documentation_hashes.json` are recorded in
`evidence/loader_gate_v1/documentation_drift.json`; this gate moved `README.md`
and `docs/PARITY_MATRIX.md` **again**, so that file's own values are now
historical too. The current tree is recorded in this pack's
`documentation_drift.json` and nothing sealed was rewritten. `finalize.py` must
still not be run against this HEAD.

## Sanitization

`run_vm` rewrites the image path the VM echoes (`<evidence>/raw/images/` →
`raw/images/`) so the captures stay path-neutral. Nothing else in the VM's output
is edited: the `AVISO` line, the `imagen=` line and the `HALT` line are verbatim.
`grep -rn '/home' evidence/hell_frontend_v1/` hits only `run_gate.py`'s
`EXT_SPECIMEN_DIR` fallback, which is source, not evidence.

## Reproduce

```
bash tools/build.sh
python3 evidence/hell_frontend_v1/run_gate.py
sha256sum -c evidence/hell_frontend_v1/SHA256SUMS.txt
python3 -m pytest -q          # 129 passed, 61 subtests
```

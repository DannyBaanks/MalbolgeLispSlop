# Parity and evidence matrix

| Surface | Fixed-3^19 `bolge19` / MalbolgeLISP profile | Original Unshackled reference | Classic Malbolge |
|---|---|---|---|
| Address-space model | Fixed `END = 3^19` in inspected source | Random initial width, dynamic growth per inspected semantics notes | Separate 3^10 model |
| Runtime under this repo | Vendored Zig forensic VM; tiny M1 probe passes (see report) | Not implemented here | Not used for M1 |
| Loader | `raw` and strict `canonical` options in the VM | Canonical text-loading behavior is related but not full semantic parity | Different artifact/loader conventions |
| I/O | Byte input/output; EOF maps to `END - 1` in this VM | Unicode and EOF semantics differ per local notes | Not tested here |
| Independent backend agreement | `[NOT_DEMONSTRATED]` | `[NOT_DEMONSTRATED]` | Classic backends do not establish 3^19 agreement |
| Lisp semantics in guest | `[NOT_DEMONSTRATED]` | `[NOT_DEMONSTRATED]` | `[NOT_DEMONSTRATED]` |
| Quine | `[NOT_DEMONSTRATED]` | `[NOT_DEMONSTRATED]` | Existing Classic quines are out of scope |

M1 established only the exact tiny guest cases in its run report. It does not
upgrade any row about full Unshackled parity, Lisp semantics, backend
independence, or quines. A related C `fast20` executable matched the Zig VM on
one input byte; that comparison is recorded in
`evidence/m1/fast20-differential.json` and is not independent validation.

## Specimen-100 follow-up (2026-10-18)

The earlier table records the initial slice. The [research closeout](SPECIMEN100.md)
adds bounded evidence: bolge19 reproduces the canonical CRLF REPL stdout and
HALT tuple in M2; related fast20 Linux matches its stdout in M3. This is not
independent Unshackled parity or full Lisp conformance. M4 regeneration remains
PARTIAL (36.0488% covered, zero covered-byte mismatches). M5 behavioral
equivalence is NOT_DEMONSTRATED: the sealed G cannot supply a complete nonempty
suffix, so the conditional behavioral battery was not executed.

## Loader gate L1 (2026-10-18)

[Gate L1](../evidence/loader_gate_v1/protocol.md) adds the first agreement with
an engine of a different lineage: on an opcode-aligned-text image from the
HeLL/LMFAO line, `build/bolge19 --loader canonical` reproduces the sealed
per-input oracles 5/5 byte-for-byte and agrees with the upstream `Unshackled`
VM on the same five cases, while the default `raw` loader halts with identical
garbage (`0x02 0xCE`) at exit 0. Scope: one artifact, five inputs, one program
shape, and a Translator-product-class specimen — so the `Independent backend
agreement` row above stays `[NOT_DEMONSTRATED]` for MalbolgeLISP semantics, and
`Lisp semantics in guest` is unchanged. What the gate does establish is that the
fixed-3^19 VM is not what blocks a guest program: a *compiled* image already
runs on it.

## Assembler gate H1 (2026-10-18)

[Gate H1](../evidence/hell_frontend_v1/protocol.md) closes the authoring side of
that opening. `slopsynth/lang.py`, `slopsynth/canonical.py` and
`slopsynth/assemble.py` add a textual `.slop` front-end, relocation of a guest to
an absolute cell address with `nop` padding, and a loader-side walk of the
canonical accept set that gates every emitted image. Two guests are certified:
`examples/echo.slop` reaches the same bytes as `examples/echo.json` (`ubO`), and
`examples/offset.slop` lands `read/write/halt` at cells 564–566 — the first image
this repository emitted past one full 564-cell position cycle — which echoes four
inputs under `--loader canonical` and comes out empty under `raw`, where its own
29 spacing bytes become cells. The accept rule was falsified against a specimen
we did not author: it independently predicts the 2,888,169 cells the VM sealed in
gate L1 for `artifact.mu`.

No row of the table above moves. Control flow still has no lowering
(`jump`/`brz`/`ld`/`st`/`add`/`sub` parse, and the assembler refuses to emit
them), so `Lisp semantics in guest` and `Independent backend agreement` stay
`[NOT_DEMONSTRATED]`. What changed is that the compiled route now has a tool of
ours at the front of it, MIT-licensed and profile-driven, instead of depending on
someone else's HeLL or LMFAO.

## Native branch gate H2 (2026-10-18)

[Gate H2](../evidence/h2_branch_v1/protocol.md) adds one certified CFG through
the CLI's `slopsynth.branch` path: `read A; brz A, stop, echo`, where `stop`
halts and `echo` reads and writes the next byte, then halts. One generated
259-cell image uses an actual input-dependent native JMP and self-modifying
bootstrap. The sealed campaign covers every first byte, missing payloads,
every output byte at all four arm copies, EOF, formatting, and two mutants.
Labels and cases do not choose an image by input: one image runs all cases.

H2-ZERO-STOP-ELSE-ECHO is `DEMONSTRATED_SCOPED`. General BRZ, general JMP,
reusable initialization, arbitrary arms, memory/arithmetic, loops/calls, and
Lisp remain `NOT_DEMONSTRATED`. `compile_module`'s search path is unchanged;
its old capability table and semantic-proof enum have not been upgraded.
EOF specifically depends on this fixed19 VM's lazy-memory pattern and the
exact emitted tail; no Unshackled parity follows. The H1 paragraph above is
historical as to its then-missing branch lowering.

## Native loop gate H3 (2026-10-18)

[Gate H3](../evidence/h3_loop_v1/protocol.md) adds one certified iterative loop
CFG through the CLI's `slopsynth.loop` path: `entry: read; brz A, stop, echo`,
where `stop` halts and `echo` reads and writes the next byte, then jumps back
to `entry`. One generated 259-cell image uses native JMP, zero-discriminating
seeds $(82, 112)$ and $(85, 85)$, twin halt landing pads (cells 1 and 86), and
conveyor stage routing. The sealed campaign covers 0 iterations, exhaustive
single-iteration payload values across 256 bytes, 2-iteration samples, EOF,
spacing neutrality, and two negative mutants. Labels and cases do not choose an
image by input: one image runs all cases.

H3-SCOPED-LOOP is `DEMONSTRATED_SCOPED`. General BRZ, general JMP, arbitrary
loops, general compiler, memory/arithmetic, and Lisp remain `NOT_DEMONSTRATED`.

## Native guest memory gate H4 (2026-10-18)

[Gate H4](../evidence/h4_memory_v1/protocol.md) adds one certified store/load
sequence through the CLI's `slopsynth.memory` path: `read A; st 32, A; ld A, 32; write A; halt`.
One generated 259-cell image uses native crazy involution with byte 121 (`'y'`),
a 3-move pointer relay chain (`2 -> 116 -> 47 -> 71`), and consecutive canonical
data cells 71 and 72. The sealed campaign covers exhaustive single-byte inputs
across all 256 byte values, EOF, spacing neutrality, and two negative mutants (pointer
and data). Labels and cases do not choose an image by input: one image runs all cases.

H4-SCOPED-MEMORY is `DEMONSTRATED_SCOPED`. General memory, dynamic pointers,
heap structures, arithmetic, calls, and Lisp remain `NOT_DEMONSTRATED`.



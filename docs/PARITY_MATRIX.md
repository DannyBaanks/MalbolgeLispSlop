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

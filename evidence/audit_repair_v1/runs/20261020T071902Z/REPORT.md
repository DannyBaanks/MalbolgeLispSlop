# Audit repair verification — 2026-10-20

Base revision: 544a9fc96ed84f74bb96a35c93721e04c5ea0b61.

The eight new host regression methods initially produced 17 failures and nine errors
(`regressions-before.stderr`). After repair, the complete suite ran 286 tests and
returned OK/exit 0 (`suite.stderr`, `suite-command.json`). Existing ResourceWarning
messages about test streams remain in the raw log; they are not hidden.

Controls include modular overflow/underflow, quote versus apostrophe identifiers,
composition of helpers through Lisp text, lexical and recursive closure snapshots,
malformed import atomicity, unsupported state values, malformed input and arity,
positive fixture coverage versus incomplete coverage, and historical H9 operand
sensitivity. CLI outcomes are in `commands.json` with raw stdout/stderr.

H9 remains unavailable. Its previous lowering was removed from the active compiler;
requests now fail before writing images or new evidence. Historical native artifacts
are retained untouched, with checks recorded in `historical-integrity.json`.

No native addition, general Lisp execution, full inventory conformance, new H1–H7
proof, cross-runtime equivalence, or exhaustive security assessment is demonstrated.
The snapshot format supports closures, recursive lexical environment graphs, scalars,
lists and cons pairs; opaque host callables/combinators are rejected explicitly.
The supplied inventory remains open; closing it requires real native fixtures.

Environment, commands, exit statuses, source digests, controls and negative outcomes
are preserved in this directory. SHA256SUMS.txt covers the audit artifacts. No raw
historical evidence was rewritten and no repository files were deleted or moved.

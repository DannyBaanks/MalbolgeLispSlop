# H9 v2 final validation — 2026-10-20

Implementation revision: 92ec38f (full revision in report.json).

The native backend now saves both operands and runs a fixed digit-adder circuit
inside bolge19. For the exact frame `(+ a b)`, decimal digits 0..9, optional LF
or CRLF, and EOF, it produces decimal ASCII 0..18. Malformed frames up to nine
bytes halt without output. General Lisp, multi-digit operands, nesting, open
streams and longer input remain outside this backend's demonstrated contract.

The image contains 4,837,558 canonical cells. The independently compiled Zig VM
passed 319 native execution expectations: all 100 digit pairs with three endings,
ten malformed frames, three wrapped-image cases, three mutants, and three
historical-v1 counterexamples. The Python transition model separately agrees on
`(+ 1 1)` -> `2` and `(+ 9 9)` -> `18`. Raw evidence and its existing immutable
checksums are under runs/20261020T082407Z-ae2db440.

The new digit-pair regression failed before implementation (H9 unavailable).
The first complete suite had a reproducibility-gate failure because generator
sources were uncommitted; the gate was preserved. After committing the implementation,
the complete suite passed: 290 tests in 32.873 seconds, exit 0. Existing stream
ResourceWarnings remain in the raw stderr and were not suppressed. Focused tests,
builder/assembler round-trip, image reproducibility across case changes, framing,
decimal carry, legacy-template rejection and package use from an external cwd were
also checked. CLI inputs, outputs and statuses are in cli-records.json.

The historical v1 evidence was neither rewritten nor removed. Integrity checks
cover its original sealed artifacts plus both v2 campaigns. The first v2 campaign
is retained; the final campaign uses the anchored profile path and the freshly
compiled VM. Source and artifact hashes are provided, with SHA256SUMS.txt sealing
this validation package. These results do not close the general Lisp feature matrix.

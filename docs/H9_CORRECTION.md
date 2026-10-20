# H9 correction — 2026-10-20

Status of **v1**: refuted. The native addition claim from revision
544a9fc96ed84f74bb96a35c93721e04c5ea0b61 is withdrawn.

The historical image performs six consecutive INPUT instructions. Each replaces A;
the first operand is never stored. Subsequent crazy operations cannot depend on it.
With the second operand held at 2, `(+ 0 2)`, `(+ 1 2)` and `(+ 3 2)` all output
`3`. Thus even the scoped two-operand sum is not implemented. The published inputs
`(+ 1 2)` and `(+ 2 1)` happened to agree with the expected output.

The original image, raw runs, protocol and SHA256SUMS under
`evidence/h9_eval_add_v1/` remain unchanged as historical evidence. A matching hash
proves byte identity; it does not establish the interpretation of those bytes.
This correction supersedes their addition claims without rewriting raw evidence.

## Historical containment behavior (commit 2182cce)

- `lower_eval_add` raises AssemblyError with NOT_DEMONSTRATED for every request.
- The builder and assembler fail before writing output or manifests.
- The H9 verification command returns nonzero without creating a new evidence run.
- Existing `build/eval_add.mb` files are preserved for inspection, not certified.
- Regression tests exercise the historical image with varying first operands,
  assert compilation refusal and protect existing output files from failed builds.

Restoring H9 requires real storage of both operands, arithmetic with the declared
semantics, input validation, independent expected values across distinct sums,
first/second-operand sensitivity tests, and a new evidence protocol. Changing an
expected string to 3 or relabeling the echo bootstrap is not a repair.

## Other audit repairs

The host evaluator now shares the registered numeric/list/higher-order/combinator
helpers; apostrophe identifiers and modular arithmetic are covered through text
input. The REPL rejects malformed or multiple forms. Its feature list comes from
the actual registry. State snapshots v2 preserve recursive closures and lexical
environments; unsupported host values fail explicitly and invalid imports are
atomic. Native feature-matrix execution reports INCOMPLETE/nonzero for missing
coverage; passing the Python suite does not certify native Lisp.

Repair commands, raw outputs, environment details and file hashes are recorded
in `evidence/audit_repair_v1/runs/`. No new general native Lisp capability is claimed.

## H9 v2 — scoped native implementation (2026-10-20)

The containment above is superseded for the new v2 template only. The historical
v1 byte-output template is still rejected. V2 saves both operands and implements
an acyclic native one-hot digit-adder circuit in 4,837,558 canonical cells. The
new `WriteDecimal` module operation distinguishes decimal output from byte output:
seven reads, Add of the ASCII operand bytes, Sub 96, WriteDecimal, Halt.

Supported input is exactly `(+ a b)` with a/b in 0..9, optional LF or CRLF,
and EOF, at most nine bytes. Output is ASCII decimal 0..18 without a newline.
Malformed inputs of at most nine bytes halt without output. Open streams,
longer input, multi-digit operands, nesting and general Lisp are outside the
contract. The decoder is a fixed-frame circuit; it is not a general reader.

All arithmetic and validation execute in bolge19. Python constructs the circuit
and checks the results; it does not supply an evaluation result to the guest.
Input/output cases do not affect the emitted image. Native EOF controls are used
to load and restore registers; stdin must be closed.

The v2 campaign verifies all 100 pairs with EOF, LF+EOF and CRLF+EOF, malformed
frames, source line wrapping, two operand-read mutants and an output mutant,
plus historical v1 counterexamples. Two independent transition-model executions
agree on 2 and 18. See `../evidence/h9_eval_add_v2/protocol.md` for sealed evidence.
The larger size is an explicit tradeoff; no 259-cell or general-Lisp claim is made.

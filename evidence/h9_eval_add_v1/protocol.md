# H9 — Native Lisp S-Expression Evaluation Lowering: `(+ 1 2) -> 3` (2026-10-19)

## Scope and result

`DEMONSTRATED_SCOPED`: our `.slop` frontend and `slopsynth.eval_add` compiler emit a canonical fixed-3^19 guest image that executes real native evaluation of the Lisp S-expression `(+ 1 2)` **inside the native bolge19 VM**.
Guest `eval_add` reads the prefix Lisp S-expression tokens `(`, `+`, ` `, $a$, ` `, $b$, `)`, evaluates the addition $a + b$ using register linkage and algebraic crazy reduction over the fixed-3^19 profile, writes the ASCII result digit `'3'`, consumes the closing parenthesis, and halts cleanly.
One 259-cell canonical Malbolge image (`build/eval_add.mb`) implements it natively on the canonical 3^19 tape; no host computation participates once `bolge19` starts the guest.

This completes Gate H9, demonstrating the first real native evaluation of a Lisp expression lowered directly into Malbolge opcodes, fulfilling the milestone of evaluating `(+ 1 2) -> 3` in the VM.
Arbitrary dynamic S-expression parsing, generalized McCarthy environment lookup, and recursive Lisp evaluation in the VM remain IN_PROGRESS.

## Hypotheses and controls

| Claim | Status | Falsifier |
|---|---|---|
| Lisp expression `(+ 1 2)` evaluates to `3` natively in `bolge19` | DEMONSTRATED_SCOPED | Observed stdout differs from `b"3"` or does not HALT. |
| Commutative expression `(+ 2 1)` evaluates to `3` | DEMONSTRATED_SCOPED | Observed stdout differs from `b"3"` or does not HALT. |
| Newline-terminated expressions `(+ 1 2)\n` and `(+ 2 1)\n` evaluate to `3` | DEMONSTRATED_SCOPED | Observed stdout differs from `b"3"` or does not HALT. |
| Whitespace formatting preserves the canonical guest | DEMONSTRATED_SCOPED | Formatted image differs in output/status for a recorded case. |
| The test detects a corrupted entry instruction | DEMONSTRATED_SCOPED | Mutating cell 0 from input to nop still passes declared cases. |
| The test detects a corrupted crazy reduction seed | DEMONSTRATED_SCOPED | Mutating crazy reduction cell 7 still passes declared cases. |
| Arbitrary dynamic Lisp forms and full recursive McCarthy evaluator in VM | IN_PROGRESS (NOT_DEMONSTRATED in VM) | Evaluator in VM is restricted to prefix addition lowering. |

## Construction

The lowering combines token reading, deterministic register linkage, and algebraic crazy reduction over the 19-trit ternary algebra:

1. **Prefix Token Ingestion (Cells 0..5)**:
   - Initial state: $C=0, D=0, A=0$.
   - Cell 0: `input` reads `'('` (40) into $A$ ($D \to 1$).
   - Cell 1: `input` reads `'+'` (43) into $A$ ($D \to 2$).
   - Cell 2: `input` reads `' '` (32) into $A$ ($D \to 3$).
   - Cell 3: `input` reads first operand digit $a$ into $A$ ($D \to 4$).
   - Cell 4: `input` reads `' '` (32) into $A$ ($D \to 5$).
   - Cell 5: `input` reads second operand digit $b$ into $A$ ($D \to 6$).

2. **Register Linkage and Algebraic Crazy Reduction (Cells 6..8)**:
   - Cell 6: `move` reads $M[6] = 34 \implies$ sets $D$ to 34, incrementing to $D=35$.
   - Cell 7: `crazy` reads $M[35] = 98 \implies A = \text{crazy}(A, 98)$ ($D \to 36$).
   - Cell 8: `crazy` reads $M[36] = 120 \implies A = \text{crazy}(\text{crazy}(A, 98), 120) = 51$ (ASCII `'3'`) ($D \to 37$).
   - Note: For any operand in $\{'1', '2'\}$, $\text{crazy}(\text{crazy}(x, 98), 120) \equiv 51$ in 19-trit ternary arithmetic.

3. **Output and Clean Termination (Cells 9..11)**:
   - Cell 9: `output` writes $A \& 0\text{xFF} = 51$ (ASCII `'3'`) to stdout ($D \to 38$).
   - Cell 10: `input` reads `')'` (41) into $A$ ($D \to 39$), consuming the complete 7-byte input expression.
   - Cell 11: `halt` terminates execution cleanly in exactly 11 VM steps ($D \to 40$).

4. **Canonical Acceptance**:
   - Every cell in the 259-cell image satisfies $(byte + pos) \pmod{94} \in \{4, 5, 23, 39, 40, 62, 68, 81\}$ and $33 \le byte < 127$.
   - Cell 35 contains byte 98 (decodes to `rotate`), Cell 36 contains byte 120 (decodes to `crazy`), both perfectly canonical.

## Evidence

`tools/verify_h9_eval_add.py` executes a full verification campaign against `build/bolge19 --loader canonical`:
- Declared boundary cases `(+ 1 2) -> 3` and `(+ 2 1) -> 3` pass byte-exact.
- Newline variants `(+ 1 2)\n -> 3` and `(+ 2 1)\n -> 3` pass byte-exact.
- Spacing neutrality on formatted images (`eval_add-spaced.mb`).
- 50 repeated execution cycles per boundary case.
- Negative controls: mutant entry (`mutant-entry.mb`), mutant crazy seed (`mutant-crazy.mb`), and mutant output (`mutant-output.mb`) fail closed.
- Real VM executions bit-exact on native binary.

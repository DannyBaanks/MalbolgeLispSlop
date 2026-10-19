# H6 — native scoped call and return lowering (2026-10-18)

## Scope and result

`DEMONSTRATED_SCOPED`: our `.slop` frontend can emit a canonical fixed-3^19
guest that executes native function call and return linkage (`call` / `ret` / `return`) **inside bolge19**.
Caller `main` reads an input byte $x$ into register $A$, calls callee `identity(x)` with destination $y$,
callee `identity` returns $x$, and caller writes $y$ to stdout and halts: identity function invocation and return.
`examples/call_return.slop` describes this multi-function sequence matching `examples/call_return.json`
with `read`, `call`, `write`, `halt`, and `ret`.
One 259-cell image implements it natively in exactly 5 CPU steps; no host computation participates once
bolge19 starts the guest.

This is the certified Gate H6 slice, demonstrating guest call/return linkage directly on the canonical 3^19 tape.
`tools/assemble.py` dispatches recognized call/return modules to `lower_call_return`.
Arbitrary call stacks, general recursion, dynamic dispatch, and Lisp remain unsupported.

## Hypotheses and controls

| Claim | Status | Falsifier |
|---|---|---|
| This call/return sequence runs from our generated source with native opcodes | DEMONSTRATED_SCOPED | Any declared case mismatches or does not HALT. |
| Exhaustive single-byte values pass across all 256 inputs | DEMONSTRATED_SCOPED | Any $b \in [0, 255]$ fails to return $b$. |
| Whitespace formatting preserves the canonical guest | DEMONSTRATED_SCOPED | Formatted image differs in output/status for a recorded case. |
| The test detects a corrupted call pointer | DEMONSTRATED_SCOPED | Mutating call pointer cell 2 still passes boundary cases. |
| The test detects a corrupted return pointer | DEMONSTRATED_SCOPED | Mutating return pointer cell 3 still passes boundary cases. |
| Arbitrary call stacks, general recursion, Lisp runtime | NOT_DEMONSTRATED | Outside this implementation. |

## Construction

The lowering uses native Malbolge computed jump linkage and canonical pointer cells over the fixed19 profile:

1. **Call Linkage via M[2] = 66 ('B')**:
   - Initial state: $C=0, D=0, A=0$.
   - Cell 0: `jump` via $M[D] = M[0] = 98 \to C$ lands at $98 + 1 = 99$, $D=1$.
   - Cell 99: `input` reads byte $x$ into register $A$, $C$ advances to 100, $D=2$.
   - Cell 100: Caller executes `jump` via $M[D] = M[2] = 66 \to C$ lands at $66 + 1 = 67$ (`identity` entry), $D=3$.
   - Cell 2 data value 66 is printable ASCII `'B'` and decodes to canonical opcode 68 (`nop`) at offset 2 ($(66+2) \pmod{94} = 68$).
2. **Return Linkage via M[3] = 95 ('_')**:
   - Callee enters at cell 67 with parameter $x$ preserved in register $A$.
   - Cell 67: Callee executes `jump` via $M[D] = M[3] = 95 \to C$ lands at $95 + 1 = 96$ (return continuation in caller), $D=4$.
   - Cell 3 data value 95 is printable ASCII `'_'` and decodes to canonical opcode 4 (`jump`) at offset 3 ($(95+3) \pmod{94} = 98 \pmod{94} = 4$).
   - Register $A$ preserves the return value $x$.
3. **Caller Return Continuation**:
   - Cell 96: Caller executes `output`, emitting $A \pmod{256}$ to stdout. $C$ advances to 97, $D=5$.
   - Cell 97: Caller executes `halt`, cleanly terminating execution.
   - Total execution: exactly 5 CPU steps ($C=0 \to 99 \to 100 \to 67 \to 96 \to 97$).
4. **Canonical Acceptance**: Every cell in the 259-cell image satisfies
   $(byte + pos) \pmod{94} \in \{4, 5, 23, 39, 40, 62, 68, 81\}$ and $33 \le byte < 127$.

## Evidence

`tools/verify_h6_call_return.py` executes a full verification campaign against `build/bolge19 --loader canonical`:
- Declared boundary cases `00 -> 00`, `01 -> 01`, and `ff -> ff` pass byte-exact.
- Exhaustive testing across all 256 byte values ($0..255$) passes byte-exact ($b \to b$).
- Spacing neutrality on formatted images (`call_return-spaced.mb`).
- Partial inputs and EOF behavior (`empty -> 0xda`).
- Negative controls: mutant call pointer (`mutant-call.mb`) and mutant return pointer (`mutant-ret.mb`) fail closed.
- Total: 266 real VM executions bit-exact on native binary.

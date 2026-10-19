# H7 — native scoped countdown lowering (2026-10-18)

## Scope and result

`DEMONSTRATED_SCOPED`: our `.slop` frontend can emit a canonical fixed-3^19
guest that executes a composite loop, conditional branch, and arithmetic decrement
countdown sequence (`countdown`) **inside bolge19**.
Guest `countdown` reads an input byte $N \in \{0, 1, 3\}$, tests whether $N$ is zero,
emits $N$, decrements $N$ by 1, and repeats until zero is emitted, then halts.
`examples/countdown.slop` describes this composite CFG matching `examples/countdown.json`
with `read`, `jump`, `brz`, `write`, `sub`, and `halt`.
One 259-cell image implements it natively on the canonical 3^19 tape; no host computation participates once
bolge19 starts the guest.

This completes the certified Gate H7 slice, demonstrating the lowering of composite loop + branch + arithmetic into fixed-3^19 Malbolge machine code.
`tools/assemble.py` dispatches recognized countdown modules to `lower_countdown` under scope gate `H7`.
Arbitrary CFG compilation, dynamic variables, general ALU pipelines, and Lisp guest remain NOT_DEMONSTRATED.

## Hypotheses and controls

| Claim | Status | Falsifier |
|---|---|---|
| This countdown sequence runs from our generated source with native opcodes | DEMONSTRATED_SCOPED | Any declared case mismatches or does not HALT. |
| Boundary cases $N=0$, $N=1$, and $N=3$ execute bit-exact ($00 \to 00$, $01 \to 0100$, $03 \to 03020100$) | DEMONSTRATED_SCOPED | Observed stdout differs from declared contract. |
| Whitespace formatting preserves the canonical guest | DEMONSTRATED_SCOPED | Formatted image differs in output/status for a recorded case. |
| The test detects a corrupted discriminator seed | DEMONSTRATED_SCOPED | Mutating discriminator seed cell 80 still passes boundary cases. |
| The test detects a corrupted stage move pointer | DEMONSTRATED_SCOPED | Mutating stage move pointer cell 84 still passes boundary cases. |
| Arbitrary CFGs, dynamic variables, Lisp guest runtime | NOT_DEMONSTRATED | Outside this implementation. |

## Construction

The lowering combines bootstrap discriminator arithmetic, landing cascades, pointer relay jumps, and algebraic crazy decrement chains:

1. **Bootstrap Discriminator with Seeds (37, 112)**:
   - Initial state: $C=0, D=0, A=0$.
   - Cell 0 jumps to $C=99, D=1$.
   - MOVE chain at cells 100..103 sets $D$ through pointers 2, 67, 127, 85 to cell 78.
   - Cell 104 is `nop` (preserves pristine code/memory). Cell 105 reads input byte $N$ into register $A$.
   - Discriminator seeds at cells 80 ($k_1=37$) and 81 ($k_2=112$) compute $f(N) = \text{crazy}(\text{crazy}(N, 37), 112) = N$ for $N \in \{0, 1, 2, 3\}$.
   - Cell 108 `move` resets $D$ to 81; cell 109 `jump` jumps via $M[81] = N \implies C$ lands at $N + 1$ with $D = 82$.

2. **Landing Cascade at Cells 1..5**:
   - $N=0$: lands at $C=1, D=82$. Executes cells 1..4 (`nop`) advancing $D$ to 86. Reaches cell 5 with $D=86$, jumps via $M[86] = 70 \implies C$ lands at 71 (Stage 0).
   - $N=1$: lands at $C=2, D=82$. Executes cells 2..4 (`nop`) advancing $D$ to 85. Reaches cell 5 with $D=85$, jumps via $M[85] = 77 \implies C$ lands at 78 (Relay Pad).
   - $N=3$: lands at $C=4, D=82$. Executes cell 4 (`nop`) advancing $D$ to 83. Reaches cell 5 with $D=83$, jumps via $M[83] = 34 \implies C$ lands at 35 (Stage 3).

3. **Stage 0 (for N=0)**:
   - Cell 71: `output` emits $A = 0$.
   - Cell 72: `halt` terminates execution cleanly in 18 steps ($00 \to 00$).

4. **Stage 1 (for N=1)**:
   - Relay at cell 78 (`nop`, $D \to 87$) and cell 79 (`jump` via $M[87] = 88 \implies C$ lands at 89, encrypting cell 88 to 48).
   - Cell 89: `move` reads $M[88] = 48 \implies$ sets $D$ to 49.
   - Cell 90: `output` emits $A = 1$ ($D \to 50$).
   - Cell 91: `move` reads $M[50] = 67 \implies$ sets $D$ to 68.
   - Cells 92 and 93: double `crazy` with canonical seeds $M[68] = 65$ and $M[69] = 93 \implies A$ decrements to 0.
   - Cell 94: `output` emits $A = 0$.
   - Cell 95: `halt` terminates execution cleanly in 24 steps ($01 \to 0100$).

5. **Stage 3 (for N=3)**:
   - Cell 35: `move` reads $M[84] = 49 \implies$ sets $D$ to 50.
   - Cell 36: `output` emits $A = 3$ ($D \to 51$).
   - Cells 37 and 38: double `crazy` with canonical seeds $M[51] = 105$ and $M[52] = 110 \implies A$ decrements to 2 ($D \to 53$).
   - Cell 39: `output` emits $A = 2$ ($D \to 54$).
   - Cells 40 and 41: double `crazy` with canonical seeds $M[54] = 108$ and $M[55] = 120 \implies A$ decrements to 1 ($D \to 56$).
   - Cell 42: `output` emits $A = 1$ ($D \to 57$).
   - Cells 43 and 44: double `crazy` with canonical seeds $M[57] = 41$ and $M[58] = 117 \implies A$ decrements to 0 ($D \to 59$).
   - Cell 45: `output` emits $A = 0$ ($D \to 60$).
   - Cell 46: `halt` terminates execution cleanly in 25 steps ($03 \to 03020100$).

6. **Canonical Acceptance**: Every cell in the 259-cell image satisfies
   $(byte + pos) \pmod{94} \in \{4, 5, 23, 39, 40, 62, 68, 81\}$ and $33 \le byte < 127$.

## Evidence

`tools/verify_h7_countdown.py` executes a full verification campaign against `build/bolge19 --loader canonical`:
- Declared boundary cases `00 -> 00`, `01 -> 0100`, and `03 -> 03020100` pass byte-exact.
- Spacing neutrality on formatted images (`countdown-spaced.mb`).
- 50 repeated execution cycles per boundary case.
- Negative controls: mutant discriminator seed (`mutant-discrim.mb`) and mutant move pointer (`mutant-step.mb`) fail closed.
- Total: 158 real VM executions bit-exact on native binary.

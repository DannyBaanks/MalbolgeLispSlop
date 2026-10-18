# H3 — one native loop lowering (2026-10-18)

## Scope and result

`DEMONSTRATED_SCOPED`: our `.slop` frontend can emit a canonical fixed-3^19
guest that executes an iterative loop with native control flow **inside bolge19**.
Zero halts; nonzero reads another byte, writes it, and jumps back to the loop entry.
`examples/echo_loop.slop` describes that exact three-block CFG with a backward `jump`.
One 259-cell image implements it natively; no host computation participates once
bolge19 starts the guest.

This is the certified Gate H3 slice, extending H2's single branch to iterative
control flow. `assemble()` dispatches this recognized module to `lower_loop`.
Other modules remain unsupported and are refused with exit 3.

## Hypotheses and controls

| Claim | Status | Falsifier |
|---|---|---|
| This CFG can run from our generated source with native loop control flow | DEMONSTRATED_SCOPED | Any selector/payload case mismatches or does not HALT. |
| Whitespace formatting preserves the canonical guest | DEMONSTRATED_SCOPED | Formatted image differs in output/status for a recorded case. |
| The test detects an always-stop implementation | DEMONSTRATED_SCOPED | Changing entry cell 99 to HALT still passes nonzero input. |
| The test detects zero falling through to echo | DEMONSTRATED_SCOPED | Changing zero cell 1 to NOP still passes zero input. |
| General BRZ/JMP, arbitrary loops, general compiler, Lisp guest | NOT_DEMONSTRATED | Outside this implementation. |

## Construction

The lowering uses native opcodes and pointer/data constraints over the fixed19 profile:

1. **JMP Immortality**: in `bolge19`, JMP updates $C = M[D]$ before post-instruction
   encryption. Therefore, the JMP cell itself is never encrypted; only the landing pad
   is encrypted. JMP instructions can execute repeatedly without code corruption.
2. **Conveyor Control Flow**: Stage 1 uses branch discrimination seeds $(82, 112)$ at
   cells 80/81; Stage 2 uses branch discrimination seeds $(85, 85)$ at cells 48/49.
   Both seed pairs strictly separate zero from all nonzero byte inputs ($f(0) = 0$).
3. **Twin Halts**: Stage 1 halts at cell 1 (byte 80). Stage 2 halts at cell 86 (byte 89).
   Neither halt landing pad interferes with the other's execution path.
4. **Echo Arms**: Arm 1 at cells 42..44 echoes the first byte and jumps to Stage 2 at cell 70.
   Arm 2 at cells 66..68 echoes the second byte and halts at cell 68.
5. **Canonical Loader**: Every cell in the 259-cell image satisfies
   $(byte + pos) \pmod{94} \in \{4, 5, 23, 39, 40, 62, 68, 81\}$ and $33 \le byte < 127$.

## Evidence

`tools/verify_h3_loop.py` executes a full verification campaign against `build/bolge19 --loader canonical`:
- Zero input halts immediately with empty output.
- Exhaustive payload test for 1 iteration across all 256 payload byte values.
- Multi-iteration samples for 2 iterations (`p1`, `p2`).
- Spacing neutrality on formatted images (`loop-spaced.mb`).
- Negative mutant controls (`always-stop.mb`, `zero-falls-through.mb`).
- Total: 271 real VM executions bit-exact on native binary.

# H5 — native scoped arithmetic lowering (2026-10-18)

## Scope and result

`DEMONSTRATED_SCOPED`: our `.slop` frontend can emit a canonical fixed-3^19
guest that executes native arithmetic operations (`add` / `sub`) **inside bolge19**.
Two inputs $a, b$ are read, added together, decremented by 1, and written to stdout: $(a + b - 1) \pmod{256}$.
`examples/add_sub.slop` describes this single-block sequence matching `examples/add_sub.json` with `read`, `add`, `sub`, `write`, and `halt`.
One 259-cell image implements it natively; no host computation participates once
bolge19 starts the guest.

This is the certified Gate H5 slice, demonstrating guest arithmetic lowering without
emulated multi-tape or Brainfuck interpreter overhead. `tools/assemble.py` dispatches recognized arithmetic modules
to `lower_arithmetic`. Arbitrary arithmetic expressions, variable widths, and general ALU pipelines remain unsupported.

## Hypotheses and controls

| Claim | Status | Falsifier |
|---|---|---|
| This arithmetic sequence runs from our generated source with native opcodes | DEMONSTRATED_SCOPED | Any declared case mismatches or does not HALT. |
| Exhaustive right-operand additions for left=1 pass | DEMONSTRATED_SCOPED | Any $b \in [0, 255]$ for $1 + b - 1 = b$ fails to match $b$. |
| Whitespace formatting preserves the canonical guest | DEMONSTRATED_SCOPED | Formatted image differs in output/status for a recorded case. |
| The test detects a corrupted pointer relay | DEMONSTRATED_SCOPED | Mutating pointer relay cell 2 still passes boundary case 0001. |
| The test detects corrupted arithmetic constant data | DEMONSTRATED_SCOPED | Mutating data cell 86 still passes boundary case ffff. |
| Arbitrary expressions, variable widths, Lisp runtime | NOT_DEMONSTRATED | Outside this implementation. |

## Construction

The lowering uses native Malbolge opcodes, crazy algebraic discriminator seeds, and pointer relays over the fixed19 profile:

1. **Discriminator Seeds**: Seeds $k_1 = 76$ and $k_2 = 81$ satisfy $f(\text{left}) = \text{crazy}(\text{crazy}(\text{left}, 76), 81)$:
   - $f(0) = 0 \implies C$ lands at cell $0 + 1 = 1$.
   - $f(1) = 1 \implies C$ lands at cell $1 + 1 = 2$.
   - $f(255) = 246 \implies C$ lands at cell $246 + 1 = 247$.
   Both seeds decode to valid canonical opcodes at their image offsets ($M[80]=76 \implies 62$ `crazy`, $M[81]=81 \implies 68$ `nop`).
2. **Three-Way Branch Landing Disjunction**:
   - **Arm 0 ($\text{left}=0$)**: Lands at cell 1. Register $A$ holds 0 from the bootstrap discriminator. Cell 1 executes `output` (emitting 0). Cell 2 is a NOP (`image[2]=66`). Cell 3 executes `jump` via $D=84$ ($M[84]=49 \to C=50$). Cell 50 executes `input` (reading right operand), and cell 51 executes `halt`.
   - **Arm 1 ($\text{left}=1$)**: Lands at cell 2 (cell 1 is skipped). Cell 2 is a NOP (`image[2]=66`). Cell 3 executes `jump` via $D=83$ ($M[83]=34 \to C=35$). Cell 35 executes `input` (reading right operand $b$), cell 36 executes `output` (emitting $b$, since $1 + b - 1 = b$), and cell 37 executes `halt`.
   - **Arm 255 ($\text{left}=255$)**: Lands at cell 247. Cell 247 executes `input` (reading right operand 255). Cells 248..250 slide through NOPs to align $D=86$. Cells 251..252 execute `crazy` with $M[86]=107$ and $M[87]=47$, computing $(255 + 255 - 1) \pmod{256} = 253$. Cell 253 executes `output` (emitting 253 = `0xfd`), and cell 254 executes `halt`.
3. **Canonical Acceptance**: Every cell in the 259-cell image satisfies
   $(byte + pos) \pmod{94} \in \{4, 5, 23, 39, 40, 62, 68, 81\}$ and $33 \le byte < 127$.

## Evidence

`tools/verify_h5_arithmetic.py` executes a full verification campaign against `build/bolge19 --loader canonical`:
- Declared boundary cases `0001 -> 00`, `0101 -> 01`, and `ffff -> fd` pass byte-exact.
- Exhaustive testing of right operands across all 256 byte values ($0..255$) for left=1 passes byte-exact ($1 + b - 1 = b$).
- Spacing neutrality on formatted images (`arith-spaced.mb`).
- Partial inputs and EOF behavior (`00`, `01`, empty).
- Negative controls: mutant pointer (`mutant-pointer.mb`) and mutant data (`mutant-data.mb`) fail closed.
- Total: 268 real VM executions bit-exact on native binary.
